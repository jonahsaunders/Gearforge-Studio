"""Preserve exact installed distribution license/notice files for native packaging."""
from __future__ import annotations

import importlib.metadata
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NAMES=("PySide6-Essentials","shiboken6","cadquery","cadquery-ocp","numpy","vtk","reportlab",
       "ezdxf","casadi","nlopt","multimethod","typish","cadquery-ocp-proxy","pillow",
       "pyparsing","fonttools","typing_extensions")


def collect():
    destination=ROOT/"release-licenses";destination.mkdir(exist_ok=True)
    supplemental=ROOT/"packaging/licenses"
    if supplemental.exists():shutil.copytree(supplemental,destination,dirs_exist_ok=True)
    manifest={}
    for name in NAMES:
        try:distribution=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:continue
        copied=[]
        for entry in distribution.files or []:
            lower=str(entry).lower()
            basename=Path(str(entry)).name.lower()
            if not (basename.startswith(("license","copying","notice")) or "/licenses/" in lower):continue
            source=Path(distribution.locate_file(entry))
            if not source.is_file():continue
            target=destination/name/Path(str(entry)).name
            target.parent.mkdir(parents=True,exist_ok=True)
            # Preserve paths for multiple Qt/native dependency licenses.
            if target.exists() and target.read_bytes() != source.read_bytes():
                target=destination/name/str(entry).replace("/","__").replace("..","_")
            shutil.copyfile(source,target);copied.append(str(target.relative_to(destination)))
        manifest[name]={"version":distribution.version,"license_metadata":distribution.metadata.get("License-Expression") or distribution.metadata.get("License",""),"files":copied}
    (destination/"DEPENDENCIES.json").write_text(json.dumps(manifest,indent=2))
    # Some Qt wheels omit license texts from RECORD. Keep committed supplemental
    # upstream license texts and include them in the distribution manifest.
    for name in ("PySide6-Essentials", "shiboken6"):
        folder=destination/name
        if name in manifest and folder.exists():
            manifest[name]["files"]=sorted(str(f.relative_to(destination)) for f in folder.rglob("*") if f.is_file())
    (destination/"DEPENDENCIES.json").write_text(json.dumps(manifest,indent=2))
    for name in ("PySide6-Essentials","shiboken6","cadquery","cadquery-ocp"):
        if name not in manifest or not manifest[name]["files"]:raise RuntimeError(f"Missing core dependency license files: {name}")
    print(f"Preserved license files for {len(manifest)} distributions")


if __name__=="__main__":collect()
