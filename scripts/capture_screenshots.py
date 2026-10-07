"""Capture the real desktop app and CAD workers for the README gallery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "screenshots")
    parser.add_argument("--section", choices=("all", "desktop", "studies", "probes"), default="all")
    parser.add_argument("--appearance", choices=("light", "dark"), default="light")
    parser.add_argument("--text-scale", type=float, choices=(1., 1.15, 1.3), default=1.)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["SystemRoot"]) / "Fonts"))

    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from gearforge import __version__
    from gearforge.app import MainWindow

    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("GearForge Studio")
    # Offscreen Qt may otherwise choose a condensed fallback. This only sets the
    # capture session's font; normal application preferences are untouched.
    families = QFontDatabase.families()
    font_family = next((name for name in ("Segoe UI", "DejaVu Sans", "Liberation Sans", "Arial") if name in families), app.font().family())
    QFont.insertSubstitution("sans-serif", font_family)
    QFont.insertSubstitution("system-ui", font_family)
    app.setFont(QFont(font_family, 11))
    captures = []
    errors = []
    with tempfile.TemporaryDirectory(prefix="gearforge-gallery-") as directory:
        settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.IniFormat)
        settings.setValue("appearance", args.appearance)
        settings.setValue("text_scale", args.text_scale)
        settings.setValue("reduced_motion", False)
        settings.sync()
        window = MainWindow(directory)
        window.error = lambda error: errors.append(str(error))
        window.resize(1600, 1080)
        window.show()

        def settle():
            for _ in range(3):
                app.processEvents()
                time.sleep(0.02)

        def wait_for_worker(owner=window, timeout=180):
            deadline = time.monotonic() + timeout
            while getattr(owner, "process", None) is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            if getattr(owner, "process", None) is not None:
                raise RuntimeError("Screenshot worker timed out")
            if errors:
                raise RuntimeError("; ".join(errors))
            settle()

        def save_capture(widget, name, example):
            settle()
            image = widget.grab()
            path = output / (name + ".png")
            if image.isNull() or not image.save(str(path)):
                raise RuntimeError(f"Could not capture {path}")
            captures.append({"file": path.name, "example": "examples/" + example,
                             "width": image.width(), "height": image.height(),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            print(path, flush=True)

        def capture(name, page=0, example="12-to-1-hybrid.gearforge"):
            window.nav.setCurrentRow(page)
            save_capture(window, name, example)

        def load_design(example):
            window.dirty = False
            window.open_project(ROOT / "examples" / example)
            window.nav.setCurrentRow(0)
            window.generate()
            wait_for_worker()
            if not window.selected:
                raise RuntimeError("Screenshot example has no selected design")
            window.load_preview()
            wait_for_worker()
            if not window.viewer.meshes:
                raise RuntimeError("Screenshot example has no CAD meshes")
            window.viewer.zoom = 1.45
            window.viewer.update()

        def capture_studies():
            from gearforge.engineering_ui import EngineeringStudyDialog, EngineeringStudy
            from gearforge.shaft_ui import ShaftStudyDialog, ShaftStudy
            from gearforge.bearing_ui import BearingStudyDialog, BearingStudy
            from gearforge.fatigue_ui import FatigueStudyDialog, FatigueStudy
            from gearforge.contact_ui import ContactStudyDialog, ContactStudy
            from gearforge.thermal_ui import ThermalStudyDialog, ThermalStudy
            from gearforge.tooth_ui import ToothProfileDialog, ToothProfileStudy
            from gearforge.root_ui import RootStressDialog, RootStressStudy
            from gearforge.cyclic_ui import HistoryStudyDialog, HistoryStudy

            studies = (
                ("engineering", EngineeringStudyDialog, EngineeringStudy, "steel-spur-250w.gearforge-study", 0),
                ("shaft", ShaftStudyDialog, ShaftStudy, "steel-spur-input.gearforge-shaft", 4),
                ("bearing", BearingStudyDialog, BearingStudy, "steel-spur-synthetic.gearforge-bearing", 4),
                ("fatigue", FatigueStudyDialog, FatigueStudy, "nasa-shaft-fatigue.gearforge-fatigue", 4),
                ("contact", ContactStudyDialog, ContactStudy, "synthetic-contact.gearforge-contact", 3),
                ("thermal", ThermalStudyDialog, ThermalStudy, "synthetic-thermal.gearforge-thermal", 3),
                ("tooth", ToothProfileDialog, ToothProfileStudy, "synthetic-tooth.gearforge-tooth", 1),
                ("root", RootStressDialog, RootStressStudy, "synthetic-root.gearforge-root", 3),
                ("root-probes", RootStressDialog, RootStressStudy, "synthetic-root-probes.gearforge-root", 7),
                ("history", HistoryStudyDialog, HistoryStudy, "synthetic-history.gearforge-history", 4),
            )
            for name, dialog_type, study_type, example, tab in studies:
                if args.section == "probes" and name != "root-probes":
                    continue
                dialog = dialog_type(window)
                dialog.show_error = lambda error: errors.append(str(error))
                try:
                    dialog.set_study(study_type.load(ROOT / "examples" / example))
                    dialog.show()
                    # Reproducible capture dimensions, independent of the
                    # offscreen platform's synthetic 800-pixel display.
                    dialog.resize(1320, 900)
                    if not dialog.calculate():
                        raise RuntimeError(f"Could not calculate {example}")
                    wait_for_worker(dialog)
                    if not dialog.result:
                        raise RuntimeError(f"No calculation result for {example}")
                    dialog.tabs.setCurrentIndex(tab)
                    if name == "root":
                        dialog.position_selector.setCurrentIndex(1)
                        dialog.view.setCurrentIndex(1)
                    save_capture(dialog, name, example)
                    if name == "history":
                        dialog.plot_mode.setCurrentIndex(1)
                        save_capture(dialog, "history-cycles", example)
                finally:
                    dialog.dirty = False
                    dialog.close()
                    app.processEvents()

        try:
            if args.section in ("all", "desktop"):
                load_design("12-to-1-hybrid.gearforge")
                capture("desktop")
                capture("simulation", 4)
                capture("catalog", 1)
                capture("calibration", 2)
                capture("report", 3)
                window.explode_slider.setValue(35)
                window.viewer.zoom = 1.1
                window.viewer.update()
                capture("exploded")
                window.explode_slider.setValue(0)
                load_design("planetary-example.gearforge")
                capture("planetary", example="planetary-example.gearforge")
                load_design("helical-example.gearforge")
                capture("helical", example="helical-example.gearforge")
            if args.section in ("all", "studies", "probes"):
                capture_studies()
            (output / f"captures-{args.section}.json").write_text(json.dumps({
                "application_version": __version__, "platform": platform.system(),
                "qt_platform": app.platformName(), "font_family": font_family,
                "appearance": args.appearance, "text_scale": args.text_scale,
                "description": "Unmodified captures of the running application using repository examples. Synthetic data are illustrative, not component allowables.",
                "captures": captures,
            }, indent=2) + "\n", encoding="utf-8")
        finally:
            window.dirty = False
            window.close()
            app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
