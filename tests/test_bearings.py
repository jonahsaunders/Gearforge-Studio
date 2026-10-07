from dataclasses import asdict
import json
import math
from pathlib import Path

import pytest

from gearforge.bearings import (BearingStudy, BearingDefinition, BearingCase, bearings_from_shaft,
    synthetic_bearing_example, calculate_bearing_study, export_bearing_study, bearing_report_html)
from gearforge.shafts import ShaftStudy, ShaftCase, ShaftLoad
from gearforge.maintenance import verify_bundle


def study_for(cases=None, kind='deep_groove_ball'):
    shaft=ShaftStudy(cases=cases or [ShaftCase(rpm=1000,duration_hours=1,loads=[ShaftLoad(force_y_n=-200)])])
    study=synthetic_bearing_example(shaft)
    for bearing in study.bearings:
        bearing.dynamic_capacity_n=1000;bearing.static_capacity_n=1000;bearing.kind=kind
        bearing.misalignment_limit_rad=.01;bearing.axial_limit_n=1000
    return study


def checks(result, position='a'):
    bearing=next(b for b in result['bearings'] if b['position']==position)
    return {c['name']:c for c in bearing['checks']+[c for row in bearing['cases'] for c in row['checks']]}


def test_constant_load_basic_life_and_static_safety():
    result=calculate_bearing_study(study_for());a=result['bearings'][0]
    assert a['cases'][0]['equivalent_dynamic_n']==100
    assert a['cases'][0]['basic_l10_revolutions']==pytest.approx(1e9)
    assert a['basic_l10_repeated_duty_hours']==pytest.approx(1e9/60000)
    assert a['cases'][0]['cycle_damage']==pytest.approx(.00006)
    assert a['cases'][0]['static_safety']==10
    assert not result['production_approved'] and result['rated_gearbox_life_hours'] is None
    assert a['assessment']=='synthetic_example'


def test_variable_speed_reversal_stops_and_peak_static_load():
    study=study_for([
        ShaftCase(name='forward',rpm=1000,duration_hours=1,loads=[ShaftLoad(force_y_n=-200)]),
        ShaftCase(name='reverse',rpm=-500,duration_hours=2,loads=[ShaftLoad(force_y_n=400)]),
        ShaftCase(name='parked peak',rpm=0,duration_hours=1,loads=[ShaftLoad(force_y_n=-1400)]),
    ])
    study.required_hours=10000
    result=calculate_bearing_study(study);a=result['bearings'][0]
    assert a['cycle_damage']==pytest.approx(.00006+.00048)
    assert a['basic_l10_repeated_duty_hours']==pytest.approx(4/.00054)
    assert a['target_damage']==pytest.approx(1.35)
    assert a['cases'][2]['cycle_damage']==0 and a['cases'][2]['revolutions']==0
    assert a['cases'][2]['static_safety']==pytest.approx(10/7)
    assert any(c['state']=='outside_limit' for c in a['cases'][2]['checks'])
    assert a['assessment']=='synthetic_outside_entered_limits'


def test_split_case_order_and_duration_scaling_preserve_life():
    initial=calculate_bearing_study(study_for())['bearings'][0]['basic_l10_repeated_duty_hours']
    study=study_for([ShaftCase(name='a',rpm=-1000,duration_hours=.25,loads=[ShaftLoad(force_y_n=-200)]),
                     ShaftCase(name='b',rpm=1000,duration_hours=.75,loads=[ShaftLoad(force_y_n=-200)])])
    assert calculate_bearing_study(study)['bearings'][0]['basic_l10_repeated_duty_hours']==pytest.approx(initial)
    study.shaft.cases.reverse();study.cases.reverse()
    for case in study.shaft.cases:case.duration_hours*=10
    assert calculate_bearing_study(study)['bearings'][0]['basic_l10_repeated_duty_hours']==pytest.approx(initial)


def test_roller_exponent_and_unsupported_axial_load():
    study=study_for(kind='cylindrical_roller_radial')
    a=calculate_bearing_study(study)['bearings'][0]
    assert a['basic_l10_repeated_duty_hours']==pytest.approx(1e6*10**(10/3)/60000)
    study.shaft.cases[0].loads[0].axial_n=100
    result=calculate_bearing_study(study)
    assert result['bearings'][0]['cycle_damage'] is None
    assert result['bearings'][0]['basic_l10_repeated_duty_hours'] is None
    assert result['bearings'][1]['basic_l10_repeated_duty_hours'] is not None
    assert checks(result)['Bearing axial-load model']['state']=='unassessed'


def test_combined_load_factors_are_required_per_case_and_radial_floor():
    study=study_for();study.shaft.cases[0].loads[0].axial_n=120
    assert calculate_bearing_study(study)['bearings'][0]['cycle_damage'] is None
    condition=study.cases[0]
    condition.dynamic_x=.56;condition.dynamic_y=1.6;condition.static_x=.6;condition.static_y=.5
    assert calculate_bearing_study(study)['bearings'][0]['cycle_damage'] is None
    condition.factor_basis='Original synthetic factor branch, only for this test'
    row=calculate_bearing_study(study)['bearings'][0]['cases'][0]
    assert row['equivalent_dynamic_n']==pytest.approx(248)
    assert row['equivalent_static_n']==pytest.approx(120)
    condition.static_y=0
    assert calculate_bearing_study(study)['bearings'][0]['cases'][0]['equivalent_static_n']==100


def test_stationary_combined_case_needs_static_not_dynamic_factors():
    study=study_for([ShaftCase(name='run',rpm=1000,duration_hours=1,loads=[ShaftLoad(force_y_n=-200)]),
                     ShaftCase(name='hold',rpm=0,duration_hours=1,loads=[ShaftLoad(force_y_n=-200,axial_n=100)])])
    condition=next(c for c in study.cases if c.case_name=='hold' and c.position=='a')
    condition.static_x=.6;condition.static_y=.5;condition.factor_basis='Synthetic static branch'
    a=calculate_bearing_study(study)['bearings'][0]
    assert a['basic_l10_repeated_duty_hours']==pytest.approx(2/.00006)
    assert not any(c['name']=='Dynamic combined-load factors' for c in a['cases'][1]['checks'])


def test_missing_data_and_oscillation_cannot_be_complete():
    study=bearings_from_shaft(ShaftStudy())
    result=calculate_bearing_study(study)
    assert all(b['assessment']=='incomplete' and b['basic_l10_repeated_duty_hours'] is None for b in result['bearings'])
    study=study_for();study.cases[0].motion='oscillation'
    a=calculate_bearing_study(study)['bearings'][0]
    assert a['cycle_damage'] is None and a['cases'][0]['revolutions'] is None


def test_zero_load_or_stationary_only_never_reports_infinite_life():
    for speed,load in ((1000,0),(0,200),(0,0)):
        study=study_for([ShaftCase(rpm=speed,duration_hours=1,loads=[ShaftLoad(force_y_n=load)])])
        result=calculate_bearing_study(study)
        assert result['bearings'][0]['basic_l10_repeated_duty_hours'] is None
        assert result['bearings'][0]['cycle_damage']==0
        json.dumps(result,allow_nan=False)


def test_very_small_load_stays_finite_and_unqualified():
    study=study_for([ShaftCase(loads=[ShaftLoad(force_y_n=1e-110)])])
    result=calculate_bearing_study(study)
    json.dumps(result,allow_nan=False)
    assert result['bearings'][0]['basic_l10_repeated_duty_hours'] is None


def test_limits_temperature_is_not_ambient_and_provenance_no_override():
    study=study_for();b=study.bearings[0]
    b.data_status='declared';b.manufacturer='Synthetic test declaration';b.bore_mm=13
    b.speed_limit_rpm=900;b.axial_limit_n=0;b.misalignment_limit_rad=.00001;b.minimum_dynamic_load_n=101
    study.cases[0].operating_temperature_c=None
    result=calculate_bearing_study(study);c=checks(result)
    assert c['Maximum bearing temperature °C']['state']=='unassessed'
    for name in ('Nominal seat/bore match','Speed rpm','Minimum equivalent dynamic load N','Conservative bearing misalignment rad'):
        assert c[name]['state']=='outside_limit'
    assert result['bearings'][0]['assessment']=='outside_entered_limits'
    assert not result['production_approved']


@pytest.mark.parametrize('change',[
    {'kind':'angular_contact'},{'dynamic_capacity_n':0},{'static_capacity_n':float('nan')},
    {'speed_limit_rpm':True},{'misalignment_limit_rad':-1},{'required_static_safety':0},
    {'minimum_temperature_c':80,'maximum_temperature_c':20},{'data_status':'approved'},
    {'position':'c'},{'source_reference':'\x00'},
])
def test_invalid_rating_data_rejected(change):
    study=study_for()
    for key,value in change.items():setattr(study.bearings[0],key,value)
    with pytest.raises(ValueError):calculate_bearing_study(study)


def test_case_identity_motion_and_complete_input_schema():
    study=study_for();study.cases[0].case_name='missing'
    with pytest.raises(ValueError):study.validate()
    study=study_for();study.cases[0].motion='stationary'
    with pytest.raises(ValueError):study.validate()
    data=asdict(study_for());del data['bearings'][0]['rating_conditions']
    with pytest.raises(ValueError,match='Missing'):BearingStudy.from_dict(data)
    data=asdict(study_for());data['cases'].append(data['cases'][0])
    with pytest.raises(ValueError):BearingStudy.from_dict(data)


def test_shaft_recalculation_changes_hash_and_loads_and_does_not_mutate_source():
    shaft=ShaftStudy();study=bearings_from_shaft(shaft)
    old=calculate_bearing_study(study)
    study.shaft.cases[0].loads[0].force_y_n*=2
    new=calculate_bearing_study(study)
    assert shaft.cases[0].loads[0].force_y_n==-100
    assert new['shaft_study_sha256']!=old['shaft_study_sha256'] and new['study_sha256']!=old['study_sha256']
    assert new['bearings'][0]['cases'][0]['radial_load_n']==2*old['bearings'][0]['cases'][0]['radial_load_n']


def test_saved_roundtrip_atomic_failure_and_export_integrity(tmp_path):
    study=study_for();study.name='<script>danger</script>'
    path=tmp_path/'bearing.gearforge-bearing';study.save(path);original=path.read_bytes()
    assert asdict(BearingStudy.load(path))==asdict(study)
    result=calculate_bearing_study(study)
    assert '<script>' not in bearing_report_html(result)
    destination=tmp_path/'assessment';export_bearing_study(study,destination)
    assert len(verify_bundle(destination)['files'])==3
    with pytest.raises(FileExistsError):export_bearing_study(study,destination)
    study.bearings[0].dynamic_capacity_n=-1
    with pytest.raises(ValueError):study.save(path)
    assert path.read_bytes()==original
    (destination/'report.html').write_text('changed')
    with pytest.raises(ValueError):verify_bundle(destination)


def test_bearing_cli_blank_example_transfer_calculate_verify(tmp_path):
    from gearforge.cli import main
    blank=tmp_path/'blank.gearforge-bearing';example=tmp_path/'example.gearforge-bearing'
    assert main(['bearing','new',str(blank)])==0
    assert BearingStudy.load(blank).bearings[0].dynamic_capacity_n is None
    assert main(['bearing','new',str(example),'--synthetic-example'])==0
    assert main(['bearing','new',str(example)])==1
    destination=tmp_path/'assessment'
    assert main(['bearing','calculate',str(example),'--out',str(destination)])==0
    assert main(['verify',str(destination)])==0
    shaft=tmp_path/'source.gearforge-shaft';ShaftStudy().save(shaft)
    transfer=tmp_path/'transferred.gearforge-bearing'
    assert main(['bearing','from-shaft',str(shaft),'--out',str(transfer)])==0
    assert BearingStudy.load(transfer).shaft==ShaftStudy.load(shaft)


def test_declared_complete_inputs_still_cannot_approve_production():
    study=study_for()
    for bearing in study.bearings:
        bearing.data_status='declared';bearing.manufacturer='Synthetic test declaration'
    result=calculate_bearing_study(study)
    assert all(b['assessment']=='within_entered_limits' for b in result['bearings'])
    assert not result['production_approved'] and result['rated_gearbox_life_hours'] is None


def test_import_keeps_entire_duty_duration():
    source=ShaftStudy(cases=[ShaftCase(name='first',duration_hours=1000000),ShaftCase(name='second',duration_hours=1000000)])
    assert bearings_from_shaft(source).required_hours==2000000


def test_high_precision_arithmetic_fixture():
    fixture=json.loads((Path(__file__).parent/'data/open_bearing_reference.json').read_text(encoding='utf-8'))
    assert fixture['passed'] and fixture['comparisons']>200
    for case in fixture['cases']:
        actual=calculate_bearing_study(BearingStudy.from_dict(case['study']))
        for expected in case['expected']:
            row=actual['bearings'][expected['bearing']]
            if expected['case'] is not None:row=row['cases'][expected['case']]
            if expected['value'] is None:assert row[expected['field']] is None
            else:assert row[expected['field']]==pytest.approx(expected['value'],rel=1e-10,abs=1e-12),(case['name'],expected)


@pytest.mark.gui
def test_bearing_editor_blank_data_dirty_invalidation_and_failed_save(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.bearing_ui import BearingStudyDialog
    app=QApplication.instance() or QApplication([])
    dialog=BearingStudyDialog(study=synthetic_bearing_example());errors=[];dialog.show_error=lambda e:errors.append(str(e))
    dialog.show();app.processEvents();assert dialog.calculate()
    for index in range(dialog.tabs.count()):
        dialog.tabs.setCurrentIndex(index);app.processEvents();assert not dialog.grab().isNull()
    editor=dialog.editors['a']['dynamic_capacity_n'];editor.setText('');editor.textEdited.emit('')
    assert dialog.result is None and dialog.dirty and not dialog.report.toPlainText()
    assert dialog.calculate() and dialog.result['bearings'][0]['basic_l10_repeated_duty_hours'] is None
    original=tmp_path/'old.gearforge-bearing';dialog.path=original
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-bearing'),''))
    def failure(*a):raise OSError('Disk full')
    monkeypatch.setattr(BearingStudy,'save',failure)
    assert not dialog.save_study() and dialog.path==original and dialog.dirty
    assert errors==['Disk full']
    dialog.dirty=False;dialog.close();app.processEvents()
