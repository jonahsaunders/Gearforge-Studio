"""Inventory the installed runtime dependency closure and preserve license texts.

Includes declared visualization dependencies even when the frozen app excludes
their modules: a conservative inventory, not a legal opinion.
"""
from __future__ import annotations

import importlib.metadata as metadata
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def runtime_distributions():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pending = [Requirement(value) for value in project["dependencies"]]
    found, visited = {}, set()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        key = (name, tuple(sorted(requirement.extras)))
        if key in visited:
            continue
        visited.add(key)
        distribution = metadata.distribution(name)
        if distribution.version not in requirement.specifier:
            raise RuntimeError(f"Incompatible installed dependency: {requirement}")
        found[name] = distribution
        for value in distribution.requires or []:
            child = Requirement(value)
            if not child.marker or any(child.marker.evaluate({"extra": extra})
                                       for extra in {"", *requirement.extras}):
                pending.append(child)
    return dict(sorted(found.items()))


def collect():
    destination = ROOT / "release-licenses"
    destination.mkdir(exist_ok=True)
    manifest = {}
    for name, distribution in runtime_distributions().items():
        folder = destination / name
        if folder.exists():
            # Only remove this generated distribution directory under ROOT.
            if folder.resolve().parent != destination.resolve():
                raise ValueError("Unsafe license output path")
            shutil.rmtree(folder)
        folder.mkdir()
        for entry in distribution.files or []:
            lower = str(entry).lower().replace("\\", "/")
            if not (Path(lower).name.startswith(("license", "copying", "notice")) or "/licenses/" in lower):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                filename = lower.replace("/", "__").replace("..", "_")
                # Deep vendor trees can exceed Windows installer path limits.
                # Retain every notice with a deterministic, collision-resistant name.
                if len(filename) > 72:
                    filename = Path(lower).name[:40] + "__" + hashlib.sha256(lower.encode()).hexdigest()[:16]
                target = folder / filename
                shutil.copyfile(source, target)
        for supplemental in (ROOT / "packaging/licenses").iterdir():
            if canonicalize_name(supplemental.name) == name:
                shutil.copytree(supplemental, folder, dirs_exist_ok=True)
        license_files = sorted(p.relative_to(destination).as_posix() for p in folder.rglob("*") if p.is_file())
        manifest[name] = {
            "version": distribution.version,
            "license_metadata": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", ""),
            "project_urls": distribution.metadata.get_all("Project-URL") or [],
            "files": license_files,
            "requires_license_review": not bool(license_files),
        }
    (destination / "DEPENDENCIES.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (destination / "requirements-runtime.txt").write_text(
        "".join(f"{name}=={value['version']}\n" for name, value in manifest.items()), encoding="utf-8")
    for name in ("pyside6-essentials", "shiboken6", "cadquery", "cadquery-ocp", "vtk"):
        if not manifest.get(name, {}).get("files"):
            raise RuntimeError(f"Missing core dependency license files: {name}")
    missing = [name for name, value in manifest.items() if value["requires_license_review"]]
    print(f"Inventoried {len(manifest)} runtime distributions; missing license texts: {missing}")
    return manifest


if __name__ == "__main__":
    collect()
