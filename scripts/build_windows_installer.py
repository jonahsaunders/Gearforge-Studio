"""Compile a complete Windows installer from an already verified native bundle."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NSIS_VERSION = '3.13'
NSIS_SHA256 = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
NSIS_URL = 'https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip'


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def compiler():
    folder = ROOT / 'build' / 'installer-tools'
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / f'nsis-{NSIS_VERSION}.zip'
    if not archive.is_file() or sha256(archive) != NSIS_SHA256:
        url = NSIS_URL
        for _ in range(3):
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() == NSIS_SHA256:
                archive.write_bytes(data)
                break
            # SourceForge sometimes returns its download page with an expiring
            # meta-refresh link. Only follow HTTPS links on its own domain.
            match = re.search(r'<meta http-equiv="refresh" content="\d+; url=([^"]+)"', data.decode('utf-8', errors='replace'))
            if not match:
                raise RuntimeError('NSIS download failed its pinned SHA256 check')
            url = html.unescape(match.group(1))
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.sourceforge.net'):
                raise RuntimeError('Unexpected NSIS download redirect')
        else:
            raise RuntimeError('Could not retrieve the pinned NSIS archive')
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            if not (folder / name).resolve().is_relative_to(folder.resolve()):
                raise ValueError('Unsafe compiler archive member')
        zipped.extractall(folder)
    return folder / f'nsis-{NSIS_VERSION}' / 'makensis.exe'


def nsis_string(value):
    return str(value).replace('$', '$$').replace('"', '$\\"')


def uninstall_manifest(source):
    files = sorted(p for p in source.rglob('*') if p.is_file())
    directories = sorted((p for p in source.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
    lines = [f'Delete "$INSTDIR\\{nsis_string(p.relative_to(source))}"' for p in files]
    lines += [f'RMDir "$INSTDIR\\{nsis_string(p.relative_to(source))}"' for p in directories]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--makensis', type=Path)
    parser.add_argument('--smoke-evidence', type=Path, default=ROOT / 'build' / 'frozen-smoke' / 'desktop-smoke.json')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise RuntimeError('Build the Windows installer on Windows')
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    source = ROOT / 'dist' / 'GearForgeStudio'
    if not (source / 'GearForgeStudio.exe').is_file() or not (source / '_internal').is_dir():
        raise RuntimeError('Build and smoke-test the native application first')
    evidence = json.loads(args.smoke_evidence.read_text())
    if not evidence.get('ok') or evidence.get('engineering_study', {}).get('app_version') != version:
        raise RuntimeError('The native smoke evidence does not match this version')
    executable_version = subprocess.check_output([str(source / 'GearForgeCLI.exe'), '--version'], text=True).strip()
    if executable_version != version:
        raise RuntimeError('The native executable does not match the release version')
    # Include current installation guidance and redistributable example inputs.
    documents = source / '_internal' / 'documentation'
    for name in ('RELEASE_STATUS.md', 'INTERNAL_DEPLOYMENT.md', 'WINDOWS_INSTALL.md'):
        shutil.copy2(ROOT / 'docs' / name, documents / name)
    examples = source / 'examples'
    examples.mkdir(exist_ok=True)
    for example in (ROOT / 'examples').glob('*.gearforge*'):
        if example.is_file():
            shutil.copy2(example, examples / example.name)
    command = args.makensis or compiler()
    tool_version = subprocess.check_output([str(command), '/VERSION'], text=True).strip()
    if tool_version != 'v' + NSIS_VERSION:
        raise RuntimeError(f'Expected NSIS {NSIS_VERSION}, got {tool_version}')
    # Preserve the installer engine's notices beside the application's notices.
    notices = source / '_internal' / 'licenses' / 'nsis'
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copy2(command.parent / 'COPYING', notices / 'COPYING.txt')
    staging = ROOT / 'build' / 'windows-installer'
    staging.mkdir(parents=True, exist_ok=True)
    manifest = staging / 'uninstall-files.nsh'
    manifest.write_text(uninstall_manifest(source), encoding='utf-8-sig')
    output = ROOT / 'release-assets'
    output.mkdir(exist_ok=True)
    installer = output / f'GearForge-Studio-{version}-Windows-x64-Setup.exe'
    numeric = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?', version)
    if not numeric:
        raise ValueError('Unsupported installer version')
    definitions = {'VERSION': version, 'NUMERIC_VERSION': '.'.join(v or '0' for v in numeric.groups()),
                   'SOURCE_DIR': source, 'PROJECT_DIR': ROOT, 'OUTPUT_FILE': installer,
                   'UNINSTALL_FILES': manifest,
                   'MAX_INSTALL_DIR_LENGTH': 240 - max(len(str(p.relative_to(source))) for p in source.rglob('*') if p.is_file()),
                   'INSTALLED_KIB': (sum(p.stat().st_size for p in source.rglob('*') if p.is_file()) + 1023) // 1024}
    subprocess.run([str(command), '/V2', '/WX', *[f'/D{k}={v}' for k, v in definitions.items()],
                    str(ROOT / 'packaging' / 'windows-installer.nsi')], check=True)
    digest = sha256(installer)
    installer.with_suffix('.exe.sha256').write_text(f'{digest}  {installer.name}\n', encoding='utf-8')
    print(installer)
    print(f'{installer.stat().st_size:,} bytes; SHA256 {digest}')


if __name__ == '__main__':
    main()
