import copy
import math
from dataclasses import asdict

import pytest
from gearforge.engine import synthesize,external_contact_ratio
from gearforge.models import GearSpec,Requirements,PrintProfile


def test_default_two_stage_load_and_energy(catalog,profile):
    req=Requirements()
    result=synthesize(req,profile,catalog)
    assert result.candidates and result.evaluated>1000
    for c in result.candidates:
        assert c.feasible
        assert abs(c.ratio/req.ratio-1)*100<=req.ratio_tolerance_percent+1e-9
        assert c.available_output_nm>=req.output_torque_nm
        assert req.input_rpm*req.available_torque*c.efficiency==pytest.approx(c.output_rpm*c.available_output_nm)
        assert c.stages[-1].output_torque_nm==pytest.approx(req.output_torque_nm)
        assert all(s.input_rpm>0 and s.input_torque_nm>0 for s in c.stages)
        assert c.estimated_cost is None
        assert any(k.status=="warn" for k in c.checks)


@pytest.mark.parametrize("family,ratio",[("spur",4),("helical",4),("planetary",4),("bevel",3),("worm",12),("cycloidal",12)])
def test_all_family_searches(catalog,profile,family,ratio):
    req=Requirements(input_rpm=400,output_rpm=400/ratio,input_torque_nm=.08,output_torque_nm=.04,mode="printed",families=[family])
    result=synthesize(req,profile,catalog)
    assert result.candidates
    assert all(c.family==family for c in result.candidates)
    assert all(c.export_level==("concept" if family in ("bevel","worm","cycloidal") else "prototype") for c in result.candidates)


def test_planetary_tooth_and_phase_constraints(catalog,profile):
    req=Requirements(input_rpm=400,output_rpm=100,input_torque_nm=.08,output_torque_nm=.04,mode="printed",families=["planetary"])
    for c in synthesize(req,profile,catalog).candidates:
        s=c.stages[0]
        assert s.driven.teeth==s.driver.teeth+2*s.planet.teeth
        assert (s.driver.teeth+s.driven.teeth)%s.planet_count==0
        assert c.ratio==pytest.approx(1+s.driven.teeth/s.driver.teeth)
        assert math.sqrt(3)*s.center_mm>s.planet.outer_mm+1


def test_commercial_preserves_catalog_bores(catalog,profile):
    req=Requirements(input_rpm=400,output_rpm=100,input_torque_nm=.08,output_torque_nm=.025,mode="commercial",families=["spur"])
    result=synthesize(req,profile,catalog)
    assert result.candidates
    stock={g.sku:g for g in catalog.gears()}
    for c in result.candidates:
        for s in c.stages:
            for g in (s.driver,s.driven):
                assert g.source=="catalog"
                assert g.bore_mm==stock[g.sku].bore_mm
        for a,b in zip(c.stages,c.stages[1:]):assert a.driven.bore_mm==b.driver.bore_mm


def test_infeasible_load_diagnostics(catalog,profile):
    req=Requirements(output_torque_nm=100)
    result=synthesize(req,profile,catalog)
    assert not result.candidates
    assert result.rejected["Available output torque"]>0


def test_repeatable_ids_and_ranking(catalog,profile,light_requirements):
    a=synthesize(light_requirements,profile,catalog,limit=8)
    b=synthesize(light_requirements,profile,catalog,limit=8)
    assert [c.id for c in a.candidates]==[c.id for c in b.candidates]
    profile.backlash_mm=.25
    assert [c.id for c in synthesize(light_requirements,profile,catalog,limit=8).candidates]!=[c.id for c in a.candidates]


def test_motor_curve_interpolation_and_domain():
    req=Requirements(input_rpm=1000,motor_curve=[[500,.15],[1500,.05]])
    req.validate()
    assert req.available_torque==pytest.approx(.1)
    req.input_rpm=1600
    with pytest.raises(ValueError,match="outside"):req.validate()


@pytest.mark.parametrize("field,value",[("input_rpm",float("nan")),("output_rpm",0),("safety_factor",.5),("max_stages",True),("families",["unknown"]),("input_torque_nm",True)])
def test_invalid_constraints(field,value):
    req=Requirements();setattr(req,field,value)
    with pytest.raises(ValueError):req.validate()


def test_contact_ratio_known_pair():
    a,b=GearSpec(20,1,10,8),GearSpec(40,1,10,10)
    assert 1.6<external_contact_ratio(a,b)<1.7


def test_cancellation(catalog,profile,light_requirements):
    with pytest.raises(InterruptedError):synthesize(light_requirements,profile,catalog,cancel=lambda:True)
