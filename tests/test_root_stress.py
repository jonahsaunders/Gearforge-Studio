from dataclasses import asdict
import copy
import json
from pathlib import Path
import time

import numpy as np
import pytest

from gearforge.maintenance import verify_bundle
from gearforge.root_stress import (RootStressStudy,synthetic_root_example,root_from_profile,RackProfile,
    load_patches,root_mesh,patch_forces,solve_root_mesh,calculate_root_study,export_root_study,root_report_html,root_csv_files,root_mesh_vtk)


@pytest.fixture(scope='module')
def full_result():return calculate_root_study(synthetic_root_example())


def small_study():
    s=synthetic_root_example();s.sector_teeth=3;s.angular_divisions_per_tooth=8;s.radial_layers=4;s.load_positions=[.5];return s


def test_full_synthetic_refinement_and_sector_sensitivity(full_result):
    r=full_result
    assert r['calculation_available'] and r['mesh_convergence_passed'] and r['domain_sensitivity_passed']
    assert [m['refinement'] for m in r['mesh_levels']]==[1,2,4]
    assert r['domain_check']['sector_teeth']==9
    assert [p['root_von_mises_mpa'] for p in r['cases'][0]['positions']]==pytest.approx([5.110810765426473,5.912949449496781,8.183902564948463],rel=1e-7)
    assert not r['production_approved'] and r['rated_output_torque_nm'] is None and r['rated_gearbox_life_hours'] is None
    assert not r['cases'][0]['declared_input_evidence_complete'] and r['cases'][0]['numerical_checks_passed']
    for response in r['mesh_levels'][-1]['responses']:
        assert response['relative_equation_residual']<1e-7
        assert max(abs(v) for v in response['force_balance_n'])<1e-9
        assert abs(response['moment_balance_n_mm'])<1e-8


def test_load_patch_torque_mirror_symmetry_width_and_modulus_scaling():
    s=small_study();p=RackProfile(s.source);patches=load_patches(s,p);mesh=root_mesh(s,p,patches)
    for flank,sign in [('left',-1),('right',1)]:
        forces=patch_forces(s,p,mesh,patches[0],flank).reshape(-1,2)
        assert np.sum(mesh['nodes'][:,0]*forces[:,1]-mesh['nodes'][:,1]*forces[:,0])==pytest.approx(sign,abs=1e-13)
    base=solve_root_mesh(s,p,patches,1);a,b=base['responses']
    for key in ('root_von_mises_mpa_per_n_mm','root_tensile_mpa_per_n_mm','compliance_per_n_mm'):
        assert a[key]==pytest.approx(b[key],rel=1e-8)
    s.youngs_modulus_mpa*=2;stiffer=solve_root_mesh(s,p,patches,1)['responses'][0]
    assert stiffer['root_von_mises_mpa_per_n_mm']==pytest.approx(a['root_von_mises_mpa_per_n_mm'])
    assert stiffer['maximum_displacement_mm_per_n_mm']==pytest.approx(a['maximum_displacement_mm_per_n_mm']/2)
    s.youngs_modulus_mpa/=2;s.effective_face_width_mm/=2;narrow=solve_root_mesh(s,p,patches,1)['responses'][0]
    assert narrow['root_von_mises_mpa_per_n_mm']==pytest.approx(2*a['root_von_mises_mpa_per_n_mm'])


@pytest.mark.parametrize('change',[
    lambda s:setattr(s,'youngs_modulus_mpa',None),lambda s:setattr(s,'support_radius_mm',18),
    lambda s:setattr(s.source.source.pair,'pinion_teeth',12),lambda s:setattr(s.source.source.pair,'pinion_helix_angle_deg',10),
    lambda s:setattr(s,'load_positions',[1.]),lambda s:setattr(s,'patch_half_width_mm',5),
])
def test_unknown_or_unsupported_model_remains_unavailable(change):
    s=small_study();change(s);r=calculate_root_study(s)
    assert not r['calculation_available'] and not r['mesh_levels'] and not r['production_approved']
    assert r['findings']


@pytest.mark.parametrize('field,value',[('schema_version',True),('sector_teeth',4),('load_positions',[.5,.2]),
    ('poisson_ratio',float('inf')),('material_status','certified'),('effective_face_width_mm',21),('angular_divisions_per_tooth',1)])
def test_strict_input_validation(field,value):
    s=small_study();setattr(s,field,value)
    with pytest.raises(ValueError):s.validate()


def cached_meshes(monkeypatch,result):
    import gearforge.root_stress as module
    def solve(study,profile,patches,refinement,sector_teeth=None,keep_fields=False):
        if sector_teeth:return {k:v for k,v in result['domain_check'].items() if k!='changes_percent'}
        return result['mesh_levels'][(1,2,4).index(refinement)]
    monkeypatch.setattr(module,'solve_root_mesh',solve)


def test_evidence_unknowns_reversals_zero_torque_and_temperature(full_result,monkeypatch):
    cached_meshes(monkeypatch,full_result)
    s=synthetic_root_example();s.material_status='declared';s.cases[0].temperature_c=None
    r=calculate_root_study(s);assert r['cases'][0]['positions'] and not r['cases'][0]['declared_input_evidence_complete']
    s.cases[0].temperature_c=100
    assert not calculate_root_study(s)['cases'][0]['positions']
    s.cases[0].temperature_c=40;s.cases[0].load_share=None
    assert not calculate_root_study(s)['cases'][0]['positions']
    s.cases[0].load_share=1;s.source.source.duty[0].input_torque_nm*=-1;s.source.source.duty[0].input_rpm*=-1
    r=calculate_root_study(s);assert r['cases'][0]['flank']=='right' and not r['cases'][0]['declared_input_evidence_complete']
    assert r['cases'][0]['positions'][1]['root_von_mises_mpa']==pytest.approx(full_result['cases'][0]['positions'][1]['root_von_mises_mpa'],rel=1e-7)
    s.source.data_status='declared'
    assert calculate_root_study(s)['cases'][0]['declared_input_evidence_complete']
    s.source.cutter_reference=''
    assert not calculate_root_study(s)['cases'][0]['declared_input_evidence_complete']
    s.source.source.duty[0].input_torque_nm=0
    assert all(p['root_von_mises_mpa']==0 for p in calculate_root_study(s)['cases'][0]['positions'])


def test_mesh_threshold_and_domain_failure_preserve_fields(full_result,monkeypatch):
    cached_meshes(monkeypatch,full_result);s=synthetic_root_example();s.convergence_tolerance_percent=.1
    r=calculate_root_study(s);assert not r['mesh_convergence_passed'] and not r['domain_sensitivity_passed']
    import gearforge.root_stress as module
    def no_wider(study,profile,patches,refinement,sector_teeth=None,keep_fields=False):
        if sector_teeth:raise ValueError('Mesh limit')
        return full_result['mesh_levels'][(1,2,4).index(refinement)]
    monkeypatch.setattr(module,'solve_root_mesh',no_wider)
    r=calculate_root_study(s);assert r['calculation_available'] and r['domain_sensitivity_passed'] is None and r['cases'][0]['positions']


def test_transfer_roundtrip_export_integrity_and_vtk(tmp_path,full_result,monkeypatch):
    s=synthetic_root_example();p=tmp_path/'example.gearforge-root';s.save(p)
    assert asdict(RootStressStudy.load(p))==asdict(s)
    transferred=root_from_profile(s.source);assert transferred.source is not s.source and transferred.youngs_modulus_mpa is None
    bad=asdict(s);bad['production_approved']=True
    with pytest.raises(ValueError):RootStressStudy.from_dict(bad)
    cached_meshes(monkeypatch,full_result);out=tmp_path/'assessment';export_root_study(s,out)
    manifest=verify_bundle(out);assert len(manifest['files'])==6
    r=json.loads((out/'calculation.json').read_text());assert r['mesh_export_view']['case_name']==s.cases[0].case_name
    from vtkmodules.vtkIOLegacy import vtkUnstructuredGridReader
    from vtkmodules.util.numpy_support import vtk_to_numpy
    reader=vtkUnstructuredGridReader();reader.SetFileName(str(out/'mesh.vtk'));reader.Update();grid=reader.GetOutput()
    assert grid.GetNumberOfCells()==r['mesh_levels'][-1]['elements'] and grid.GetCellType(0)==28
    assert grid.GetNumberOfPoints()==r['mesh_levels'][-1]['nodes']
    fields=vtk_to_numpy(grid.GetPointData().GetVectors());vm=vtk_to_numpy(grid.GetCellData().GetScalars())
    expected=r['cases'][0]['positions'][0]
    assert np.linalg.norm(fields,axis=1).max()==pytest.approx(expected['maximum_displacement_mm'])
    assert vm.max()==pytest.approx(expected['domain_gauss_von_mises_mpa'])
    assert np.max(abs(fields[r['mesh_levels'][-1]['mesh']['fixed_node_indices']]))==0
    with pytest.raises(FileExistsError):export_root_study(s,out)
    (out/'mesh.vtk').write_text('tampered')
    with pytest.raises(ValueError):verify_bundle(out)


def test_html_csv_escaping_and_no_fields_without_supported_calculation(full_result,tmp_path):
    r=copy.deepcopy(full_result);r['inputs']['name']='<script>unsafe</script>';r['cases'][0]['name']='=HYPERLINK("evil")'
    assert '<script>' not in root_report_html(r)
    cases,curves=root_csv_files(r);assert "'=HYPERLINK" in cases and 'mpa_per_n_mm' in curves
    out=tmp_path/'unknown';export_root_study(RootStressStudy(),out)
    assert len(verify_bundle(out)['files'])==3 and not (out/'mesh.vtk').exists()


def test_cli_create_transfer_and_calculate_unknown(tmp_path):
    from gearforge.cli import main
    p=tmp_path/'new.gearforge-root'
    assert main(['root','new',str(p)])==0 and main(['root','new',str(p)])==1
    assert main(['root','calculate',str(p),'--out',str(tmp_path/'unknown')])==0
    source=tmp_path/'profile.gearforge-tooth';synthetic_root_example().source.save(source)
    transfer=tmp_path/'transfer.gearforge-root'
    assert main(['root','from-profile',str(source),'--out',str(transfer)])==0
    assert RootStressStudy.load(transfer).youngs_modulus_mpa is None


@pytest.mark.gui
def test_editor_worker_roundtrip_cancel_invalidation_and_failed_save(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.root_ui import RootStressDialog
    app=QApplication.instance() or QApplication([]);s=small_study();dialog=RootStressDialog(study=s);errors=[]
    dialog.show_error=lambda e:errors.append(str(e));dialog.show();app.processEvents()
    assert asdict(dialog.read_study())==asdict(s) and dialog.tabs.count()==7
    assert dialog.calculate();assert dialog.process is not None and dialog.cancel.isEnabled()
    deadline=time.monotonic()+60
    while dialog.process is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert dialog.process is None and not errors and dialog.result['calculation_available']
    for index in range(7):dialog.tabs.setCurrentIndex(index);app.processEvents();assert not dialog.grab().isNull()
    dialog.tabs.setCurrentIndex(3);app.processEvents();assert dialog.plot.rendered_items>0
    dialog.view.setCurrentIndex(1);dialog.deformation.setCurrentIndex(2);app.processEvents();assert dialog.plot.rendered_items>0
    dialog.tabs.setCurrentIndex(4);app.processEvents();assert dialog.curves.rendered_items>0
    dialog.fields['youngs_modulus_mpa'].setText('invalid');assert dialog.result is None and dialog.dirty
    assert not dialog.calculate() and dialog.fields['youngs_modulus_mpa'].text()=='invalid'
    dialog.fields['youngs_modulus_mpa'].setText('210000');assert dialog.calculate();dialog.cancel_job()
    assert dialog.process is None and dialog.result is None and not dialog.cancel.isEnabled()
    old=tmp_path/'old.gearforge-root';dialog.path=old
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-root'),''))
    def fail(*args):raise OSError('Disk full')
    monkeypatch.setattr(RootStressStudy,'save',fail)
    assert not dialog.save_study() and dialog.dirty and dialog.path==old and errors[-1]=='Disk full'
    dialog.dirty=False;dialog.close();app.processEvents()
