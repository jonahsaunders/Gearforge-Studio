from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .catalog import Catalog
from .engine import run_search, synthesize
from .models import Project, candidate_from_dict, atomic_text


def worker(input_path=None):
    """A local one-shot subprocess protocol used by the desktop UI."""
    if input_path is not None:
        input_path=Path(input_path)
        if input_path.stat().st_size > 32_000_000:raise ValueError("Worker request exceeds 32 MB")
        request=input_path.read_text(encoding="utf-8")
    else:request=sys.stdin.read(32_000_001)
    payload = json.loads(request)
    output = Path(payload.pop("result_path"))
    try:
        task = payload.pop("task")
        if task == "search":
            result = run_search(**payload)
        elif task == "preview":
            from .geometry import build_preview
            result = build_preview(**payload)
        elif task == "export":
            from .exporting import export_bundle
            result = export_bundle(**payload)
        elif task == "coupon":
            from .calibration import export_coupon
            export_coupon(**payload)
            result = {"destination":payload["path"]}
        elif task == "mesh-check":
            from .simulation import sampled_mesh_check
            result = sampled_mesh_check(**payload)
        else:
            raise ValueError("Unknown worker task")
        response = {"ok":True,"result":result}
    except Exception as exc:
        response = {"ok":False,"error":str(exc),"type":type(exc).__name__}
    atomic_text(output,json.dumps(response,allow_nan=False))
    return 0 if response["ok"] else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--worker" in argv:
        return worker()
    if "--worker-file" in argv:
        return worker(argv[argv.index("--worker-file")+1])
    parser = argparse.ArgumentParser(prog="gearforge",description="GearForge Studio desktop and batch design tools")
    parser.add_argument("--version",action="version",version=__version__)
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("gui",help="Launch the desktop app")
    subs.add_parser("doctor",help="Check runtime dependencies")
    smoke = subs.add_parser("smoke",help="Run the desktop worker and capture a diagnostic screenshot")
    smoke.add_argument("--out",type=Path,required=True)
    smoke.add_argument("--cad",action="store_true")
    new = subs.add_parser("new",help="Create a default project")
    new.add_argument("path",type=Path)
    search = subs.add_parser("search",help="Search a project and save candidate JSON")
    search.add_argument("project",type=Path)
    search.add_argument("--catalog",type=Path)
    search.add_argument("--out",type=Path,required=True)
    search.add_argument("--limit",type=int,default=60)
    export = subs.add_parser("export",help="Recalculate and export one candidate")
    export.add_argument("project",type=Path)
    export.add_argument("--catalog",type=Path)
    export.add_argument("--candidate",default="best")
    export.add_argument("--out",type=Path,required=True)
    export.add_argument("--report-only",action="store_true")
    export.add_argument("--limit",type=int,default=60)
    args = parser.parse_args(argv)
    try:
        if args.command in (None,"gui"):
            from .app import main as launch
            return launch()
        if args.command == "doctor":
            result = {"app":__version__,"python":sys.version.split()[0],"dependencies":{}}
            for package in ("cadquery","PySide6-Essentials","reportlab"):
                try:result["dependencies"][package]=importlib.metadata.version(package)
                except importlib.metadata.PackageNotFoundError:result["dependencies"][package]="MISSING"
            print(json.dumps(result,indent=2))
            return int("MISSING" in result["dependencies"].values())
        if args.command == "smoke":
            from .diagnostics import desktop_smoke
            return desktop_smoke(args.out,args.cad)
        if args.command == "new":
            if args.path.exists():raise FileExistsError("Project already exists")
            Project().save(args.path)
            print(args.path)
            return 0
        if not 1 <= args.limit <= 500:raise ValueError("Limit must be 1..500")
        project = Project.load(args.project)
        catalog = Catalog()
        if args.catalog:catalog.import_csv(args.catalog.read_text(encoding="utf-8-sig"))
        result = synthesize(project.requirements,project.profile,catalog,limit=args.limit)
        catalog.close()
        if args.command == "search":
            if args.out.exists():raise FileExistsError("Search output already exists")
            atomic_text(args.out,json.dumps(asdict(result),indent=2,allow_nan=False))
            print(f"{len(result.candidates)} candidates; {result.evaluated} evaluated; {result.elapsed_s}s")
            return 0 if result.candidates else 2
        if not result.candidates:raise ValueError("No feasible design. Run search to inspect rejection counts.")
        candidate = result.candidates[0] if args.candidate == "best" else next((c for c in result.candidates if c.id == args.candidate),None)
        if candidate is None:raise ValueError("Candidate not found in current recalculation")
        from .exporting import export_bundle
        exported = export_bundle(asdict(candidate),asdict(project.requirements),asdict(project.profile),str(args.out),not args.report_only)
        print(json.dumps(exported,indent=2))
        return 0
    except (ValueError,OSError,TypeError,json.JSONDecodeError) as exc:
        print(f"GearForge: {exc}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
