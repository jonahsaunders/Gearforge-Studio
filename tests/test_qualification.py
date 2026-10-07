import json
from dataclasses import asdict

import pytest

from gearforge.cli import main
from gearforge.engine import synthesize
from gearforge.exporting import export_bundle
from gearforge.models import Project, Requirements
from gearforge.qualification import production_assessment


@pytest.mark.parametrize("family,ratio",[("spur",4),("helical",4),("planetary",4),("bevel",3),("worm",12),("cycloidal",12)])
def test_no_family_can_claim_production_rating(catalog,profile,family,ratio):
    req=Requirements(input_rpm=400,output_rpm=400/ratio,input_torque_nm=.08,
                     output_torque_nm=.04,mode="printed",families=[family])
    profile.test_evidence="approved for production"  # Unverified text is not approval.
    candidate=synthesize(req,profile,catalog,limit=1).candidates[0]
    assessment=production_assessment(candidate,req,profile)
    assert candidate.feasible
    assert assessment["production_approved"] is False
    assert assessment["rated_output_torque_nm"] is None
    assert assessment["rated_life_hours"] is None
    assert not assessment["profile_notes_are_verified_material_data"]
    assert len(assessment["blockers"])>=9


def test_production_export_fails_before_writing(tmp_path,catalog,profile,light_requirements):
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    dest=tmp_path/"production"
    with pytest.raises(ValueError,match="Production export blocked"):
        export_bundle(asdict(c),asdict(light_requirements),asdict(profile),str(dest),require_production=True)
    assert not dest.exists()


def test_qualification_cli_is_actionable_and_fails_closed(tmp_path,light_requirements):
    source=tmp_path/"project.gearforge";out=tmp_path/"assessment.json"
    Project(requirements=light_requirements).save(source)
    assert main(["qualify",str(source),"--out",str(out),"--limit","1"])==2
    assert json.loads(out.read_text())["status"]=="not_qualified"
    assert main(["export",str(source),"--out",str(tmp_path/"production"),"--require-production-rating"])==1
    assert not (tmp_path/"production").exists()
