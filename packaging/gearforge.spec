# Build on the target OS with: python -m PyInstaller packaging/gearforge.spec
from pathlib import Path
import sys
import tomllib
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

project = Path(SPECPATH).parent
configuration=tomllib.loads((project/"pyproject.toml").read_text())
version=configuration["project"]["version"]
macos_build=configuration["tool"]["gearforge"]["release"]["macos-build"]
icon=str(project/"src/gearforge/data/icon.png")
datas = collect_data_files("gearforge")
for distribution in ("PySide6-Essentials", "shiboken6", "reportlab", "cadquery", "cadquery-ocp", "numpy", "vtk", "casadi", "nlopt", "ezdxf"):
    datas += copy_metadata(distribution)
license_dir = project / "release-licenses"
if license_dir.exists():
    datas.append((str(license_dir), "licenses"))
for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "docs/RELEASE_STATUS.md", "docs/INTERNAL_DEPLOYMENT.md", "docs/PRODUCTION_QUALIFICATION.md", "docs/OPEN_ENGINEERING.md", "docs/SHAFT_ANALYSIS.md", "docs/BEARING_ANALYSIS.md"):
    datas.append((str(project / name), "documentation"))
binaries = collect_dynamic_libs("OCP")
a = Analysis([str(project / "packaging/entry.py")],
    pathex=[str(project / "src")], binaries=binaries, datas=datas,
    hiddenimports=collect_submodules("gearforge")+["casadi._casadi"],
    excludes=["torch", "tensorflow", "pandas", "matplotlib", "IPython", "notebook", "jupyter", "cv2"],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GearForgeStudio", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=sys.platform not in ("darwin","win32"),
    icon=icon, argv_emulation=False)
executables = [exe]
if sys.platform == "win32":
    # IT automation needs visible diagnostics and reliable console exit codes.
    cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GearForgeCLI",
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
        console=True, icon=icon)
    executables.append(cli)
coll = COLLECT(*executables, a.binaries, a.datas, strip=False, upx=False, name="GearForgeStudio")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="GearForgeStudio.app", icon=icon,
        bundle_identifier="org.gearforge.studio",
        info_plist={"CFBundleName":"GearForge Studio","CFBundleDisplayName":"GearForge Studio",
            "CFBundleShortVersionString":version.split("rc")[0],"CFBundleVersion":macos_build,
            "NSHighResolutionCapable":True,"LSMinimumSystemVersion":"14.0",
            "NSHumanReadableCopyright":"GearForge Studio contributors. Apache-2.0.",
            "CFBundleDocumentTypes":[{"CFBundleTypeName":"GearForge project","CFBundleTypeRole":"Editor",
                "LSHandlerRank":"Owner","CFBundleTypeExtensions":["gearforge"],
                "LSItemContentTypes":["org.gearforge.project"]}],
            "UTExportedTypeDeclarations":[{"UTTypeIdentifier":"org.gearforge.project","UTTypeDescription":"GearForge gearbox project",
                "UTTypeConformsTo":["public.json"],"UTTypeTagSpecification":{"public.filename-extension":["gearforge"]}}]})
