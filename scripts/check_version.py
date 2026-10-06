"""Fail releases with mismatched package, runtime or tag versions."""
import os
from pathlib import Path
import re
import tomllib

ROOT=Path(__file__).resolve().parents[1]
configuration=tomllib.loads((ROOT/"pyproject.toml").read_text())
version=configuration["project"]["version"]
build=configuration["tool"]["gearforge"]["release"]["macos-build"]
if not re.fullmatch(r"[1-9][0-9]*",build):raise SystemExit("macOS build number must be a positive integer")
runtime=re.search(r'__version__\s*=\s*["\']([^"\']+)',(ROOT/"src/gearforge/__init__.py").read_text()).group(1)
if version!=runtime:raise SystemExit("Package/runtime version mismatch")
ref=os.environ.get("GITHUB_REF","")
if ref.startswith("refs/tags/") and ref!=f"refs/tags/v{version}":raise SystemExit("Release tag must match package version")
print(version)
