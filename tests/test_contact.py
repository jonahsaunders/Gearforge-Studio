from dataclasses import asdict,replace
import json
import math
from pathlib import Path

import pytest

from gearforge.contact import (ContactStudy,ContactMaterial,ContactLifePoint,contact_from_study,
    synthetic_contact_example,calculate_contact_study,hertz_line,contact_life,contact_report_html,export_contact_study)
from gearforge.engineering import EngineeringStudy,DutyPoint,GearPair
from gearforge.maintenance import verify_bundle


def duty_study(cases):
    study=synthetic_contact_example();study.source.duty=cases
    study.source.target_life_hours=math.fsum(c.duration_hours for c in cases)
    study.cases=[replace(study.cases[0],case_name=c.name) for c in cases]
    return study


def test_independent_slippy_reference_fixture():
    fixture=json.loads((Path(__file__).parent/'data/open_contact_reference.json').read_text(encoding='utf-8'))
    assert fixture['reference_commit']=='a4fbb447fc494d0480661ee41ef15fdc82e7423c'
    assert fixture['passed'] and fixture['comparisons']==208
    for case in fixture['cylinder_cases']:
        actual=hertz_line(*case['inputs'])
        for key,value in case['expected'].items():assert actual[key]==pytest.approx(value,rel=1e-10,abs=1e-12)
    for case in fixture['gear_studies']:
        profile=calculate_contact_study(ContactStudy.from_dict(case['study']))['cases'][0]['profile']
        for row in case['expected']:
            for key,value in row['values'].items():assert profile[row['profile_index']][key]==pytest.approx(value,rel=1e-10,abs=1e-12)


def test_hertz_force_width_convention_symmetry_and_scaling():
    result=hertz_line(5,20,40,210000,70000,.3,.33)
    # Integrate semicircular pressure using a cosine coordinate; catches half-
    # width/full-width and peak/mean pressure convention mistakes.
    count=1000;step=math.pi/count
    integral=result['half_width_mm']*result['peak_pressure_mpa']*step*math.fsum(
        math.cos(-math.pi/2+i*step)**2 for i in range(1,count))
    assert integral==pytest.approx(40,rel=1e-10)
    swapped=hertz_line(20,5,40,70000,210000,.33,.3)
    assert result==pytest.approx(swapped)
    scaled=hertz_line(5,20,160,210000,70000,.3,.33)
    assert scaled['peak_pressure_mpa']==pytest.approx(2*result['peak_pressure_mpa'])
    assert scaled['half_width_mm']==pytest.approx(2*result['half_width_mm'])
    zero=hertz_line(5,20,0,210000,70000,.3,.33)
    assert zero['half_width_mm']==zero['peak_pressure_mpa']==0


@pytest.mark.parametrize('index,value',[(0,0),(1,-1),(2,-1),(3,float('inf')),(4,True),(5,-.1),(6,.5)])
def test_invalid_hertz_inputs_rejected(index,value):
    inputs=[5,20,40,210000,70000,.3,.33];inputs[index]=value
    with pytest.raises(ValueError):hertz_line(*inputs)


def test_spur_curvature_against_involute_parametric_derivatives():
    result=calculate_contact_study(synthetic_contact_example());g=result['geometry']
    tangent=g['operating_center_distance_mm']*math.sin(math.radians(g['operating_pressure_angle_deg']))
    for row in result['cases'][0]['profile'][::17]:
        assert row['pinion_curvature_mm']+row['wheel_curvature_mm']==pytest.approx(tangent)
        for role in ('pinion','wheel'):
            rb=g[role]['base_diameter_mm']/2;t=row[f'{role}_curvature_mm']/rb
            # For x=rb(cos(t)+t sin(t)), y=rb(sin(t)-t cos(t)),
            # rho=|r'|³ / |x'y''-y'x''|, computed from independent derivatives.
            dx,dy=rb*t*math.cos(t),rb*t*math.sin(t)
            ddx,ddy=rb*(math.cos(t)-t*math.sin(t)),rb*(math.sin(t)+t*math.cos(t))
            curvature_radius=math.hypot(dx,dy)**3/abs(dx*ddy-dy*ddx)
            assert row[f'{role}_curvature_mm']==pytest.approx(curvature_radius,rel=1e-12)


def test_equal_pair_sharing_closes_mesh_force_and_keeps_jump_limits():
    study=synthetic_contact_example();study.load_sharing='equal_pairs';result=calculate_contact_study(study)
    path=result['contact_path'];pitch=result['geometry']['transverse_base_pitch_mm'];length=path['length_mm']
    for interval in path['intervals']:
        position=(interval['start_mm']+interval['end_mm'])/2
        visible=[position+i*pitch for i in range(-5,6) if 0<position+i*pitch<length]
        assert len(visible)==interval['simultaneous_pairs']
        assert interval['pair_load_fraction']*len(visible)==pytest.approx(1)
    grouped={}
    for row in result['cases'][0]['profile']:
        if row['side'] in ('left','right'):grouped.setdefault(row['path_mm'],[]).append(row)
    jumps=[v for v in grouped.values() if len(v)==2]
    assert len(jumps)==2
    for a,b in jumps:
        assert a['effective_radius_mm']==pytest.approx(b['effective_radius_mm'])
        assert a['peak_pressure_mpa']/b['peak_pressure_mpa']==pytest.approx(math.sqrt(a['pair_load_fraction']/b['pair_load_fraction']))


def test_high_contact_ratio_has_two_and_three_pair_intervals():
    study=synthetic_contact_example();study.load_sharing='equal_pairs'
    study.source.pair=GearPair(pinion_teeth=100,wheel_teeth=200,normal_pressure_angle_deg=15)
    result=calculate_contact_study(study)
    assert not result['geometry_findings']
    assert {i['simultaneous_pairs'] for i in result['contact_path']['intervals']}=={2,3}


def test_exact_peak_bounds_dense_interior_and_pitch_sliding_is_zero():
    for sharing in ('full_load_envelope','equal_pairs'):
        study=synthetic_contact_example();study.load_sharing=sharing;result=calculate_contact_study(study)
        row=result['cases'][0];critical=[p for p in row['profile'] if p['critical']]
        assert row['worst_contact']['side'] in ('left','right')
        assert row['peak_hertz_pressure_mpa']==max(p['peak_pressure_mpa'] for p in critical)
        # A dense independent line-of-action evaluation cannot exceed the exact
        # endpoint result, including the one-sided pair-count jumps.
        first=row['profile'][0]['pinion_curvature_mm'];total=first+row['profile'][0]['wheel_curvature_mm']
        for interval in result['contact_path']['intervals']:
            for i in range(1,1000):
                x=first+interval['start_mm']+(interval['end_mm']-interval['start_mm'])*i/1000
                reduced=x*(total-x)/total
                pressure=math.sqrt(row['normal_mesh_force_n']/20*interval['pair_load_fraction']*(210000/(2*(1-.3**2)))/(math.pi*reduced))
                assert pressure<=row['peak_hertz_pressure_mpa']*(1+1e-12)
        pitch=next(p for p in row['profile'] if abs(p['relative_to_pitch_mm'])<1e-12)
        assert pitch['sliding_speed_m_s']==pytest.approx(0,abs=1e-12)
        assert pitch['slide_roll_ratio']==pytest.approx(0,abs=1e-12)


def test_pressure_life_interpolation_endpoints_and_no_extrapolation():
    curve=[ContactLifePoint(1e3,1000),ContactLifePoint(1e9,100)]
    assert contact_life(curve,math.sqrt(1000*100))['cycles_to_failure']==pytest.approx(1e6)
    assert contact_life(curve,1000)['cycles_to_failure']==pytest.approx(1e3)
    assert contact_life(curve,100)['cycles_to_failure']==pytest.approx(1e9)
    for value,state in ((1001,'above_curve_pressure'),(99,'below_curve_pressure'),(0,'zero_pressure')):
        result=contact_life(curve,value);assert result['cycles_to_failure'] is None and result['state']==state


def test_cycles_are_per_tooth_not_mesh_frequency_or_profile_sample_count():
    result=calculate_contact_study(synthetic_contact_example());case=result['cases'][0]
    pinion,wheel=case['members']
    assert pinion['tooth_contact_cycles']==900000000
    assert wheel['tooth_contact_cycles']==180000000
    assert pinion['modeled_flank_damage']==pytest.approx(5*wheel['modeled_flank_damage'])
    assert result['members'][0]['flanks'][0]['modeled_damage']==pinion['modeled_flank_damage']
    assert not result['production_approved'] and result['rated_gearbox_life_hours'] is None


def test_reverse_flanks_are_separate_stationary_peaks_are_checked():
    study=duty_study([DutyPoint(name='forward',input_rpm=1000,input_torque_nm=2,duration_hours=1),
        DutyPoint(name='reverse',input_rpm=-500,input_torque_nm=-2,duration_hours=2),
        DutyPoint(name='hold',input_rpm=0,input_torque_nm=100,duration_hours=1)])
    result=calculate_contact_study(study);a,b=result['members'][0]['flanks']
    assert a['tooth_contact_cycles']==b['tooth_contact_cycles']==60000
    assert result['cases'][2]['members'][0]['modeled_flank_damage'] is None  # elastic limit exceeded
    assert a['modeled_damage'] is None and b['modeled_damage'] is not None
    study.source.duty[2].input_torque_nm=2;result=calculate_contact_study(study)
    assert result['cases'][2]['members'][0]['modeled_flank_damage']==0
    assert result['members'][0]['flanks'][0]['modeled_damage']==pytest.approx(result['members'][0]['flanks'][1]['modeled_damage'])


def test_unloaded_and_stationary_duty_never_reports_infinite_life():
    study=duty_study([DutyPoint(name='unloaded',input_rpm=1000,input_torque_nm=0,duration_hours=1),
        DutyPoint(name='parked',input_rpm=0,input_torque_nm=2,duration_hours=1)])
    for m in study.materials:m.life_curve=[]
    result=calculate_contact_study(study)
    for case in result['cases']:
        for member in case['members']:
            assert member['cycles_to_failure'] is None and member['modeled_flank_damage']==0
    assert result['members'][0]['flanks'][0]['modeled_damage']==0
    assert result['members'][0]['flanks'][1]['state']=='not_exercised'
    assert all(p['slide_roll_ratio'] is None for p in result['cases'][1]['profile'])
    json.dumps(result,allow_nan=False)


def test_pressure_and_load_factors_are_distinct_and_duration_scales_damage():
    study=synthetic_contact_example()
    for m in study.materials:m.life_curve=[ContactLifePoint(1e3,1000),ContactLifePoint(1e9,100)]
    original=calculate_contact_study(study)['cases'][0]
    study.cases[0].normal_load_multiplier=4
    changed=calculate_contact_study(study)['cases'][0]
    assert changed['peak_hertz_pressure_mpa']==pytest.approx(2*original['peak_hertz_pressure_mpa'])
    assert changed['members'][0]['modeled_flank_damage']==pytest.approx(64*original['members'][0]['modeled_flank_damage'])
    study.cases[0].normal_load_multiplier=1;study.pressure_design_factor=2
    factored=calculate_contact_study(study)['cases'][0]
    assert factored['peak_hertz_pressure_mpa']==original['peak_hertz_pressure_mpa']
    assert factored['design_pressure_mpa']==pytest.approx(changed['peak_hertz_pressure_mpa'])
    assert factored['members'][0]['modeled_flank_damage']==pytest.approx(changed['members'][0]['modeled_flank_damage'])


def test_missing_inputs_temperature_and_contact_domain_fail_closed():
    blank=calculate_contact_study(ContactStudy());assert blank['cases'][0]['peak_hertz_pressure_mpa'] is None
    for field in ('normal_load_multiplier','face_line_load_multiplier','effective_face_width_mm'):
        study=synthetic_contact_example();setattr(study.cases[0],field,None)
        assert calculate_contact_study(study)['cases'][0]['members'][0]['modeled_flank_damage'] is None
    study=synthetic_contact_example();study.cases[0].pinion_temperature_c=100
    result=calculate_contact_study(study)
    assert result['cases'][0]['members'][0]['modeled_flank_damage'] is None
    assert result['cases'][0]['members'][1]['modeled_flank_damage'] is not None
    study=synthetic_contact_example();study.cases[0].normal_load_multiplier=100;study.cases[0].face_line_load_multiplier=100
    result=calculate_contact_study(study)
    assert any(not p['within_small_contact_guard'] for p in result['cases'][0]['profile'])
    assert all(m['modeled_flank_damage'] is None for m in result['cases'][0]['members'])


def test_helical_undercut_and_noncontinuous_geometry_unassessed():
    for pair in (GearPair(pinion_helix_angle_deg=20),GearPair(pinion_teeth=10),GearPair(normal_pressure_angle_deg=30)):
        study=synthetic_contact_example();study.source.pair=pair;result=calculate_contact_study(study)
        assert result['geometry_findings'] and result['contact_path'] is None
        assert result['cases'][0]['peak_hertz_pressure_mpa'] is None


@pytest.mark.parametrize('change',[
    {'poisson_ratio':.5},{'youngs_modulus_mpa':0},{'maximum_elastic_pressure_mpa':float('nan')},
    {'minimum_temperature_c':100,'maximum_temperature_c':20},{'data_status':'approved'},
    {'life_curve':[ContactLifePoint()]},{'life_curve':[ContactLifePoint(1000,100),ContactLifePoint(2000,200)]},
    {'life_curve':[ContactLifePoint(1000,200),ContactLifePoint(1000,100)]},
])
def test_bad_material_data_rejected(change):
    study=synthetic_contact_example()
    for key,value in change.items():setattr(study.materials[0],key,value)
    with pytest.raises(ValueError):study.validate()


def test_strict_schema_factor_bounds_and_source_copy():
    source=EngineeringStudy();study=contact_from_study(source);study.source.pair.normal_module_mm=3
    assert source.pair.normal_module_mm==2
    data=asdict(study);del data['materials'][0]['redistribution_basis']
    with pytest.raises(ValueError):ContactStudy.from_dict(data)
    for field,value in (('normal_load_multiplier',.99),('effective_face_width_mm',21),('case_name','missing')):
        study=synthetic_contact_example();setattr(study.cases[0],field,value)
        with pytest.raises(ValueError):study.validate()


def test_source_recalculation_and_provenance_cannot_approve_production():
    study=synthetic_contact_example()
    for m in study.materials:m.data_status='declared'
    first=calculate_contact_study(study);study.source.duty[0].input_torque_nm*=2;second=calculate_contact_study(study)
    assert first['study_sha256']!=second['study_sha256'] and first['source_study_sha256']!=second['source_study_sha256']
    assert second['cases'][0]['peak_hertz_pressure_mpa']==pytest.approx(math.sqrt(2)*first['cases'][0]['peak_hertz_pressure_mpa'])
    assert not second['production_approved'] and second['rated_output_torque_nm'] is None


def test_saved_roundtrip_html_escaping_and_atomic_export(tmp_path):
    study=synthetic_contact_example();study.name='<script>bad</script>'
    path=tmp_path/'case.gearforge-contact';study.save(path);original=path.read_bytes()
    assert asdict(ContactStudy.load(path))==asdict(study)
    assert '<script>' not in contact_report_html(calculate_contact_study(study))
    out=tmp_path/'assessment';export_contact_study(study,out);assert len(verify_bundle(out)['files'])==3
    with pytest.raises(FileExistsError):export_contact_study(study,out)
    study.materials[0].poisson_ratio=5
    with pytest.raises(ValueError):study.save(path)
    assert path.read_bytes()==original
    (out/'report.html').write_text('changed')
    with pytest.raises(ValueError):verify_bundle(out)


def test_contact_cli_create_transfer_calculate_verify(tmp_path):
    from gearforge.cli import main
    blank=tmp_path/'blank.gearforge-contact';example=tmp_path/'example.gearforge-contact'
    assert main(['contact','new',str(blank)])==0
    assert ContactStudy.load(blank).materials[0].youngs_modulus_mpa is None
    assert main(['contact','new',str(example),'--synthetic-example'])==0
    assert main(['contact','new',str(example)])==1
    out=tmp_path/'assessment';assert main(['contact','calculate',str(example),'--out',str(out)])==0
    assert main(['verify',str(out)])==0
    source=tmp_path/'source.gearforge-study';EngineeringStudy().save(source);transfer=tmp_path/'transfer.gearforge-contact'
    assert main(['contact','from-study',str(source),'--out',str(transfer)])==0
    assert ContactStudy.load(transfer).source==EngineeringStudy.load(source)


@pytest.mark.gui
def test_editor_roundtrip_diagrams_and_failed_save(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.contact_ui import ContactStudyDialog,ContactPlot
    app=QApplication.instance() or QApplication([]);source=synthetic_contact_example();source.pressure_design_factor=1.23456789012345
    dialog=ContactStudyDialog(study=source);errors=[];dialog.show_error=lambda e:errors.append(str(e))
    assert asdict(dialog.read_study())==asdict(source)
    dialog.show();app.processEvents();assert dialog.calculate()
    for index in range(dialog.tabs.count()):
        dialog.tabs.setCurrentIndex(index);app.processEvents();assert not dialog.grab().isNull()
    for quantity in ContactPlot.QUANTITIES:
        dialog.quantity.setCurrentText(quantity);app.processEvents();assert not dialog.plot.grab().isNull()
    editor=dialog.materials['pinion']['youngs_modulus_mpa'];editor.setText('');editor.textEdited.emit('')
    assert dialog.dirty and dialog.result is None and not dialog.plot.profile
    assert dialog.calculate() and dialog.result['cases'][0]['peak_hertz_pressure_mpa'] is None
    old=tmp_path/'old.gearforge-contact';dialog.path=old
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-contact'),''))
    def fail(*a):raise OSError('Disk full')
    monkeypatch.setattr(ContactStudy,'save',fail)
    assert not dialog.save_study() and dialog.path==old and dialog.dirty and errors==['Disk full']
    dialog.dirty=False;dialog.close();app.processEvents()
