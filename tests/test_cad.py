import json
import math
from dataclasses import asdict

import pytest

from gearforge.calibration import export_coupon
from gearforge.engine import synthesize
from gearforge.exporting import export_bundle,report_html
from gearforge.geometry import build_parts,collision_report,gear_solid
from gearforge.models import Requirements,GearSpec,PrintProfile


@pytest.mark.cad
@pytest.mark.parametrize("family",["spur","helical","planetary"])
def test_prototype_solids_and_interference(catalog,profile,light_requirements,family):
    light_requirements.families=[family]
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    parts=build_parts(c,light_requirements,profile)
    assert len(parts)>=10
    assert all(p.shape.val().isValid() and p.shape.val().Volume()>0 for p in parts)
    unexpected=[r for r in collision_report(parts) if r["status"]=="interference"]
    assert not unexpected,unexpected


@pytest.mark.cad
def test_full_bundle_real_roundtrip(tmp_path,catalog,profile,light_requirements):
    import cadquery as cq
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    dest=tmp_path/"bundle"
    result=export_bundle(asdict(c),asdict(light_requirements),asdict(profile),str(dest))
    assert result["cad_included"]
    assembly=cq.importers.importStep(str(dest/"assembly.step"))
    assert assembly.val().isValid()
    assert list((dest/"print").glob("*.stl")) and list((dest/"print").glob("*.3mf"))
    assert (dest/"report.pdf").read_bytes().startswith(b"%PDF")
    manifest=json.loads((dest/"manifest.json").read_text())
    import hashlib
    for path,digest in manifest["files"].items():assert hashlib.sha256((dest/path).read_bytes()).hexdigest()==digest
    with pytest.raises(FileExistsError):export_bundle(asdict(c),asdict(light_requirements),asdict(profile),str(dest))


def test_concepts_never_export_fake_manufacturing_teeth(tmp_path,catalog,profile):
    req=Requirements(input_rpm=400,output_rpm=400/12,input_torque_nm=.08,output_torque_nm=.04,mode="printed",families=["worm"])
    c=synthesize(req,profile,catalog,limit=1).candidates[0]
    with pytest.raises(ValueError,match="concept-only"):build_parts(c,req,profile)
    result=export_bundle(asdict(c),asdict(req),asdict(profile),str(tmp_path/"concept"))
    assert not result["cad_included"] and not (tmp_path/"concept"/"assembly.step").exists()


@pytest.mark.cad
def test_calibration_coupon_solid(tmp_path):
    import cadquery as cq
    path=tmp_path/"coupon.step";export_coupon(path)
    shape=cq.importers.importStep(str(path)).val()
    assert shape.isValid()
    assert shape.Volume()==pytest.approx((40*40-math.pi*5**2)*6,rel=1e-4)


def test_report_escapes_user_content(catalog,profile,light_requirements):
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    profile.test_evidence='<script>alert(1)</script>'
    text=report_html(c,light_requirements,profile)
    assert '<script>' not in text and '&lt;script&gt;' in text
