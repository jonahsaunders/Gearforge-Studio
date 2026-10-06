from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import sqlite3
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .catalog import Catalog
from .engine import run_search, synthesize
from .models import Project, candidate_from_dict, atomic_text, read_text_limited, strict_json


def worker(input_path=None):
    """A local one-shot subprocess protocol used by the desktop UI."""
    if input_path is not None:
        request=read_text_limited(Path(input_path),32_000_000,"Worker request")
    else:request=sys.stdin.read(32_000_001)
    if len(request.encode("utf-8"))>32_000_000:raise ValueError("Worker request exceeds 32 MB")
    payload = strict_json(request)
    if not isinstance(payload,dict) or not isinstance(payload.get("result_path"),str):
        raise ValueError("Invalid worker request")
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
    if "--worker" in argv or "--worker-file" in argv:
        try:
            return worker(argv[argv.index("--worker-file")+1]) if "--worker-file" in argv else worker()
        except (ValueError,OSError,TypeError,IndexError) as exc:
            print(f"GearForge worker: {exc}",file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(prog="gearforge",description="GearForge Studio desktop and batch design tools")
    parser.add_argument("--version",action="version",version=__version__)
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("gui",help="Launch the desktop app")
    subs.add_parser("doctor",help="Check runtime dependencies")
    verify = subs.add_parser("verify",help="Verify a design export or data backup against its manifest")
    verify.add_argument("directory",type=Path)
    backup = subs.add_parser("backup",help="Back up local catalog, profiles, settings and recovery; close the app first")
    backup.add_argument("--data-dir",type=Path,required=True)
    backup.add_argument("--out",type=Path,required=True)
    restore = subs.add_parser("restore",help="Restore a verified data backup into a new data directory")
    restore.add_argument("backup",type=Path)
    restore.add_argument("--data-dir",type=Path,required=True)
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
    qualify = subs.add_parser("qualify",help="Write a production-readiness assessment; exit 2 means not qualified")
    qualify.add_argument("project",type=Path)
    qualify.add_argument("--catalog",type=Path)
    qualify.add_argument("--candidate",default="best")
    qualify.add_argument("--out",type=Path,required=True)
    qualify.add_argument("--limit",type=int,default=60)
    export = subs.add_parser("export",help="Recalculate and export one candidate")
    export.add_argument("project",type=Path)
    export.add_argument("--catalog",type=Path)
    export.add_argument("--candidate",default="best")
    export.add_argument("--out",type=Path,required=True)
    export.add_argument("--report-only",action="store_true")
    export.add_argument("--require-production-rating",action="store_true",
                        help="Refuse export unless a verified production rating exists (unavailable in this release)")
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
        if args.command in ("verify","backup","restore"):
            from .maintenance import verify_bundle, backup_data, restore_data
            if args.command == "verify":
                manifest=verify_bundle(args.directory)
                result={"ok":True,"files":len(manifest["files"]),
                        "note":"Hashes verify integrity, not authorship or engineering approval."}
            elif args.command == "backup":result=backup_data(args.data_dir,args.out)
            else:result=restore_data(args.backup,args.data_dir)
            print(json.dumps(result,indent=2))
            return 0
        if not 1 <= args.limit <= 500:raise ValueError("Limit must be 1..500")
        project = Project.load(args.project)
        catalog = Catalog()
        try:
            if args.catalog:catalog.import_csv(read_text_limited(args.catalog,5_000_000,"Catalog","utf-8-sig"))
            catalog_text=catalog.export_csv()
            result = synthesize(project.requirements,project.profile,catalog,limit=args.limit)
        finally:catalog.close()
        if args.command == "search":
            if args.out.exists():raise FileExistsError("Search output already exists")
            atomic_text(args.out,json.dumps(asdict(result),indent=2,allow_nan=False))
            print(f"{len(result.candidates)} candidates; {result.evaluated} evaluated; {result.elapsed_s}s")
            return 0 if result.candidates else 2
        if not result.candidates:raise ValueError("No feasible design. Run search to inspect rejection counts.")
        candidate = result.candidates[0] if args.candidate == "best" else next((c for c in result.candidates if c.id == args.candidate),None)
        if candidate is None:raise ValueError("Candidate not found in current recalculation")
        if args.command == "qualify":
            from .qualification import production_assessment
            assessment=production_assessment(candidate,project.requirements,project.profile)
            if args.out.exists():raise FileExistsError("Assessment output already exists")
            atomic_text(args.out,json.dumps(assessment,indent=2,allow_nan=False))
            print(f"Not qualified for production: {len(assessment['blockers'])} engineering blockers. See {args.out}")
            return 2
        from .exporting import export_bundle
        exported = export_bundle(asdict(candidate),asdict(project.requirements),asdict(project.profile),str(args.out),not args.report_only,
                                 project=asdict(project),catalog_text=catalog_text,require_production=args.require_production_rating)
        print(json.dumps(exported,indent=2))
        return 0
    except (ValueError,OSError,TypeError,RuntimeError,sqlite3.Error) as exc:
        print(f"GearForge: {exc}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
