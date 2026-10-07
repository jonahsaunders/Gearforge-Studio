import json
from dataclasses import asdict

import pytest

from gearforge.catalog import Catalog
from gearforge.cli import main
from gearforge.engine import synthesize
from gearforge.exporting import export_bundle
from gearforge.maintenance import backup_data, restore_data, verify_bundle, lock_data_directory
from gearforge.models import Project, Requirements


def test_backup_restore_preserves_catalog_profiles_and_recovery(tmp_path):
    source=tmp_path/"source";source.mkdir()
    catalog=Catalog(source/"catalog.sqlite")
    profile=Project().profile;profile.name="Company material"
    catalog.save_profile(profile)
    original=catalog.export_csv();catalog.close()
    Project(name="Unfinished design").save(source/"recovery.gearforge")
    (source/"settings.ini").write_text("[General]\nreduced_motion=true\n")
    (source/"gearforge.log").write_text("Not part of a backup")
    backup=tmp_path/"backup";restored=tmp_path/"restored"
    assert main(["backup","--data-dir",str(source),"--out",str(backup)])==0
    assert main(["verify",str(backup)])==0
    assert main(["restore",str(backup),"--data-dir",str(restored)])==0
    recovered=Catalog(restored/"catalog.sqlite")
    assert recovered.export_csv()==original
    assert recovered.profiles()[0].name==profile.name
    recovered.close()
    assert Project.load(restored/"recovery.gearforge").name=="Unfinished design"
    assert (restored/"settings.ini").read_bytes()==(source/"settings.ini").read_bytes()
    assert not (backup/"gearforge.log").exists()
    with pytest.raises(FileExistsError):restore_data(backup,restored)
    with pytest.raises(FileExistsError):backup_data(source,backup)


def test_backup_refuses_active_data_directory(tmp_path):
    catalog=Catalog(tmp_path/"catalog.sqlite");catalog.close()
    lock=lock_data_directory(tmp_path)
    try:
        with pytest.raises(RuntimeError,match="already in use"):
            backup_data(tmp_path,tmp_path.parent/(tmp_path.name+"-backup"))
        with pytest.raises(RuntimeError):lock_data_directory(tmp_path)
    finally:lock.unlock()


@pytest.fixture
def backup(tmp_path):
    source=tmp_path/"source";source.mkdir()
    catalog=Catalog(source/"catalog.sqlite");catalog.close()
    dest=tmp_path/"backup";backup_data(source,dest)
    return dest


@pytest.mark.parametrize("change",["modify","delete","extra","traversal"])
def test_verify_rejects_tampering_and_restore_is_not_published(backup,tmp_path,change):
    if change=="modify":(backup/"catalog.sqlite").write_bytes(b"tampered")
    elif change=="delete":(backup/"catalog.sqlite").unlink()
    elif change=="extra":(backup/"unexpected.txt").write_text("extra")
    else:
        manifest=json.loads((backup/"manifest.json").read_text())
        manifest["files"]={"../outside":"0"*64}
        (backup/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):verify_bundle(backup)
    with pytest.raises(ValueError):restore_data(backup,tmp_path/"restored")
    assert not (tmp_path/"restored").exists()


def test_export_preserves_inputs_catalog_and_project_metadata(tmp_path,catalog,profile):
    req=Requirements(input_rpm=400,output_rpm=400/12,input_torque_nm=.08,
                     output_torque_nm=.04,mode="printed",families=["worm"])
    c=synthesize(req,profile,catalog,limit=1).candidates[0]
    project=Project(name="Company pilot",notes="Review ticket ENG-42",requirements=req,profile=profile)
    destination=tmp_path/"export"
    export_bundle(asdict(c),asdict(req),asdict(profile),str(destination),False,
                  asdict(project),catalog.export_csv())
    manifest=verify_bundle(destination)
    assert manifest["kind"]=="gearforge-design-export"
    loaded=Project.load(destination/"design.gearforge")
    assert loaded.name==project.name and loaded.notes==project.notes
    assert loaded.selected_id==c.id
    assert (destination/"catalog.csv").read_text(encoding="utf-8")==catalog.export_csv().replace("\r\n","\n")
    evidence=json.loads((destination/"provenance.json").read_text(encoding="utf-8"))
    assert evidence["requirements"]==asdict(req)
    assert evidence["catalog_snapshot_included"]
    assert "cadquery" in evidence["dependencies"]
