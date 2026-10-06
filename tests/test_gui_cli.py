import json
import os
import subprocess
import sys
import time
from dataclasses import asdict

import pytest

from gearforge.cli import main
from gearforge.models import Project


def test_cli_project_and_search(tmp_path):
    project=tmp_path/"new.gearforge"
    assert main(["new",str(project)])==0
    result=tmp_path/"result.json"
    assert main(["search",str(project),"--out",str(result),"--limit","4"])==0
    assert len(json.loads(result.read_text())["candidates"])==4
    assert main(["new",str(project)])==1


def test_worker_protocol(tmp_path):
    p=Project();from gearforge.catalog import Catalog
    catalog=Catalog();text=catalog.export_csv();catalog.close()
    result=tmp_path/"worker.json"
    payload=dict(task="search",result_path=str(result),requirements=asdict(p.requirements),profile=asdict(p.profile),catalog_text=text,limit=2)
    process=subprocess.run([sys.executable,"-m","gearforge.cli","--worker"],input=json.dumps(payload),text=True,capture_output=True,timeout=30)
    assert process.returncode==0,process.stderr
    response=json.loads(result.read_text());assert response["ok"] and len(response["result"]["candidates"])==2


@pytest.mark.gui
def test_desktop_worker_and_stale_design_guard(tmp_path):
    from PySide6.QtWidgets import QApplication
    from gearforge.app import MainWindow,STYLE
    app=QApplication.instance() or QApplication([]);app.setStyleSheet(STYLE)
    w=MainWindow(tmp_path);errors=[];w.error=lambda e:errors.append(str(e));w.show()
    w.generate();deadline=time.monotonic()+30
    while w.process is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.02)
    assert not errors,errors
    assert w.selected and w.candidates
    assert w.ready_payload()["candidate"]["id"]==w.selected.id
    w.fields["output_rpm"].setValue(110)
    with pytest.raises(ValueError,match="Regenerate"):w.ready_payload()
    mesh=dict(name="test",vertices=[[0,0,0],[1,0,0],[0,1,0]],triangles=[[0,1,2]],center=[0,0,0],shaft=0,source="print",color=[.1,.5,.9])
    w.apply_preview(dict(candidate_id=w.selected.id,meshes=[mesh]))
    assert not w.viewer.meshes
    w.apply_mesh_check(dict(candidate_id=w.selected.id,status="No interference at sampled poses",maximum_overlap_mm3=0,samples=12))
    assert w.mesh_result is None
    w.dirty=False;w.close();app.processEvents()


@pytest.mark.gui
def test_all_desktop_pages_render(tmp_path):
    from PySide6.QtWidgets import QApplication
    from gearforge.app import MainWindow
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path);w.error=lambda e:None;w.show();app.processEvents()
    for i in range(w.pages.count()):
        w.nav.setCurrentRow(i);app.processEvents()
        assert not w.grab().isNull()
    assert len(w.catalog_rows)>=6
    w.dirty=False;w.close();app.processEvents()


@pytest.mark.gui
def test_cancelled_recovery_and_failed_save_as_keep_current_document(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.app import MainWindow
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path/"data");errors=[];w.error=lambda e:errors.append(str(e))
    original=tmp_path/"original.gearforge";Project(name="Original").save(original)
    assert w.open_project(original)
    Project(name="Recovery").save(w.data_dir/"recovery.gearforge")
    w.dirty=True;w.may_discard=lambda:False
    w.restore_recovery()
    assert w.path==original and w.project.name=="Original" and w.dirty
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *a:(str(tmp_path/"new.gearforge"),""))
    def fail_save(*a):raise OSError("Disk full")
    monkeypatch.setattr(Project,"save",fail_save)
    assert not w.save_project(True)
    assert w.path==original and w.dirty and errors==["Disk full"]
    w.may_discard=lambda:True;w.close();app.processEvents()


@pytest.mark.gui
def test_catalog_change_during_search_rejects_result(tmp_path):
    from PySide6.QtWidgets import QApplication
    from gearforge.app import MainWindow
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path);w.search_snapshot=w.capture()
    w.search_catalog_text=w.catalog.export_csv()
    w.catalog.import_csv(w.search_catalog_text.replace("SS1-20","COMPANY-PART"))
    w.apply_result({})
    assert not w.candidates and w.result_snapshot is None
    assert "Catalog changed" in w.notice.text()
    w.dirty=False;w.close();app.processEvents()


def test_cli_malformed_project_returns_error_without_traceback(tmp_path,capsys):
    path=tmp_path/"bad.gearforge";path.write_text('{"schema_version":1}')
    assert main(["search",str(path),"--out",str(tmp_path/"out.json")])==1
    assert "must be an object" in capsys.readouterr().err
