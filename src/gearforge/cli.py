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
        elif task in ("root-calculate","root-export"):
            from .root_stress import RootStressStudy,calculate_root_study,export_root_study
            study=RootStressStudy.from_dict(payload['study'])
            result=calculate_root_study(study) if task=='root-calculate' else export_root_study(study,Path(payload['destination']))
        elif task in ('history-calculate','history-export'):
            from .cyclic import HistoryStudy,calculate_history_study,export_history_study
            study=HistoryStudy.from_dict(payload['study'])
            result=calculate_history_study(study) if task=='history-calculate' else export_history_study(study,Path(payload['destination']))
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
    study = subs.add_parser("study",help="Create or calculate a traceable spur/helical engineering study")
    study_commands = study.add_subparsers(dest="study_command",required=True)
    study_new = study_commands.add_parser("new",help="Create the agreed 250 W, 1500 rpm, 5:1 qualification target")
    study_new.add_argument("path",type=Path)
    study_calculate = study_commands.add_parser("calculate",help="Export geometry, quasi-static loads and duty exposure; no production rating")
    study_calculate.add_argument("path",type=Path)
    study_calculate.add_argument("--out",type=Path,required=True)
    shaft = subs.add_parser("shaft",help="Create or calculate explicit shaft and bearing loads")
    shaft_commands = shaft.add_subparsers(dest="shaft_command",required=True)
    shaft_new = shaft_commands.add_parser("new",help="Create an editable shaft study for the 250 W development target")
    shaft_new.add_argument("path",type=Path)
    shaft_from = shaft_commands.add_parser("from-study",help="Transfer all gear duty cases and the off-axis thrust couple")
    shaft_from.add_argument("path",type=Path)
    shaft_from.add_argument("--role",choices=["pinion","wheel"],default="pinion")
    shaft_from.add_argument("--out",type=Path,required=True)
    shaft_calculate = shaft_commands.add_parser("calculate",help="Export bearing loads, elastic motion and nominal shaft stress")
    shaft_calculate.add_argument("path",type=Path)
    shaft_calculate.add_argument("--out",type=Path,required=True)
    bearing = subs.add_parser("bearing",help="Assess explicit bearing ratings against a retained shaft duty study")
    bearing_commands = bearing.add_subparsers(dest="bearing_command",required=True)
    bearing_new = bearing_commands.add_parser("new",help="Create blank bearing definitions for the development shaft")
    bearing_new.add_argument("path",type=Path)
    bearing_new.add_argument("--synthetic-example",action="store_true",help="Use original invented ratings for verification only")
    bearing_from = bearing_commands.add_parser("from-shaft",help="Retain a shaft study and create blank bearing data for every case")
    bearing_from.add_argument("path",type=Path)
    bearing_from.add_argument("--out",type=Path,required=True)
    bearing_calculate = bearing_commands.add_parser("calculate",help="Export per-bearing basic fatigue and explicit operating-limit checks")
    bearing_calculate.add_argument("path",type=Path)
    bearing_calculate.add_argument("--out",type=Path,required=True)
    fatigue = subs.add_parser("fatigue",help="Assess explicit shaft material and rotating-bending fatigue blocks")
    fatigue_commands = fatigue.add_subparsers(dest="fatigue_command",required=True)
    fatigue_new = fatigue_commands.add_parser("new",help="Create blank fatigue evidence for the development shaft")
    fatigue_new.add_argument("path",type=Path)
    fatigue_new.add_argument("--nasa-example",action="store_true",help="Use public NASA numerical benchmark inputs, never material allowables")
    fatigue_from = fatigue_commands.add_parser("from-shaft",help="Retain shaft inputs with fresh material and critical-section data")
    fatigue_from.add_argument("path",type=Path)
    fatigue_from.add_argument("--out",type=Path,required=True)
    fatigue_calculate = fatigue_commands.add_parser("calculate",help="Export bounded stress-life arithmetic and evidence gaps; no production rating")
    fatigue_calculate.add_argument("path",type=Path)
    fatigue_calculate.add_argument("--out",type=Path,required=True)
    contact = subs.add_parser("contact",help="Assess tooth contact pressure and declared surface-fatigue curves")
    contact_commands = contact.add_subparsers(dest="contact_command",required=True)
    contact_new = contact_commands.add_parser("new",help="Create blank material and contact factors for the development gear pair")
    contact_new.add_argument("path",type=Path)
    contact_new.add_argument("--synthetic-example",action="store_true",help="Use original invented material/fatigue data for arithmetic only")
    contact_from = contact_commands.add_parser("from-study",help="Retain a gear study with fresh contact material and factor data")
    contact_from.add_argument("path",type=Path);contact_from.add_argument("--out",type=Path,required=True)
    contact_calculate = contact_commands.add_parser("calculate",help="Export contact path, pressure and separate flank exposure; no production rating")
    contact_calculate.add_argument("path",type=Path);contact_calculate.add_argument("--out",type=Path,required=True)
    thermal = subs.add_parser("thermal",help="Assess declared heat losses, thermal paths and ordered cooling duty")
    thermal_commands = thermal.add_subparsers(dest="thermal_command",required=True)
    thermal_new = thermal_commands.add_parser("new",help="Create unknown thermal inputs for the development gear study")
    thermal_new.add_argument("path",type=Path);thermal_new.add_argument("--synthetic-example",action="store_true")
    thermal_from = thermal_commands.add_parser("from-study",help="Retain a gear study with fresh heat/cooling inputs")
    thermal_from.add_argument("path",type=Path);thermal_from.add_argument("--out",type=Path,required=True)
    thermal_calculate = thermal_commands.add_parser("calculate",help="Export thermal histories, continuous extrema and energy balance; no production rating")
    thermal_calculate.add_argument("path",type=Path);thermal_calculate.add_argument("--out",type=Path,required=True)
    tooth = subs.add_parser("tooth",help="Study rack-generated spur roots and export sampled profiles")
    tooth_commands = tooth.add_subparsers(dest="tooth_command",required=True)
    tooth_new = tooth_commands.add_parser("new",help="Create unknown cutter inputs or an explicit synthetic example")
    tooth_new.add_argument("path",type=Path);tooth_new.add_argument("--synthetic-example",action="store_true")
    tooth_from = tooth_commands.add_parser("from-study",help="Retain gear geometry with fresh cutter evidence")
    tooth_from.add_argument("path",type=Path);tooth_from.add_argument("--out",type=Path,required=True)
    tooth_from.add_argument("--role",choices=["pinion","wheel"],default="pinion")
    tooth_calculate = tooth_commands.add_parser("calculate",help="Export analytic dimensions, sampled DXF/SVG and coordinates; no production rating")
    tooth_calculate.add_argument("path",type=Path);tooth_calculate.add_argument("--out",type=Path,required=True)
    root = subs.add_parser("root",help="Study elastic stress in a rack-generated spur root")
    root_commands = root.add_subparsers(dest="root_command",required=True)
    root_new = root_commands.add_parser("new",help="Create unknown material/support inputs or a synthetic example")
    root_new.add_argument("path",type=Path);root_new.add_argument("--synthetic-example",action="store_true")
    root_from = root_commands.add_parser("from-profile",help="Retain cutter geometry with fresh elastic material and load data")
    root_from.add_argument("path",type=Path);root_from.add_argument("--out",type=Path,required=True)
    root_calculate = root_commands.add_parser("calculate",help="Export 2D elastic fields, mesh checks and evidence gaps; no fatigue rating")
    root_calculate.add_argument("path",type=Path);root_calculate.add_argument("--out",type=Path,required=True)
    history = subs.add_parser('history',help='Count local stress cycles and assess bounded uniaxial fatigue damage')
    history_commands = history.add_subparsers(dest='history_command',required=True)
    history_new = history_commands.add_parser('new',help='Create unknown inputs or an original synthetic example')
    history_new.add_argument('path',type=Path);history_new.add_argument('--synthetic-example',action='store_true')
    history_from = history_commands.add_parser('from-study',help='Retain gear duty with fresh local history and material inputs')
    history_from.add_argument('path',type=Path);history_from.add_argument('--out',type=Path,required=True)
    history_calculate = history_commands.add_parser('calculate',help='Export cycles, bounded damage and evidence gaps; no production rating')
    history_calculate.add_argument('path',type=Path);history_calculate.add_argument('--out',type=Path,required=True)
    history_import = history_commands.add_parser('import-csv',help='Import signed time/stress CSV into a named block and save a new study')
    history_import.add_argument('path',type=Path);history_import.add_argument('csv',type=Path)
    history_import.add_argument('--block',required=True);history_import.add_argument('--out',type=Path,required=True)
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
        if args.command == 'history':
            from .cyclic import HistoryStudy,history_from_study,synthetic_history_example,export_history_study,import_sample_csv
            from .engineering import EngineeringStudy
            if args.history_command == 'calculate':
                print(json.dumps(export_history_study(HistoryStudy.load(args.path),args.out),indent=2));return 0
            destination=args.path if args.history_command=='new' else args.out
            if destination.exists() or destination.is_symlink():raise FileExistsError('History study already exists')
            if args.history_command=='new':study=synthetic_history_example() if args.synthetic_example else HistoryStudy()
            elif args.history_command=='from-study':study=history_from_study(EngineeringStudy.load(args.path))
            else:
                study=HistoryStudy.load(args.path)
                blocks=[b for b in study.blocks if b.name==args.block]
                if not blocks:raise ValueError('No history block has that name')
                import_sample_csv(args.csv,blocks[0])
            study.save(destination);print(destination);return 0
        if args.command == "root":
            from .root_stress import RootStressStudy,root_from_profile,synthetic_root_example,export_root_study
            from .tooth_profile import ToothProfileStudy
            if args.root_command in ("new","from-profile"):
                destination=args.path if args.root_command=='new' else args.out
                if destination.exists() or destination.is_symlink():raise FileExistsError('Root study already exists')
                study=(synthetic_root_example() if args.synthetic_example else RootStressStudy()) if args.root_command=='new' else root_from_profile(ToothProfileStudy.load(args.path))
                study.save(destination);return 0
            print(json.dumps(export_root_study(RootStressStudy.load(args.path),args.out),indent=2));return 0
        if args.command == "tooth":
            from .tooth_profile import ToothProfileStudy,profile_from_study,synthetic_profile_example,export_profile_study
            from .engineering import EngineeringStudy
            if args.tooth_command in ("new","from-study"):
                destination=args.path if args.tooth_command=="new" else args.out
                if destination.exists() or destination.is_symlink():raise FileExistsError("Tooth study already exists")
                study=(synthetic_profile_example() if args.synthetic_example else ToothProfileStudy()) if args.tooth_command=="new" else profile_from_study(EngineeringStudy.load(args.path),args.role)
                study.save(destination);print(destination);return 0
            result=export_profile_study(ToothProfileStudy.load(args.path),args.out)
            print(json.dumps(result,indent=2));return 0
        if args.command == "study":
            from .engineering import EngineeringStudy, export_study
            if args.study_command == "new":
                if args.path.exists() or args.path.is_symlink():raise FileExistsError("Study already exists")
                EngineeringStudy().save(args.path)
                print(args.path)
            else:
                result=export_study(EngineeringStudy.load(args.path),args.out)
                print(json.dumps(result,indent=2))
            return 0
        if args.command == "shaft":
            from .engineering import EngineeringStudy
            from .shafts import ShaftStudy, shaft_from_gear_study, export_shaft_study
            if args.shaft_command == "calculate":
                print(json.dumps(export_shaft_study(ShaftStudy.load(args.path),args.out),indent=2))
            else:
                path=args.path if args.shaft_command=="new" else args.out
                if path.exists() or path.is_symlink():raise FileExistsError("Shaft study already exists")
                source=EngineeringStudy() if args.shaft_command=="new" else EngineeringStudy.load(args.path)
                shaft_from_gear_study(source,getattr(args,"role","pinion")).save(path)
                print(path)
            return 0
        if args.command == "bearing":
            from .bearings import BearingStudy, bearings_from_shaft, synthetic_bearing_example, export_bearing_study
            from .shafts import ShaftStudy, shaft_from_gear_study
            from .engineering import EngineeringStudy
            if args.bearing_command == "calculate":
                print(json.dumps(export_bearing_study(BearingStudy.load(args.path),args.out),indent=2))
            else:
                path=args.out if args.bearing_command=="from-shaft" else args.path
                if path.exists() or path.is_symlink():raise FileExistsError("Bearing study already exists")
                if args.bearing_command=="from-shaft":study=bearings_from_shaft(ShaftStudy.load(args.path))
                elif args.synthetic_example:study=synthetic_bearing_example()
                else:study=bearings_from_shaft(shaft_from_gear_study(EngineeringStudy()))
                study.save(path);print(path)
            return 0
        if args.command == "fatigue":
            from .fatigue import FatigueStudy,fatigue_from_shaft,nasa_example,export_fatigue_study
            from .shafts import ShaftStudy,shaft_from_gear_study
            from .engineering import EngineeringStudy
            if args.fatigue_command == "calculate":
                print(json.dumps(export_fatigue_study(FatigueStudy.load(args.path),args.out),indent=2))
            else:
                path=args.out if args.fatigue_command=="from-shaft" else args.path
                if path.exists() or path.is_symlink():raise FileExistsError("Fatigue study already exists")
                if args.fatigue_command=="from-shaft":study=fatigue_from_shaft(ShaftStudy.load(args.path))
                elif args.nasa_example:study=nasa_example()
                else:study=fatigue_from_shaft(shaft_from_gear_study(EngineeringStudy()))
                study.save(path);print(path)
            return 0
        if args.command == "contact":
            from .contact import ContactStudy,contact_from_study,synthetic_contact_example,export_contact_study
            from .engineering import EngineeringStudy
            if args.contact_command == "calculate":
                print(json.dumps(export_contact_study(ContactStudy.load(args.path),args.out),indent=2))
            else:
                path=args.out if args.contact_command=="from-study" else args.path
                if path.exists() or path.is_symlink():raise FileExistsError("Contact study already exists")
                if args.contact_command=="from-study":study=contact_from_study(EngineeringStudy.load(args.path))
                elif args.synthetic_example:study=synthetic_contact_example()
                else:study=contact_from_study(EngineeringStudy())
                study.save(path);print(path)
            return 0
        if args.command == "thermal":
            from .thermal import ThermalStudy,thermal_from_study,synthetic_thermal_example,export_thermal_study
            from .engineering import EngineeringStudy
            if args.thermal_command == "calculate":
                print(json.dumps(export_thermal_study(ThermalStudy.load(args.path),args.out),indent=2))
            else:
                path=args.out if args.thermal_command=="from-study" else args.path
                if path.exists() or path.is_symlink():raise FileExistsError("Thermal study already exists")
                if args.thermal_command=="from-study":study=thermal_from_study(EngineeringStudy.load(args.path))
                elif args.synthetic_example:study=synthetic_thermal_example()
                else:study=thermal_from_study(EngineeringStudy())
                study.save(path);print(path)
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
