from dataclasses import asdict
import copy
import csv
import io
import json
from pathlib import Path
import sys
import time

import numpy as np
import pytest

from gearforge.elasticity import PlaneElasticSystem
from gearforge.maintenance import verify_bundle
from gearforge.root_stress import RootStressStudy, calculate_root_study, export_root_study, root_report_html
from gearforge.stress_probes import StressProbe, locate_point, locate_probes, probe_response, resolve_stress, probe_changes, probe_csv

ROOT=Path(__file__).resolve().parents[1]


def small_study():
    study=RootStressStudy.load(ROOT/'examples/synthetic-root-probes.gearforge-root')
    study.sector_teeth=3;study.angular_divisions_per_tooth=8;study.radial_layers=4
    return study


@pytest.fixture(scope='module')
def result():
    study=small_study()
    study.probes.extend([StressProbe('Shared edge',0.,15.,37.,'Synthetic inner material point'),StressProbe('Outside',0.,0.)])
    for name,factor in [('Reversed',-1),('Zero',0),('Unknown temperature',1)]:
        duty=copy.deepcopy(study.source.source.duty[0]);duty.name=name;duty.input_torque_nm*=factor
        if factor<0:duty.input_rpm*=-1
        case=copy.deepcopy(study.cases[0]);case.case_name=name
        if name=='Unknown temperature':case.temperature_c=100
        study.source.source.duty.append(duty);study.cases.append(case)
    study.source.source.target_life_hours=sum(duty.duration_hours for duty in study.source.source.duty)
    return calculate_root_study(study)


def test_independent_fixed_points_include_edges_and_vertices():
    sys.path.insert(0,str(ROOT/'scripts'))
    from verify_stress_probe_reference import application_points,source_hash
    reference=json.loads((ROOT/'tests/data/open_stress_probe_reference.json').read_text())
    base=json.loads((ROOT/'tests/data/open_elastic_reference.json').read_text())['cases'];count=0
    assert reference['reference_license']=='BSD-3-Clause' and reference['reference_version']=='12.0.2'
    for case,expected in zip(base,reference['cases'],strict=True):
        assert source_hash(case)==expected['elastic_case_sha256'] and case['name']==expected['name']
        actual=np.array(application_points(case,expected['points']))
        np.testing.assert_allclose(actual,expected['expected_stress_mpa'],rtol=reference['relative_tolerance'],atol=reference['absolute_tolerance_mpa'])
        count+=actual.size
    assert count==reference['comparisons']==6400


@pytest.mark.parametrize('direction,expected',[(0,[12,-5,-3,7]),(90,[-3,5,12,7]),(45,[-.5,-7.5,9.5,7]),(-45,[9.5,7.5,-.5,7])])
def test_signed_traction_rotation(direction,expected):
    actual=resolve_stress([12,-3,-5,7],direction)
    np.testing.assert_allclose(list(actual.values()),expected,atol=1e-12)
    np.testing.assert_allclose(list(resolve_stress([-12,3,5,-7],direction).values()),-np.array(expected),atol=1e-12)


def test_distorted_cell_affine_stress_and_shared_edge_values_are_not_averaged():
    nodes=np.array([[0,0],[2,0],[2.2,1.1],[0,1],[4,0],[4,1.3]])
    elements=np.array([[0,1,2,3],[1,4,5,2]])
    system=PlaneElasticSystem(nodes,elements,210000,.3,3)
    u=np.column_stack((.001*nodes[:,0]+.002*nodes[:,1],-.003*nodes[:,0]+.0005*nodes[:,1])).ravel()
    point=nodes[[1,2]].mean(axis=0);probes=[StressProbe('Edge',*point,0,'Synthetic')]
    location=locate_probes(system,probes);assert len(location[0]['locations'])==2
    values=probe_response(system,u,probes,location)[0]['values']
    np.testing.assert_allclose([v['stress_mpa_per_n_mm'] for v in values],[[265.38461538461536,184.6153846153846,-80.76923076923077,0]]*2,atol=1e-10)
    # Change only nodes on the right cell: the shared displacement stays continuous,
    # but derivatives on its two sides differ and must remain separately observable.
    u[8]+=.002;u[10]+=.002
    values=probe_response(system,u,probes,location)[0]['values']
    assert len(values)==2 and values[0]['stress_mpa_per_n_mm'][0]!=pytest.approx(values[1]['stress_mpa_per_n_mm'][0])
    for point in ((-1e-4,.5),(1,2),(float('nan'),0)):
        with pytest.raises(ValueError):locate_point(nodes,elements,*point)


def test_fixed_coordinates_all_meshes_reversal_and_zero_stress(result):
    assert result['calculation_available'] and not result['production_approved']
    assert result['rated_gearbox_life_hours'] is None
    for mesh in [*result['mesh_levels'],result['domain_check']]:
        for probe,mapping in zip(result['inputs']['probes'],mesh['probe_locations'],strict=True):
            if probe['name']=='Outside':assert not mapping['available'] and not mapping['locations'];continue
            assert mapping['available']
            for side in mapping['locations']:
                np.testing.assert_allclose([side['recovered_x_mm'],side['recovered_y_mm']],[probe['x_mm'],probe['y_mm']],atol=1e-10)
        assert len(mesh['probe_locations'][2]['locations'])>=2
    forward,reverse,zero,unknown=result['cases']
    assert forward['flank']=='left' and reverse['flank']=='right' and not unknown['positions']
    for a,b,z in zip(forward['positions'],reverse['positions'],zero['positions'],strict=True):
        left=np.array([v['stress_mpa'] for v in a['point_probes'][0]['values']])
        right=np.array([v['stress_mpa'] for v in b['point_probes'][1]['values']])*[1,1,-1,1]
        np.testing.assert_allclose(left[np.argsort(left[:,0])],right[np.argsort(right[:,0])],rtol=1e-8,atol=1e-9)
        for point in z['point_probes']:
            for value in point['values']:assert value['stress_mpa']==[0.,0.,0.,0.]
        assert not a['point_probes'][-1]['values']
    check=result['probe_checks'][-1]
    assert check['mesh_convergence_passed'] is None and check['domain_sensitivity_passed'] is None and not check['basis_entered']
    assert any('Outside' in finding for finding in result['findings'])
    assert all(value is not None for value in result['probe_checks'][0]['mesh_changes_percent'])


def test_component_envelope_sensitivity_and_missing_values(result):
    first=copy.deepcopy(result['mesh_levels'][0]);second=copy.deepcopy(first)
    assert probe_changes(first,second,0)==0
    for response in second['responses']:
        for value in response['point_probes'][0]['values']:
            value['resolved_mpa_per_n_mm']={k:2*v for k,v in value['resolved_mpa_per_n_mm'].items()}
    assert probe_changes(first,second,0)==pytest.approx(50)
    second['responses'][0]['point_probes'][0]['values']=[]
    assert probe_changes(first,second,0) is None
    second['responses'][0]['flank']='opposite'
    with pytest.raises(ValueError):probe_changes(first,second,0)


@pytest.mark.parametrize('field,value',[('x_mm',True),('y_mm',float('inf')),('normal_direction_deg',181),('name',''),('basis',False)])
def test_strict_probe_input(field,value):
    probe=StressProbe();setattr(probe,field,value)
    with pytest.raises(ValueError):probe.validate()


def test_legacy_inputs_probe_limits_and_roundtrip(tmp_path):
    study=small_study();data=asdict(study);data.pop('probes')
    assert RootStressStudy.from_dict(data).probes==[]
    path=tmp_path/'points.gearforge-root';study.save(path);assert asdict(RootStressStudy.load(path))==asdict(study)
    for probes in ([study.probes[0]]*2,[StressProbe(str(i)) for i in range(17)],False,[{'bogus':3}]):
        data=asdict(study);data['probes']=[asdict(p) if isinstance(p,StressProbe) else p for p in probes] if isinstance(probes,list) else probes
        with pytest.raises(ValueError):RootStressStudy.from_dict(data)


def test_signed_export_integrity_and_unavailable_rows(result,tmp_path,monkeypatch):
    import gearforge.root_stress as module
    r=copy.deepcopy(result);study=RootStressStudy.from_dict(r['inputs'])
    r['inputs']['probes'][0]['name']='=POINT';r['inputs']['probes'][0]['basis']='<script>test</script>'
    r['cases'][0]['name']='@CASE';monkeypatch.setattr(module,'calculate_root_study',lambda s:r)
    destination=tmp_path/'export';export_root_study(study,destination)
    assert len(verify_bundle(destination)['files'])==7
    rows=list(csv.DictReader(io.StringIO((destination/'fixed-point-stresses.csv').read_text())))
    assert rows[0]['case']=="'@CASE" and rows[0]['point']=="'=POINT"
    expected=r['cases'][0]['positions'][0]['point_probes'][0]['values'][0]
    assert float(rows[0]['normal_mpa'])==pytest.approx(expected['resolved_mpa']['normal_mpa'])
    unavailable=[row for row in rows if row['status']!='Available']
    assert {row['status'] for row in unavailable}=={'Outside fine mesh','Operating case unassessed'}
    assert all(row['normal_mpa']==row['sigma_x_mpa']==row['element_index']=='' for row in unavailable)
    assert 'time_s' not in rows[0] and '<script>' not in root_report_html(r) and '&lt;script&gt;' in root_report_html(r)
    assert 'not fatigue histories' in root_report_html(r)
    (destination/'fixed-point-stresses.csv').write_text('tampered')
    with pytest.raises(ValueError):verify_bundle(destination)


@pytest.mark.gui
def test_probe_editor_worker_plot_and_invalidation(tmp_path):
    from PySide6.QtWidgets import QApplication,QTableWidgetItem
    from gearforge.root_ui import RootStressDialog
    app=QApplication.instance() or QApplication([]);study=small_study();dialog=RootStressDialog(study=study);errors=[]
    dialog.show_error=lambda error:errors.append(str(error));dialog.show();app.processEvents()
    assert asdict(dialog.read_study())==asdict(study)
    dialog.add_probe();assert dialog.probe_table.rowCount()==3 and dialog.dirty
    dialog.remove_probe();assert dialog.probe_table.rowCount()==2
    assert dialog.calculate() and not dialog.probe_table.isEnabled()
    deadline=time.monotonic()+60
    while dialog.process is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert dialog.process is None and not errors and dialog.probe_table.isEnabled()
    dialog.tabs.setCurrentIndex(7);app.processEvents();assert dialog.probe_plot.rendered_items==12
    assert not dialog.grab().isNull()
    dialog.probe_selector.setCurrentIndex(1);app.processEvents();assert dialog.probe_plot.rendered_items==12
    dialog.probe_table.setItem(0,1,QTableWidgetItem('-2.5'));assert dialog.result is None and dialog.dirty
    assert dialog.probe_plot.result is None and dialog.read_study().probes[0].x_mm==-2.5
    dialog.read_study().save(tmp_path/'edited.gearforge-root')
    assert RootStressStudy.load(tmp_path/'edited.gearforge-root').probes[0].x_mm==-2.5
    dialog.dirty=False;dialog.close();app.processEvents()
