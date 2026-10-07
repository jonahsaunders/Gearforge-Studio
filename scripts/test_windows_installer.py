"""Install, exercise and uninstall the actual Windows package in an isolated folder.

Run on a clean build machine: this checks the real per-user registration and
Start Menu entries, and refuses to replace an existing registered installation.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import uuid

ROOT = Path(__file__).resolve().parents[1]
KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\GearForgeStudio'


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Test the Windows installer on Windows')
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            pass
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('An existing GearForge installation must not be replaced by this test')
    shortcuts = Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'GearForge Studio'
    if shortcuts.exists():
        raise RuntimeError('Existing GearForge Start Menu entries must not be replaced by this test')
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    installer = ROOT / 'release-assets' / f'GearForge-Studio-{version}-Windows-x64-Setup.exe'
    destination = (ROOT / 'build' / ('installer smoke-' + uuid.uuid4().hex)).resolve()
    if not destination.is_relative_to((ROOT / 'build').resolve()) or destination.exists():
        raise ValueError('Unsafe installer test destination')
    occupied = (ROOT / 'build' / ('installer-occupied-' + uuid.uuid4().hex)).resolve()
    occupied.mkdir()
    existing_document = occupied / 'existing-project.txt'
    existing_document.write_text('Do not overwrite this folder.', encoding='utf-8')
    command = subprocess.list2cmdline([str(installer), '/S']) + ' /D=' + str(occupied)
    blocked = subprocess.run(command, timeout=90)
    assert blocked.returncode != 0
    assert list(occupied.iterdir()) == [existing_document]
    assert existing_document.read_text(encoding='utf-8') == 'Do not overwrite this folder.'
    print('Nonempty destination rejected without changing existing files.', flush=True)
    long_destination = ROOT / 'build' / ('installer-long-' + 'x' * 140)
    command = subprocess.list2cmdline([str(installer), '/S']) + ' /D=' + str(long_destination)
    assert subprocess.run(command, timeout=90).returncode != 0
    assert not long_destination.exists()
    print('Overlong installation path rejected before creating files.', flush=True)
    # NSIS requires /D and _?= to be the final, unquoted command-line tail.
    command = subprocess.list2cmdline([str(installer), '/S']) + ' /D=' + str(destination)
    subprocess.run(command, check=True, timeout=300)
    try:
        source = ROOT / 'dist' / 'GearForgeStudio'
        files = [p for p in source.rglob('*') if p.is_file()]
        for file in files:
            target = destination / file.relative_to(source)
            if not target.is_file() or sha256(target) != sha256(file):
                raise RuntimeError(f'Installed file differs: {file.relative_to(source)}')
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            assert winreg.QueryValueEx(key, 'InstallLocation')[0] == str(destination)
            assert winreg.QueryValueEx(key, 'DisplayVersion')[0] == version
            assert winreg.QueryValueEx(key, 'UninstallString')[0] == f'"{destination / "Uninstall.exe"}"'
            assert winreg.QueryValueEx(key, 'QuietUninstallString')[0] == f'"{destination / "Uninstall.exe"}" /S'
        assert (shortcuts / 'GearForge Studio.lnk').is_file()
        print(f'Installed {len(files)} files; content, registration and shortcuts verified.', flush=True)
        executable = destination / 'GearForgeCLI.exe'
        assert subprocess.check_output([str(executable), '--version'], text=True).strip() == version
        # Import the bundled dependencies, then drive the GUI and real CAD worker
        # from the installed location with no Python runtime on PATH.
        environment = os.environ.copy()
        environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        environment['QT_QPA_FONTDIR'] = str(Path(os.environ['SystemRoot']) / 'Fonts')
        subprocess.run([str(executable), 'doctor'], check=True, env=environment, capture_output=True, text=True, timeout=60)
        smoke = ROOT / 'build' / ('installed-smoke-' + uuid.uuid4().hex)
        result = subprocess.run([str(executable), 'smoke', '--out', str(smoke), '--cad'], env=environment,
                                capture_output=True, text=True, timeout=240)
        (ROOT / 'build' / 'installed-smoke.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('Installed desktop/CAD smoke failed; see build/installed-smoke.log')
        evidence = json.loads((smoke / 'desktop-smoke.json').read_text())
        assert evidence['ok'] and evidence['cad_meshes'] > 0
        print('Installed desktop and CAD checks passed without Python on PATH.', flush=True)
        # An arbitrary user-created document must survive uninstalling the app.
        user_document = destination / 'user-project-note.txt'
        user_document.write_text('Keep my project data.', encoding='utf-8')
    finally:
        uninstaller = destination / 'Uninstall.exe'
        if uninstaller.is_file():
            command = subprocess.list2cmdline([str(uninstaller), '/S']) + ' _?=' + str(destination)
            subprocess.run(command, check=True, timeout=120)
            # _?= keeps the test synchronous rather than spawning a temp copy.
            # Windows cannot remove the running uninstaller; remove that one file.
            uninstaller.unlink(missing_ok=True)
    assert not (destination / 'GearForgeStudio.exe').exists()
    assert not (destination / '_internal').exists()
    assert user_document.read_text(encoding='utf-8') == 'Keep my project data.'
    assert not shortcuts.exists()
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('Uninstall registration remains after uninstall')
    report = {'version': version, 'installer_sha256': sha256(installer), 'installed_files_verified': len(files),
              'desktop_and_cad_smoke': evidence, 'python_on_path': False,
              'registration_and_shortcuts_verified': True, 'uninstall_verified': True, 'user_document_preserved': True}
    report['nonempty_destination_rejected'] = True
    report['overlong_destination_rejected'] = True
    (ROOT / 'build' / 'windows-installer-test.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Installer verified: {len(files)} files; desktop/CAD passed; uninstall preserved user data.')


if __name__ == '__main__':
    main()
