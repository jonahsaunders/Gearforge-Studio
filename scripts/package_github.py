"""Create a source-only repository ZIP with paths rooted at the project level."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md",
    "CONTRIBUTING.md", "SECURITY.md", "pyproject.toml", "MANIFEST.in",
    "constraints-release.txt", "VALIDATION.json", ".gitignore",
)
DIRECTORIES = ("src", "tests", "docs", "examples", "screenshots", "packaging", "scripts", ".github")


def source_files():
    files = [ROOT / name for name in ROOT_FILES]
    for name in DIRECTORIES:
        for file in (ROOT / name).rglob("*"):
            relative = file.relative_to(ROOT)
            if not file.is_file() or file.is_symlink():
                continue
            if any(p in ("__pycache__", ".pytest_cache") or p.endswith(".egg-info") for p in relative.parts):
                continue
            if file.suffix in (".pyc", ".pyo", ".log", ".sqlite", ".xml"):
                continue
            if name == "examples" and any(p.startswith("exported-") for p in relative.parts):
                continue
            files.append(file)
    return sorted(set(files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    output = args.out or ROOT / "release-assets" / f"GearForge-Studio-{version}-GitHub-source.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = source_files()
    checksums = [f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.relative_to(ROOT).as_posix()}" for file in files]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in files:
            archive.write(file, file.relative_to(ROOT))
        archive.writestr("SHA256SUMS.txt", "\n".join(checksums) + "\n")
    print(f"{output.resolve()}\n{len(files) + 1} files; {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
