"""Archive the target-native build and emit SHA256; never upload anything."""
from pathlib import Path
import argparse
import os
import hashlib
import platform
import subprocess
import tarfile
import tomllib
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--smoke",action="store_true");args=parser.parse_args()
    version=tomllib.loads((ROOT/"pyproject.toml").read_text())["project"]["version"]
    system=platform.system().lower();arch=platform.machine().lower().replace("amd64","x86_64").replace("aarch64","arm64")
    folder=ROOT/"dist"/("GearForgeStudio.app" if system=="darwin" else "GearForgeStudio")
    executable=folder/"Contents/MacOS/GearForgeStudio" if system=="darwin" else folder/("GearForgeStudio.exe" if system=="windows" else "GearForgeStudio")
    if not executable.is_file():raise FileNotFoundError(executable)
    if args.smoke:
        destination=ROOT/"build"/"frozen-smoke"
        if destination.exists():
            if destination.resolve().parent != (ROOT/"build").resolve():raise ValueError("Unsafe smoke output path")
            import shutil;shutil.rmtree(destination)
        diagnostic_executable=folder/"GearForgeCLI.exe" if system=="windows" else executable
        environment=os.environ.copy()
        if system=="windows" and environment.get("QT_QPA_PLATFORM")=="offscreen":
            environment.setdefault("QT_QPA_FONTDIR",str(Path(os.environ["SystemRoot"])/"Fonts"))
        process=subprocess.run([str(diagnostic_executable),"smoke","--out",str(destination),"--cad"],capture_output=True,text=True,timeout=180,env=environment)
        (ROOT/"build"/"frozen-smoke.log").write_text(process.stdout+process.stderr,encoding="utf-8")
        if process.returncode:
            raise RuntimeError("Native smoke failed: "+process.stderr[-4000:])
        # Exercise the windowed desktop entry point's file-based worker as well.
        if system=="windows":
            import json
            from dataclasses import asdict
            from gearforge.models import Project
            from gearforge.catalog import Catalog
            project=Project();catalog=Catalog()
            request=ROOT/"build"/"desktop-worker-request.json"
            result=ROOT/"build"/"desktop-worker-result.json"
            result.unlink(missing_ok=True)
            request.write_text(json.dumps(dict(task="search",result_path=str(result),
                requirements=asdict(project.requirements),profile=asdict(project.profile),
                catalog_text=catalog.export_csv(),limit=1)),encoding="utf-8")
            catalog.close()
            subprocess.run([str(executable),"--worker-file",str(request)],check=True,timeout=60)
            if not json.loads(result.read_text(encoding="utf-8"))["ok"]:raise RuntimeError("Windowed worker failed")
        import json
        evidence=json.loads((destination/"desktop-smoke.json").read_text())
        if not evidence["ok"] or evidence["simulation_points"]!=25:raise RuntimeError(evidence)
        study=evidence.get("engineering_study") or {}
        if study.get("app_version")!=version or study.get("tabs_rendered")!=4 or study.get("verified_files")!=3:
            raise RuntimeError("Native engineering study smoke failed: "+str(study))
        shaft=evidence.get("shaft_study") or {}
        if shaft.get("app_version")!=version or shaft.get("tabs_rendered")!=6 or shaft.get("verified_files")!=3:
            raise RuntimeError("Native shaft study smoke failed: "+str(shaft))
        bearing=evidence.get("bearing_study") or {}
        if bearing.get("app_version")!=version or bearing.get("tabs_rendered")!=5 or bearing.get("verified_files")!=3:
            raise RuntimeError("Native bearing study smoke failed: "+str(bearing))
        fatigue=evidence.get("fatigue_study") or {}
        if fatigue.get("app_version")!=version or fatigue.get("tabs_rendered")!=5 or fatigue.get("verified_files")!=3:
            raise RuntimeError("Native fatigue study smoke failed: "+str(fatigue))
        contact=evidence.get("contact_study") or {}
        if contact.get("app_version")!=version or contact.get("tabs_rendered")!=6 or contact.get("diagrams_rendered")!=4 or contact.get("verified_files")!=3:
            raise RuntimeError("Native contact study smoke failed: "+str(contact))
        thermal=evidence.get("thermal_study") or {}
        if thermal.get("app_version")!=version or thermal.get("tabs_rendered")!=6 or thermal.get("diagrams_rendered")!=12 or thermal.get("verified_files")!=3:
            raise RuntimeError("Native thermal study smoke failed: "+str(thermal))
        tooth=evidence.get("tooth_profile") or {}
        if tooth.get("app_version")!=version or tooth.get("tabs_rendered")!=4 or tooth.get("diagrams_rendered")!=2 or tooth.get("verified_files")!=6:
            raise RuntimeError("Native tooth profile smoke failed: "+str(tooth))
        root=evidence.get("root_stress") or {}
        if root.get('app_version')!=version or root.get('tabs_rendered')!=7 or root.get('diagrams_rendered')!=7 or root.get('verified_files')!=6 or not root.get('calculation_and_export_workers') or not root.get('mesh_convergence_passed') or not root.get('domain_sensitivity_passed'):
            raise RuntimeError('Native root stress smoke failed: '+str(root))
        history=evidence.get('stress_history') or {}
        if history.get('app_version')!=version or history.get('tabs_rendered')!=7 or history.get('diagrams_rendered')!=3 or history.get('verified_files')!=5 or not history.get('calculation_and_export_workers') or history.get('production_approved') is not False:
            raise RuntimeError('Native stress history smoke failed: '+str(history))
    output=ROOT/"release-assets";output.mkdir(exist_ok=True)
    if system!="darwin":
        platform_note=("Use GearForgeCLI.exe for console commands and diagnostics.\n" if system=="windows"
                       else "Linux target: x86_64, Ubuntu 24.04 class / glibc 2.39+.\n")
        (folder/"START_HERE.txt").write_text("GearForge Studio "+version+" — unsigned release candidate\n\nLaunch GearForgeStudio"+(".exe" if system=="windows" else "")+" in this folder. Keep _internal alongside it.\n"+platform_note+"Use Help > About and Help > Open third-party license notices.\nSimulations are kinematic and quasi-static; no verified production load rating.\n",encoding="utf-8")
    stem=f"GearForge-Studio-{version}-{system}-{arch}-unsigned"
    if system=="linux":
        path=output/(stem+".tar.gz")
        with tarfile.open(path,"w:gz") as archive:archive.add(folder,arcname=folder.name)
    elif system=="darwin":
        path=output/(stem+".zip")
        subprocess.run(["ditto","-c","-k","--sequesterRsrc","--keepParent",str(folder),str(path)],check=True)
    else:
        path=output/(stem+".zip")
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(folder.rglob("*")):
                if file.is_file():archive.write(file,file.relative_to(folder.parent))
    digest=hashlib.file_digest(path.open("rb"),"sha256").hexdigest()
    path.with_name(path.name+".sha256").write_text(f"{digest}  {path.name}\n")
    print(path)


if __name__=="__main__":main()
