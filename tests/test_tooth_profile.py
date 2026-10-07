from dataclasses import asdict
import json
import math
from pathlib import Path

import pytest

from gearforge.engineering import EngineeringStudy, pair_geometry
from gearforge.maintenance import verify_bundle
from gearforge.tooth_profile import (ToothProfileStudy,RackProfile,synthetic_profile_example,
    profile_from_study,calculate_profile_study,export_profile_study,profile_report_html,chord_distance)


def test_independent_numerical_cutting_fixture():
    fixture=json.loads((Path(__file__).parent/'data/open_tooth_reference.json').read_text())
    assert fixture['passed'];count=0
    for case in fixture['cases']:
        p=RackProfile(ToothProfileStudy.from_dict(case['study']))
        for angle,radius in zip(case['angles_rad'],case['expected_radii_mm'],strict=True):
            assert p.radius_at_angle(angle)==pytest.approx(radius,rel=2e-9,abs=2e-7);count+=1
    assert count==fixture['comparisons']==266


def test_cutter_dimensions_and_reference_tooth_thickness():
    study=synthetic_profile_example();study.source.pair.pinion_profile_shift=.3
    study.tooth_thickness_reduction_mm=.08;p=RackProfile(study)
    assert p.rf==pytest.approx(20+.6-2.5)
    assert 2*p.R*p.half_pitch==pytest.approx(math.pi+.6*2*math.tan(math.radians(20))-.08)
    assert p.radius_at_angle(0)==p.ra
    assert p.radius_at_angle(math.pi/p.z)==p.rf
    assert p.radius_at_angle(-p.phij)==pytest.approx(p.rj)
    with pytest.raises(ValueError):p.radius_at_angle(float('nan'))


def test_cutter_envelope_has_zero_normal_relative_velocity_and_tangent_joins():
    p=RackProfile(synthetic_profile_example())
    for i in range(101):
        psi=p.alpha+(math.pi/2-p.alpha)*i/100;u,v=p.cutter(psi)
        x,y=p.fillet(psi);w=p.shift+v;theta=(w/math.tan(psi)-u)/p.R
        # Inverse rigid transform recovers the independently specified rack surface.
        qx=x*math.cos(theta)+y*math.sin(theta)-p.R*theta
        qy=-x*math.sin(theta)+y*math.cos(theta)-p.R-p.shift
        assert (qx,qy)==pytest.approx((u,v),abs=1e-12)
        velocity=(-p.shift-v,u+p.R*theta)
        assert velocity[0]*math.cos(psi)+velocity[1]*math.sin(psi)==pytest.approx(0,abs=1e-12)
    def unit(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);return dx/length,dy/length
    eps=1e-7
    first=unit(p.fillet(p.alpha+eps),p.join)
    second=unit(p.join,p.flank(p.rj+eps))
    assert first==pytest.approx(second,abs=2e-6)
    assert math.hypot(*p.fillet(math.pi/2))==pytest.approx(p.rf)
    root=unit(p.fillet(math.pi/2-eps),p.fillet(math.pi/2))
    expected=(math.cos(p.phif),-math.sin(p.phif))
    assert root==pytest.approx(expected,abs=2e-6)


def test_analytic_regularity_positive_shift_negative_D_and_undercut_rejection():
    study=synthetic_profile_example();study.source.pair.pinion_teeth=70;study.source.pair.pinion_profile_shift=.95
    p=RackProfile(study);assert p.D<0 and p.minimum_speed_numerator>0 and p.minimum_polar_factor>0
    radii=[p.radius_at_angle(math.pi/p.z*i/1000) for i in range(1001)]
    assert all(a>=b-1e-10 for a,b in zip(radii,radii[1:]))
    study=synthetic_profile_example();study.source.pair.pinion_teeth=12
    result=calculate_profile_study(study)
    assert not result['profile_available'] and 'undercut' in ' '.join(result['findings'])
    study.source.pair.pinion_profile_shift=.6
    assert calculate_profile_study(study)['profile_available']


@pytest.mark.parametrize('change',[
    lambda s:setattr(s.source.pair,'pinion_helix_angle_deg',10),
    lambda s:setattr(s,'cutter_tip_radius_coefficient',None),
    lambda s:setattr(s,'tooth_thickness_reduction_mm',5),
    lambda s:setattr(s,'cutter_tip_radius_coefficient',1),
    lambda s:setattr(s,'tooth_thickness_reduction_mm',2),
])
def test_unsupported_geometry_produces_no_profile_or_false_rating(change,tmp_path):
    study=synthetic_profile_example();change(study);result=calculate_profile_study(study)
    assert not result['profile_available'] and not result['outline_mm']
    assert not result['production_approved'] and result['rated_output_torque_nm'] is None
    out=tmp_path/'assessment';export_profile_study(study,out)
    assert len(verify_bundle(out)['files'])==3 and not (out/'profile.dxf').exists()


def test_sampling_convergence_circular_pitch_and_closed_outline():
    study=synthetic_profile_example();p=RackProfile(study);segments=p.segments(.005);outline=p.outline(segments)
    assert len(outline)%p.z==0
    # A periodic rotated sector and no zero-length closed edges.
    sector=len(outline)//p.z;angle=-2*math.pi/p.z
    for a,b in zip(outline[:sector],outline[sector:2*sector]):
        assert b==pytest.approx((a[0]*math.cos(angle)-a[1]*math.sin(angle),a[0]*math.sin(angle)+a[1]*math.cos(angle)))
    assert all(math.dist(a,b)>1e-9 for a,b in zip(outline,outline[1:]+outline[:1]))
    for function,start,end,points in [(p.fillet,p.alpha,math.pi/2,segments[2][1]),(p.flank,p.ra,p.rj,segments[1][1])]:
        # Dense verification includes locations other than the adaptive probes.
        error=max(min(chord_distance(function(start+(end-start)*i/2000),a,b) for a,b in zip(points,points[1:])) for i in range(2001))
        assert error < .005
    assert len(p.outline(p.segments(.0005)))>len(outline)


def test_contact_path_uses_actual_involute_start_and_does_not_approve_pair():
    study=synthetic_profile_example();result=calculate_profile_study(study)
    assert result['geometry']['nominal_active_path_above_fillet']
    study.cutter_tip_radius_coefficient=.5
    # Larger radius at this depth can remove the cutter's flat tip entirely.
    assert not calculate_profile_study(study)['profile_available']
    study.cutter_tip_radius_coefficient=.38;study.cutter_depth_coefficient=1.1
    result=calculate_profile_study(study)
    assert result['profile_available'] and not result['geometry']['nominal_active_path_above_fillet']
    assert result['geometry']['root_diameter_difference_from_source_mm']==pytest.approx(.6)
    assert not result['production_approved']


@pytest.mark.parametrize('field,value',[('sampling_tolerance_mm',float('inf')),('cutter_tip_radius_coefficient',True),
    ('cutter_depth_coefficient',0),('role','internal'),('schema_version',True),('data_status','approved')])
def test_strict_inputs(field,value):
    study=synthetic_profile_example();setattr(study,field,value)
    with pytest.raises(ValueError):study.validate()


def test_transfer_keeps_source_and_never_infers_actual_cutter():
    source=EngineeringStudy();source.pair.pinion_profile_shift=.25
    study=profile_from_study(source,'wheel');assert study.source==source and study.source is not source
    assert study.cutter_tip_radius_coefficient is None and study.role=='wheel'
    source.pair.normal_module_mm=4;assert study.source.pair.normal_module_mm==2
    assert not calculate_profile_study(study)['profile_available']


def test_roundtrip_html_and_dxf_integrity_and_recalculation(tmp_path):
    study=synthetic_profile_example();study.name='<script>test</script>';path=tmp_path/'study.gearforge-tooth';study.save(path)
    assert asdict(ToothProfileStudy.load(path))==asdict(study)
    bad=asdict(study);bad['approval']=True
    with pytest.raises(ValueError):ToothProfileStudy.from_dict(bad)
    result=calculate_profile_study(study);assert '<script>' not in profile_report_html(result)
    out=tmp_path/'profile';export_profile_study(study,out);assert len(verify_bundle(out)['files'])==6
    pairs=(out/'profile.dxf').read_text().splitlines();pairs=list(zip(pairs[::2],pairs[1::2],strict=True))
    assert ('9','$INSUNITS') in pairs and ('70','4') in pairs and ('70','1') in pairs
    assert sum(key=='10' for key,value in pairs)==len(result['outline_mm'])
    assert len((out/'profile.csv').read_text().splitlines())==len(result['outline_mm'])+1
    with pytest.raises(FileExistsError):export_profile_study(study,out)
    study.cutter_tip_radius_coefficient=.3
    assert calculate_profile_study(study)['study_sha256']!=result['study_sha256']
    (out/'profile.dxf').write_text('changed')
    with pytest.raises(ValueError):verify_bundle(out)


def test_cli_profile_create_transfer_calculate_verify(tmp_path):
    from gearforge.cli import main
    path=tmp_path/'example.gearforge-tooth';out=tmp_path/'profile'
    assert main(['tooth','new',str(path),'--synthetic-example'])==0
    assert main(['tooth','new',str(path)])==1
    assert main(['tooth','calculate',str(path),'--out',str(out)])==0
    assert main(['verify',str(out)])==0
    source=tmp_path/'source.gearforge-study';EngineeringStudy().save(source);transfer=tmp_path/'transfer.gearforge-tooth'
    assert main(['tooth','from-study',str(source),'--out',str(transfer),'--role','wheel'])==0
    study=ToothProfileStudy.load(transfer);assert study.role=='wheel' and study.cutter_tip_radius_coefficient is None


@pytest.mark.cad
def test_exported_dxf_imports_as_one_valid_closed_solid_in_millimetres(tmp_path):
    import cadquery as cq
    study=synthetic_profile_example();out=tmp_path/'cad-profile';export_profile_study(study,out)
    points=calculate_profile_study(study)['outline_mm']
    area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2
    part=cq.importers.importDXF(str(out/'profile.dxf')).wires().toPending().extrude(20)
    assert len(part.solids().vals())==1 and part.val().isValid()
    assert part.val().Volume()==pytest.approx(area*20,rel=1e-8)


@pytest.mark.gui
def test_editor_roundtrip_invalidation_views_and_save_failure(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.tooth_ui import ToothProfileDialog
    app=QApplication.instance() or QApplication([]);study=synthetic_profile_example();study.tooth_thickness_reduction_mm=.123456789012345
    dialog=ToothProfileDialog(study=study);errors=[];dialog.show_error=lambda e:errors.append(str(e))
    dialog.show();app.processEvents();assert asdict(dialog.read_study())==asdict(study)
    assert dialog.calculate() and dialog.result['profile_available']
    assert dialog.tabs.count()==4
    for index in range(4):dialog.tabs.setCurrentIndex(index);app.processEvents();assert not dialog.grab().isNull()
    for view in range(2):dialog.view.setCurrentIndex(view);app.processEvents();assert not dialog.plot.grab().isNull()
    field=dialog.fields['cutter_tip_radius_coefficient'];field.setText('invalid')
    assert dialog.dirty and dialog.result is None and dialog.plot.result is None
    assert not dialog.calculate() and field.text()=='invalid'
    field.setText('');assert dialog.calculate() and not dialog.result['profile_available']
    field.setText('.38');old=tmp_path/'old.gearforge-tooth';dialog.path=old
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-tooth'),''))
    def fail(*a):raise OSError('Disk full')
    monkeypatch.setattr(ToothProfileStudy,'save',fail)
    assert not dialog.save_study() and dialog.path==old and dialog.dirty and errors[-1]=='Disk full'
    dialog.dirty=False;dialog.close();app.processEvents()
