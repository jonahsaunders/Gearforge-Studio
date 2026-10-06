"""Capture the real desktop app and CAD workers for the README gallery."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "screenshots")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from gearforge.app import MainWindow

    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("GearForge Studio")
    errors = []
    with tempfile.TemporaryDirectory(prefix="gearforge-gallery-") as directory:
        settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.IniFormat)
        settings.setValue("appearance", "light")
        settings.setValue("reduced_motion", False)
        settings.sync()
        window = MainWindow(directory)
        window.error = lambda error: errors.append(str(error))
        window.resize(1500, 1040)
        window.show()

        def settle():
            for _ in range(3):
                app.processEvents()
                time.sleep(0.02)

        def wait_for_worker(timeout=180):
            deadline = time.monotonic() + timeout
            while window.process is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            if window.process is not None:
                raise RuntimeError("Screenshot worker timed out")
            if errors:
                raise RuntimeError("; ".join(errors))
            settle()

        def capture(name, page=0):
            window.nav.setCurrentRow(page)
            settle()
            image = window.grab()
            path = output / (name + ".png")
            if image.isNull() or not image.save(str(path)):
                raise RuntimeError(f"Could not capture {path}")
            print(path, flush=True)

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

        try:
            load_design("12-to-1-hybrid.gearforge")
            capture("desktop")
            capture("simulation", 4)
            capture("catalog", 1)
            capture("calibration", 2)
            capture("report", 3)
            window.explode_slider.setValue(35)
            capture("exploded")
            window.explode_slider.setValue(0)
            load_design("planetary-example.gearforge")
            capture("planetary")
            load_design("helical-example.gearforge")
            capture("helical")
        finally:
            window.dirty = False
            window.close()
            app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
