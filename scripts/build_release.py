from __future__ import annotations

import hashlib
import shutil
import stat
import zipfile
import tomllib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    version=tomllib.loads((ROOT/"pyproject.toml").read_text())["project"]["version"]
    stage=ROOT/"release"/f"GearForge-Studio-{version}"
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for name in ("README.md","LICENSE","THIRD_PARTY_NOTICES.md","CHANGELOG.md","pyproject.toml","MANIFEST.in","VALIDATION.json","CONTRIBUTING.md","SECURITY.md",".gitignore","constraints-release.txt"):
        source=ROOT/name
        if source.exists():shutil.copy2(source,stage/name)
    for directory in ("src","tests","docs","scripts","packaging","examples","release-licenses","screenshots"):
        source=ROOT/directory
        if source.exists():shutil.copytree(source,stage/directory,ignore=shutil.ignore_patterns("__pycache__","*.pyc","*.egg-info","exported-*"))
    (stage/"dist").mkdir()
    for source in (ROOT/"dist").glob(f"gearforge_studio-{version}-*.whl"):shutil.copy2(source,stage/"dist"/source.name)
    (stage/"VERSION.txt").write_text(version+"\n")
    for source in (ROOT/"packaging").glob("Install-and-launch.*"):
        shutil.copy2(source,stage/source.name)
        if source.suffix in (".sh",".command"):(stage/source.name).chmod(0o755)
    workflow=ROOT/".github"
    if workflow.exists():shutil.copytree(workflow,stage/".github")
    checksums=[]
    for file in sorted(stage.rglob("*")):
        if file.is_file():checksums.append(hashlib.sha256(file.read_bytes()).hexdigest()+"  "+file.relative_to(stage).as_posix())
    (stage/"SHA256SUMS.txt").write_text("\n".join(checksums)+"\n")
    output=ROOT/"release-assets";output.mkdir(exist_ok=True)
    archive=output/f"GearForge-Studio-{version}-release.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for file in sorted(stage.rglob("*")):
            if file.is_file():zipped.write(file,file.relative_to(stage.parent))
    archive.with_name(archive.name+".sha256").write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+"  "+archive.name+"\n")
    print(archive)


if __name__=="__main__":main()
