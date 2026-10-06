from __future__ import annotations

import json
import time
from pathlib import Path


def desktop_smoke(destination: Path, include_cad=False):
    """Exercise the actual desktop/process worker and save diagnostic evidence."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow,STYLE
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError("Diagnostic directory already exists")
    destination.mkdir(parents=True)
    app=QApplication.instance() or QApplication([])
    app.setApplicationName("GearForge Studio");app.setStyleSheet(STYLE)
    window=MainWindow(destination/"diagnostic-data")
    errors=[];window.error=lambda e:errors.append(str(e))
    window.show()
    started=time.monotonic();state={"cad_requested":False,"finished":False}
    timer=QTimer();timer.setInterval(100)
    def finish():
        if state["finished"]:return
        state["finished"]=True
        result={"ok":not errors,"errors":errors,"candidates":len(window.candidates),"cad_meshes":len(window.viewer.meshes),"elapsed_s":round(time.monotonic()-started,3),"simulation_points":len(window.sweep["points"]) if window.selected else 0,"native_platform":"offscreen"}
        if window.selected:result["selected"]=window.selected.id
        (destination/"desktop-smoke.json").write_text(json.dumps(result,indent=2))
        if not errors:
            window.grab().save(str(destination/"desktop.png"))
        window.dirty=False;window.close();timer.stop();app.quit()
    def tick():
        if time.monotonic()-started>120:
            errors.append("Desktop smoke timed out");finish();return
        if errors:finish();return
        if window.process is not None:return
        if not window.candidates:
            errors.append("Search returned no candidates");finish();return
        if include_cad and not state["cad_requested"]:
            state["cad_requested"]=True;window.load_preview();return
        if include_cad and not window.viewer.meshes:
            errors.append("CAD preview returned no meshes");finish();return
        # Verify all four native pages render, then capture the CAD/design workspace.
        for index in range(window.pages.count()):
            window.nav.setCurrentRow(index)
            if window.grab().isNull():errors.append(f"Page {index} did not render")
        window.nav.setCurrentRow(0)
        if include_cad:
            count=len(window.viewer.meshes);window.viewer.step()
            if len(window.viewer.meshes)!=count or window.viewer.phase==0:errors.append("CAD single-step failed")
        window.nav.setCurrentRow(4)
        window.grab().save(str(destination/"simulation.png"))
        window.nav.setCurrentRow(0)
        finish()
    window.generate();timer.timeout.connect(tick);timer.start()
    app.exec()
    print(json.dumps(json.loads((destination/"desktop-smoke.json").read_text()),indent=2))
    return 1 if errors else 0
