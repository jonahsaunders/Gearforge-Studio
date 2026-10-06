from dataclasses import asdict
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from gearforge.engineering import EngineeringStudy
from gearforge.maintenance import verify_bundle
from gearforge.thermal import (AMBIENT,ThermalNode,ThermalLink,ThermalPhase,ThermalStudy,ThermalSystem,
    thermal_from_study,synthetic_thermal_example,calculate_thermal_study,exponential_roots,
    thermal_report_html,export_thermal_study)


def test_independent_thermal_reference_fixture():
    fixture=json.loads((Path(__file__).parent/'data/open_thermal_reference.json').read_text())
    assert fixture['passed'] and fixture['comparisons']==3539
    comparisons=0
    for case in fixture['cases']:
        result=calculate_thermal_study(ThermalStudy.from_dict(case['study']))
        for key,rows in (('entered',result['phases']),('periodic',[] if result['periodic_cycle'] is None else result['periodic_cycle']['phases'])):
            for row,reference in zip(rows,case['expected'][key] or [],strict=True):
                for point,temps in zip(row['profile'],reference['temperature_c'],strict=True):
                    assert list(point['temperature_c'].values())==pytest.approx(temps,rel=2e-9,abs=2e-7)
                    comparisons+=len(temps)
                for field,ref in (('heat_generated_j','generated_j'),('heat_rejected_to_ambient_j','rejected_j'),('stored_energy_change_j','stored_j')):
                    assert row[field]==pytest.approx(reference[ref],rel=2e-8,abs=2e-5);comparisons+=1
    assert comparisons==fixture['comparisons']


def one_body(capacity=1000,initial=20,heat=100,g=2,duration=500,ambient=20):
    study=thermal_from_study(EngineeringStudy());study.nodes=[ThermalNode('Body',capacity,initial)]
    study.links=[ThermalLink('Cooling','Body',AMBIENT)]
    study.phases=[ThermalPhase('Run',study.source.duty[0].name,duration,ambient,{'Body':heat},{'Cooling':g})]
    return study


def test_one_body_transient_steady_energy_and_small_time():
    study=one_body();result=calculate_thermal_study(study);row=result['phases'][0]
    expected=20+50*(1-math.exp(-1))
    assert row['end_temperature_c']['Body']==pytest.approx(expected,rel=1e-13)
    assert result['periodic_cycle']['start_temperature_c']['Body']==pytest.approx(70)
    assert row['heat_generated_j']==50000
    assert row['stored_energy_change_j']==pytest.approx(1000*(expected-20))
    assert row['heat_rejected_to_ambient_j']==pytest.approx(50000-1000*(expected-20))
    assert abs(row['energy_residual_j'])<1e-8
    system=ThermalSystem(study.nodes,study.links,study.phases[0])
    assert system.trajectory([20],1e-6)[0]==pytest.approx(20+1e-7,abs=1e-13)
    assert system.trajectory([20],1e10)[0]==pytest.approx(70)


def test_insulated_body_heats_linearly_without_periodic_rating():
    study=one_body(g=0);result=calculate_thermal_study(study);row=result['phases'][0]
    assert row['end_temperature_c']['Body']==pytest.approx(70)
    assert row['heat_rejected_to_ambient_j']==0 and row['stored_energy_change_j']==pytest.approx(50000)
    assert result['periodic_cycle'] is None and result['findings']
    assert row['uncooled_components']==[['Body']]
    study.nodes[0].initial_temperature_c=None;result=calculate_thermal_study(study)
    assert not result['phases'][0]['profile'] and result['periodic_cycle'] is None


def test_insulated_exchange_conserves_energy_with_unequal_capacities():
    study=one_body();study.nodes=[ThermalNode('Hot',1000,100),ThermalNode('Cold',3000,20)]
    study.links=[ThermalLink('Exchange','Hot','Cold')]
    study.phases=[ThermalPhase('Equalize',study.source.duty[0].name,100000,20,{'Hot':0,'Cold':0},{'Exchange':5})]
    result=calculate_thermal_study(study);row=result['phases'][0]
    assert list(row['end_temperature_c'].values())==pytest.approx([40,40],abs=1e-10)
    assert abs(row['stored_energy_change_j'])<1e-7 and abs(row['energy_residual_j'])<1e-7
    assert result['periodic_cycle'] is None


def test_phase_order_cooling_ambient_change_and_periodic_closure():
    study=synthetic_thermal_example();result=calculate_thermal_study(study)
    assert result['phases'][1]['start_temperature_c']==result['phases'][0]['end_temperature_c']
    assert result['periodic_cycle']['closure_residual_c']<1e-9
    first=result['phases'][-1]['end_temperature_c'];study.phases.reverse()
    reverse=calculate_thermal_study(study)
    assert first!=reverse['phases'][-1]['end_temperature_c']
    assert result['study_sha256']!=reverse['study_sha256']
    total=sum(r['heat_generated_j']-r['heat_rejected_to_ambient_j'] for r in result['periodic_cycle']['phases'])
    assert abs(total)<1e-6


def test_exponential_root_isolation_finds_multiple_and_tangent_roots():
    # x=e^-t. (x-.2)(x-.5)(x-.8) and (x-.5)^2 have known roots.
    roots=exponential_roots([0,1,2,3],[-.08,.66,-1.5,1],10)
    assert roots==pytest.approx(sorted([-math.log(.2),-math.log(.5),-math.log(.8)]),abs=1e-9)
    touch=exponential_roots([0,1,2],[.25,-1,1],10)
    assert min(abs(r-math.log(2)) for r in touch)<1e-8
    assert not exponential_roots([1,2],[1,2],10)
    # Factoring out a huge common decay must not lose late roots to underflow.
    late=exponential_roots([1000,1001],[-math.exp(-20),1],100)
    assert late==pytest.approx([20],abs=1e-8)


def test_internal_peak_is_found_between_start_and_end_without_plot_samples():
    study=one_body();study.nodes=[ThermalNode('Hot',1000,120),ThermalNode('Cool',1000,20)]
    study.links=[ThermalLink('Exchange','Hot','Cool'),ThermalLink('Cooling','Cool',AMBIENT)]
    study.phases=[ThermalPhase('Transfer',study.source.duty[0].name,10000,20,{'Hot':0,'Cool':0},{'Exchange':2,'Cooling':1})]
    system=ThermalSystem(study.nodes,study.links,study.phases[0]);row=system.phase_result([120,20],draw=False)
    cool=row['extrema'][1]
    assert 0<cool['maximum_at_s']<10000 and cool['maximum_c']>40
    dense=[system.trajectory([120,20],t)[1] for t in np.linspace(0,10000,10001)]
    assert cool['maximum_c']>=max(dense)-1e-10
    assert row['extrema']==system.phase_result([120,20],draw=True)['extrema']


def test_repeated_cycle_envelope_contains_warmup_from_mixed_initial_temperatures():
    study=synthetic_thermal_example();study.nodes[0].initial_temperature_c=100;study.nodes[1].initial_temperature_c=5
    result=calculate_thermal_study(study);envelope=result['repeated_cycle_envelope']['nodes']
    systems=[ThermalSystem(study.nodes,study.links,p) for p in study.phases];state=np.array([n.initial_temperature_c for n in study.nodes])
    for _ in range(35):
        for system in systems:
            row=system.phase_result(state,draw=False)
            for e,b in zip(row['extrema'],envelope):
                assert e['minimum_c']>=b['minimum_bound_c']-1e-8
                assert e['maximum_c']<=b['maximum_bound_c']+1e-8
            state=np.array(list(row['end_temperature_c'].values()))


def test_unknown_initial_still_allows_periodic_but_missing_phase_breaks_history():
    study=synthetic_thermal_example();study.nodes[0].initial_temperature_c=None
    result=calculate_thermal_study(study)
    assert all(not row['profile'] for row in result['phases']) and result['periodic_cycle']
    assert result['repeated_cycle_envelope'] is None
    study=synthetic_thermal_example();study.phases[0].heat_w['Oil']=None
    result=calculate_thermal_study(study)
    assert result['periodic_cycle'] is None and all(not row['profile'] for row in result['phases'])


def test_unknown_capacity_and_ambient_remain_unassessed():
    for field in ('capacity_j_per_k','initial_temperature_c'):
        study=synthetic_thermal_example();setattr(study.nodes[0],field,None)
        result=calculate_thermal_study(study);assert not result['phases'][0]['profile']
    study=synthetic_thermal_example();study.phases[0].ambient_c=None
    assert not calculate_thermal_study(study)['phases'][0]['profile']


def test_conservative_bound_crossing_is_not_a_calculated_failure():
    study=synthetic_thermal_example();study.nodes[0].initial_temperature_c=75
    first=calculate_thermal_study(study)
    node=study.nodes[2];info=first['nodes'][2]
    assert info['all_repeated_cycles_bound']['maximum_bound_c']>info['calculated_maximum_c']+1
    node.maximum_allowable_c=info['calculated_maximum_c']+.1
    result=calculate_thermal_study(study)['nodes'][2]
    assert result['calculated_temperatures_within_allowable'] is True
    assert result['all_repeated_cycles_bound_within_allowable'] is False
    assert 'outside' not in result['assessment']


def test_known_exceeded_model_or_material_limits_report_outside():
    for field in ('maximum_allowable_c','model_maximum_c'):
        study=synthetic_thermal_example();setattr(study.nodes[0],field,26)
        assert 'outside' in calculate_thermal_study(study)['nodes'][0]['assessment']


def test_transfer_uses_actual_duration_but_never_assumed_efficiency_as_heat():
    source=EngineeringStudy();study=thermal_from_study(source)
    assert study.phases[0].duration_s==source.duty[0].duration_hours*3600
    assert all(v is None for v in study.phases[0].heat_w.values())
    study.source.assumed_efficiency=.5;assert source.assumed_efficiency!=.5
    result=calculate_thermal_study(study)
    assert not result['phases'][0]['profile'] and result['source_estimated_loss_power_w'][source.duty[0].name]==pytest.approx(125)


@pytest.mark.parametrize('field,value',[('capacity_j_per_k',0),('capacity_j_per_k',True),('initial_temperature_c',float('nan')),
    ('data_status','approved'),('name',AMBIENT),('maximum_allowable_c',-10)])
def test_bad_node_inputs_rejected(field,value):
    study=synthetic_thermal_example();setattr(study.nodes[0],field,value)
    with pytest.raises(ValueError):study.validate()


def test_network_and_phase_integrity_rejects_bad_topology_or_conditions():
    changes=[lambda s:s.links.append(copy.deepcopy(s.links[0])),lambda s:setattr(s.links[0],'second','missing'),
        lambda s:setattr(s.links[0],'second',s.links[0].first),lambda s:s.phases[0].heat_w.pop('Oil'),
        lambda s:s.phases[0].heat_w.update(Oil=-1),lambda s:setattr(s.phases[0],'source_case','absent'),
        lambda s:s.phases[0].conductance_w_per_k.update({'Gears to oil':float('inf')})]
    for change in changes:
        study=synthetic_thermal_example();change(study)
        with pytest.raises(ValueError):study.validate()
    study=synthetic_thermal_example()
    for phase in study.phases:phase.duration_s=0
    with pytest.raises(ValueError):study.validate()


def test_zero_duration_phase_adds_no_heat_and_preserves_temperature():
    study=synthetic_thermal_example();study.phases[0].duration_s=0
    result=calculate_thermal_study(study);row=result['phases'][0]
    assert row['heat_generated_j']==0 and row['stored_energy_change_j']==0
    assert row['start_temperature_c']==row['end_temperature_c']


def test_roundtrip_strict_schema_escaping_and_export_integrity(tmp_path):
    study=synthetic_thermal_example();study.name='<script>name</script>';path=tmp_path/'x.gearforge-thermal';study.save(path)
    assert asdict(ThermalStudy.load(path))==asdict(study)
    data=asdict(study);data['approval']=True
    with pytest.raises(ValueError):ThermalStudy.from_dict(data)
    result=calculate_thermal_study(study);assert '<script>' not in thermal_report_html(result)
    out=tmp_path/'assessment';export_thermal_study(study,out);assert len(verify_bundle(out)['files'])==3
    with pytest.raises(FileExistsError):export_thermal_study(study,out)
    (out/'report.html').write_text('changed')
    with pytest.raises(ValueError):verify_bundle(out)
    for node in study.nodes:node.data_status='declared'
    result=calculate_thermal_study(study)
    assert not result['production_approved'] and result['rated_gearbox_life_hours'] is None


def test_thermal_cli_create_transfer_calculate_verify(tmp_path):
    from gearforge.cli import main
    blank=tmp_path/'blank.gearforge-thermal';example=tmp_path/'example.gearforge-thermal'
    assert main(['thermal','new',str(blank)])==0
    assert ThermalStudy.load(blank).nodes[0].capacity_j_per_k is None
    assert main(['thermal','new',str(example),'--synthetic-example'])==0
    assert main(['thermal','new',str(example)])==1
    out=tmp_path/'assessment';assert main(['thermal','calculate',str(example),'--out',str(out)])==0
    assert main(['verify',str(out)])==0
    source=tmp_path/'source.gearforge-study';EngineeringStudy().save(source);transfer=tmp_path/'transfer.gearforge-thermal'
    assert main(['thermal','from-study',str(source),'--out',str(transfer)])==0
    assert ThermalStudy.load(transfer).source==EngineeringStudy.load(source)


@pytest.mark.gui
def test_thermal_editor_roundtrip_topology_history_and_failed_save(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.thermal_ui import ThermalStudyDialog
    app=QApplication.instance() or QApplication([]);study=synthetic_thermal_example();study.nodes[0].capacity_j_per_k=1234.56789012345
    dialog=ThermalStudyDialog(study=study);errors=[];dialog.show_error=lambda e:errors.append(str(e));dialog.show();app.processEvents()
    assert asdict(dialog.read_study())==asdict(study)
    assert dialog.calculate()
    for index in range(dialog.tabs.count()):dialog.tabs.setCurrentIndex(index);app.processEvents();assert not dialog.grab().isNull()
    for cycle in range(2):
        dialog.cycle_selector.setCurrentIndex(cycle)
        for phase in range(dialog.plot_phase.count()):
            dialog.plot_phase.setCurrentIndex(phase)
            for node in range(dialog.plot_body.count()):
                dialog.plot_body.setCurrentIndex(node);app.processEvents();assert dialog.plot.points and not dialog.plot.grab().isNull()
    dialog.early.setChecked(True);app.processEvents();assert not dialog.plot.grab().isNull()
    field=dialog.body_fields['name'];field.setText('Renamed gear train');field.textEdited.emit(field.text())
    assert dialog.result is None and not dialog.plot.points and dialog.dirty
    renamed=dialog.read_study();assert 'Renamed gear train' in renamed.phases[0].heat_w
    assert renamed.links[0].first=='Renamed gear train'
    dialog.paths.item(0,0).setText('Renamed path');renamed=dialog.read_study()
    assert renamed.phases[1].conductance_w_per_k['Renamed path']==2
    assert dialog.add_body();assert dialog.add_path();assert dialog.remove_body()
    assert len(dialog.read_study().nodes)==3
    assert dialog.add_phase();assert dialog.move_phase(-1);assert dialog.remove_phase()
    assert len(dialog.read_study().phases)==2
    bad=dialog.body_fields['capacity_j_per_k'];bad.setText('invalid');bad.textEdited.emit('invalid')
    original_index=dialog.body_index;dialog.body_selector.setCurrentIndex((original_index+1)%3)
    assert dialog.body_index==original_index and bad.text()=='invalid'
    bad.setText('1234.56789012345');bad.textEdited.emit(bad.text())
    old=tmp_path/'old.gearforge-thermal';dialog.path=old
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-thermal'),''))
    def fail(*a):raise OSError('Disk full')
    monkeypatch.setattr(ThermalStudy,'save',fail)
    assert not dialog.save_study() and dialog.path==old and dialog.dirty and errors[-1]=='Disk full'
    dialog.dirty=False;dialog.close();app.processEvents()
