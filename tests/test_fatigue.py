from dataclasses import asdict
import json
import math
from pathlib import Path

import pytest

from gearforge.fatigue import (FatigueStudy,FatigueStation,FatigueCase,fatigue_from_shaft,nasa_example,
    calculate_fatigue_study,stress_life_block,export_fatigue_study,fatigue_report_html)
from gearforge.shafts import ShaftStudy,ShaftSection,ShaftCase,ShaftLoad,shaft_section_stress,solve_shaft_case
from gearforge.maintenance import verify_bundle


def test_exact_cut_sides_at_diameter_and_torque_discontinuities():
    shaft=ShaftStudy(sections=[ShaftSection(end_mm=60),ShaftSection(start_mm=60,outer_diameter_mm=16)],
        cases=[ShaftCase(loads=[ShaftLoad(name='Drive',position_mm=0,torque_nm=10),
            ShaftLoad(name='Gear',position_mm=60,force_y_n=-200,torque_nm=-10,moment_z_nm=2,axial_n=30)])])
    left=shaft_section_stress(shaft,0,60,'left');right=shaft_section_stress(shaft,0,60,'right')
    assert left['section']['outer_diameter_mm']==12 and right['section']['outer_diameter_mm']==16
    assert left['torque_nm']==-10 and right['torque_nm']==0
    assert left['axial_force_n']==30 and right['axial_force_n']==0
    assert right['curvature_moment_y_nmm']-left['curvature_moment_y_nmm']==pytest.approx(-2000)
    # Existing solver keeps both section boundary limits; match them independently
    # of plotting density or station interpolation.
    points=[p for p in solve_shaft_case(shaft)['critical_points'] if p['position_mm']==60]
    assert len(points)==2
    for cut,point in zip((left,right),points):
        assert abs(cut['nominal_torsion_mpa'])==pytest.approx(point['nominal_surface_torsion_mpa'])
        assert cut['nominal_bending_mpa']+abs(cut['nominal_axial_mpa'])==pytest.approx(point['nominal_surface_normal_mpa'])


@pytest.mark.parametrize('x,side',[(0,'left'),(120,'right'),(121,'left'),(50,'bad')])
def test_invalid_cut_rejected(x,side):
    with pytest.raises(ValueError):shaft_section_stress(ShaftStudy(),0,x,side)


def test_public_example_and_reference_fixture():
    fixture=json.loads((Path(__file__).parent/'data/open_fatigue_reference.json').read_text(encoding='utf-8'))
    assert fixture['passed'] and fixture['comparisons']==100
    for case in fixture['cases']:
        station=calculate_fatigue_study(FatigueStudy.from_dict(case['study']))['stations'][0]
        for expected in case['expected']:
            row=station if expected['case'] is None else station['cases'][expected['case']]
            actual=row['stress'][expected['stress']] if 'stress' in expected else row[expected['field']]
            assert actual==pytest.approx(expected['value'],rel=1e-10,abs=1e-12)


def test_temperature_not_ambient_and_missing_material_are_visible():
    study=fatigue_from_shaft(ShaftStudy());result=calculate_fatigue_study(study)
    assert result['stations'][0]['assessment']=='incomplete'
    assert result['stations'][0]['modeled_block_damage'] is None
    study=nasa_example();study.cases[0].operating_temperature_c=None
    station=calculate_fatigue_study(study)['stations'][0]
    assert next(c for c in station['checks'] if 'temperature' in c['name'])['state']=='unassessed'
    study.cases[0].operating_temperature_c=80
    station=calculate_fatigue_study(study)['stations'][0]
    assert station['cases'][0]['damage'] is None
    assert station['cases'][0]['range_state']=='outside_material_temperature'


@pytest.mark.parametrize('change',[
    {'fatigue_coefficient_mpa':100},{'yield_strength_mpa':0},{'maximum_cycles':10000},
    {'minimum_cycles':999},{'reference_cycles':float('inf')},{'yield_strength_mpa':True},
    {'minimum_temperature_c':60,'maximum_temperature_c':20},{'data_status':'approved'},
])
def test_bad_material_inputs_rejected(change):
    study=nasa_example()
    for key,value in change.items():setattr(study.material,key,value)
    with pytest.raises(ValueError):calculate_fatigue_study(study)


@pytest.mark.parametrize('change',[
    {'fatigue_reduction_factor':0},{'fatigue_reduction_factor':1.1},{'static_bending_kt':.9},
    {'position_mm':601},{'side':'unknown'},{'static_axial_kt':float('nan')},
])
def test_bad_station_inputs_rejected(change):
    study=nasa_example()
    for key,value in change.items():setattr(study.stations[0],key,value)
    with pytest.raises(ValueError):calculate_fatigue_study(study)


def test_power_law_limits_never_extrapolate_or_claim_infinite_life():
    study=nasa_example();m=study.material;s=study.stations[0]
    endpoint=m.reference_strength_mpa*s.fatigue_reduction_factor
    b=math.log(m.fatigue_coefficient_mpa/endpoint)/math.log(m.reference_cycles)
    for cycles in (m.minimum_cycles,m.reference_cycles,m.maximum_cycles):
        amplitude=m.fatigue_coefficient_mpa/cycles**b
        result=stress_life_block(m,s,amplitude,0,100)
        assert result['cycles_to_failure']==pytest.approx(cycles)
        assert result['damage']==pytest.approx(100/cycles)
    for amplitude,state in ((1e-100,'beyond_maximum_cycles'),(1e8,'below_minimum_cycles')):
        result=stress_life_block(m,s,amplitude,0,100)
        assert result['range_state']==state and result['damage'] is None and result['cycles_to_failure'] is None
    zero=stress_life_block(m,s,0,0,100)
    assert zero['damage']==0 and zero['cycles_to_failure'] is None
    assert stress_life_block(m,s,100,10000,100)['range_state']=='mean_torque_exceeds_ellipse'


def test_torque_ellipse_reduces_endpoint_not_coefficient():
    study=nasa_example();m=study.material;s=study.stations[0]
    plain=stress_life_block(m,s,200,0,1000);torque=stress_life_block(m,s,200,100,1000)
    expected=323*.4*math.sqrt(1-3*(100/634)**2)
    assert torque['corrected_reference_strength_mpa']==pytest.approx(expected)
    assert torque['cycles_to_failure'] < plain['cycles_to_failure']
    assert torque==stress_life_block(m,s,200,-100,1000)


def test_axial_hollow_and_unknown_load_model_are_not_silently_ignored():
    for change in ('axial','hollow','load_model'):
        study=nasa_example()
        if change=='axial':study.shaft.cases[0].loads[0].axial_n=1
        elif change=='hollow':study.shaft.sections[0].inner_diameter_mm=5
        else:study.cases[0].load_model='other'
        result=calculate_fatigue_study(study)['stations'][0]
        assert result['modeled_block_damage'] is None
        assert result['cases'][0]['range_state']=='unsupported_load_path'


def test_static_stationary_peaks_yield_and_concentrations():
    study=nasa_example();study.shaft.cases[0].rpm=0
    station=calculate_fatigue_study(study)['stations'][0]
    assert station['cases'][0]['rotation_cycles']==0 and station['cases'][0]['damage']==0
    study.stations[0].static_bending_kt=8
    station=calculate_fatigue_study(study)['stations'][0]
    assert station['cases'][0]['range_state']=='elastic_yield_reached'
    assert station['cases'][0]['damage'] is None
    assert any(c['state']=='outside_limit' and 'yield' in c['name'] for c in station['checks'])


def test_speed_sign_order_split_and_required_duration():
    study=nasa_example();first=calculate_fatigue_study(study)['stations'][0]
    for c in study.shaft.cases:c.rpm=-c.rpm
    study.shaft.cases.reverse();study.cases.reverse()
    second=calculate_fatigue_study(study)['stations'][0]
    assert first['modeled_block_damage']==pytest.approx(second['modeled_block_damage'])
    study.required_hours*=3
    third=calculate_fatigue_study(study)['stations'][0]
    assert third['target_modeled_block_damage']==pytest.approx(3*second['target_modeled_block_damage'])
    assert any(c['name']=='Duty and critical-section coverage' and c['state']=='unassessed' for c in third['checks'])


def test_strict_schema_case_mapping_bounds_and_copy():
    study=nasa_example();data=asdict(study);del data['material']['redistribution_basis']
    with pytest.raises(ValueError,match='Missing'):FatigueStudy.from_dict(data)
    data=asdict(study);data['production_approved']=True
    with pytest.raises(ValueError):FatigueStudy.from_dict(data)
    study.cases[0].case_name='missing'
    with pytest.raises(ValueError):study.validate()
    study=nasa_example();study.stations*=51
    with pytest.raises(ValueError):study.validate()
    shaft=ShaftStudy();copy=fatigue_from_shaft(shaft);copy.shaft.cases[0].loads[0].force_y_n=10
    assert shaft.cases[0].loads[0].force_y_n==-100


def test_recalculation_fingerprint_changes_and_no_approval_override():
    study=nasa_example();study.material.data_status='declared'
    first=calculate_fatigue_study(study)
    study.shaft.cases[0].loads[0].force_y_n*=1.01
    second=calculate_fatigue_study(study)
    assert first['study_sha256']!=second['study_sha256']
    assert first['shaft_study_sha256']!=second['shaft_study_sha256']
    assert not second['production_approved'] and second['rated_gearbox_life_hours'] is None
    assert second['stations'][0]['assessment']!='within_entered_limits'


def test_atomic_roundtrip_html_escaping_and_export_integrity(tmp_path):
    study=nasa_example();study.name='<script>alert(1)</script>'
    path=tmp_path/'shaft.gearforge-fatigue';study.save(path);original=path.read_bytes()
    assert asdict(FatigueStudy.load(path))==asdict(study)
    assert '<script>' not in fatigue_report_html(calculate_fatigue_study(study))
    out=tmp_path/'result';export_fatigue_study(study,out);assert len(verify_bundle(out)['files'])==3
    with pytest.raises(FileExistsError):export_fatigue_study(study,out)
    study.material.minimum_cycles=0
    with pytest.raises(ValueError):study.save(path)
    assert path.read_bytes()==original
    (out/'report.html').write_text('changed')
    with pytest.raises(ValueError):verify_bundle(out)


def test_cli_creation_transfer_and_calculation(tmp_path):
    from gearforge.cli import main
    blank=tmp_path/'blank.gearforge-fatigue';example=tmp_path/'example.gearforge-fatigue'
    assert main(['fatigue','new',str(blank)])==0
    assert FatigueStudy.load(blank).material.yield_strength_mpa is None
    assert main(['fatigue','new',str(example),'--nasa-example'])==0
    assert main(['fatigue','new',str(example)])==1
    out=tmp_path/'result';assert main(['fatigue','calculate',str(example),'--out',str(out)])==0
    assert main(['verify',str(out)])==0
    source=tmp_path/'source.gearforge-shaft';ShaftStudy().save(source);transfer=tmp_path/'transfer.gearforge-fatigue'
    assert main(['fatigue','from-shaft',str(source),'--out',str(transfer)])==0
    assert FatigueStudy.load(transfer).shaft==ShaftStudy.load(source)


@pytest.mark.gui
def test_editor_exact_roundtrip_dirty_invalidation_and_failed_save(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.fatigue_ui import FatigueStudyDialog
    app=QApplication.instance() or QApplication([]);source=nasa_example()
    source.required_hours=1.2345678901234567
    dialog=FatigueStudyDialog(study=source);errors=[];dialog.show_error=lambda e:errors.append(str(e))
    assert asdict(dialog.read_study())==asdict(source)
    dialog.show();app.processEvents();assert dialog.calculate()
    for index in range(dialog.tabs.count()):
        dialog.tabs.setCurrentIndex(index);app.processEvents();assert not dialog.grab().isNull()
    field=dialog.material['yield_strength_mpa'];field.setText('');field.textEdited.emit('')
    assert dialog.dirty and dialog.result is None and not dialog.report.toPlainText()
    assert dialog.calculate() and dialog.result['stations'][0]['modeled_block_damage'] is None
    old=tmp_path/'old.gearforge-fatigue';dialog.path=old
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-fatigue'),''))
    def failure(*a):raise OSError('Disk full')
    monkeypatch.setattr(FatigueStudy,'save',failure)
    assert not dialog.save_study() and dialog.path==old and dialog.dirty and errors==['Disk full']
    dialog.dirty=False;dialog.close();app.processEvents()
