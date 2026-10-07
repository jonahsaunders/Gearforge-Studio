from dataclasses import asdict
import json
import math
from pathlib import Path

import pytest

from gearforge.engineering import EngineeringStudy, GearPair, DutyPoint
from gearforge.maintenance import verify_bundle
from gearforge.shafts import (ShaftStudy,ShaftSection,ShaftCase,ShaftLoad,solve_shaft_case,
                             calculate_shaft_study,shaft_from_gear_study,export_shaft_study,shaft_report_html)


def test_central_load_hand_solution():
    study=ShaftStudy(); result=solve_shaft_case(study)
    section=study.sections[0]; ei=section.youngs_modulus_mpa*math.pi*12**4/64
    assert [b['radial_load_n'] for b in result['bearings']]==[50,50]
    assert result['maxima']['bending_moment_magnitude_nm']['value']==3
    assert result['maxima']['deflection_magnitude_mm']['value']==pytest.approx(100*120**3/(48*ei))
    assert result['bearings'][0]['slope_magnitude_rad']==pytest.approx(100*120**2/(16*ei))
    assert result['load_stations'][0]['deflection_y_mm']<0
    assert result['maxima']['nominal_surface_von_mises_mpa']['value']==pytest.approx(32*3000/(math.pi*12**3))
    assert all(abs(v)<1e-10 for v in result['equilibrium_residual'].values())


def test_asymmetric_load_extreme_is_not_at_load_or_a_drawing_sample():
    study=ShaftStudy(cases=[ShaftCase(loads=[ShaftLoad(position_mm=30,force_y_n=-100)])])
    result=solve_shaft_case(study)
    expected_x=120-math.sqrt((120**2-30**2)/3)
    extreme=result['maxima']['deflection_magnitude_mm']
    assert extreme['position_mm']==pytest.approx(expected_x)
    ei=200000*math.pi*12**4/64
    y=100*30*(120-expected_x)*(120**2-30**2-(120-expected_x)**2)/(6*120*ei)
    assert extreme['value']==pytest.approx(y)
    assert extreme['value']>max(point['deflection_magnitude_mm'] for point in result['samples'])


def test_overhang_and_physical_couple_reactions():
    study=ShaftStudy(bearing_a_mm=20,bearing_b_mm=100,
        cases=[ShaftCase(loads=[ShaftLoad(position_mm=120,force_y_n=-100)])])
    result=solve_shaft_case(study)
    assert [b['reaction_on_shaft_y_n'] for b in result['bearings']]==[-25,125]
    assert result['maxima']['bending_moment_magnitude_nm']['value']==pytest.approx(2)
    study.cases[0].loads=[ShaftLoad(position_mm=120,moment_z_nm=1,moment_y_nm=2)]
    result=solve_shaft_case(study)
    assert result['bearings'][0]['reaction_on_shaft_y_n']==pytest.approx(12.5)
    assert result['bearings'][0]['reaction_on_shaft_z_n']==pytest.approx(-25)
    assert all(abs(v)<1e-10 for v in result['equilibrium_residual'].values())


def test_axial_extension_hollow_torsion_and_locator_boundary():
    study=ShaftStudy(sections=[ShaftSection(outer_diameter_mm=20,inner_diameter_mm=10)],
        cases=[ShaftCase(loads=[ShaftLoad(name='input',position_mm=0,torque_nm=10),
                              ShaftLoad(name='output',position_mm=120,axial_n=500,torque_nm=-10)])])
    result=solve_shaft_case(study); section=study.sections[0]
    assert result['bearings'][0]['axial_load_n']==500
    assert result['bearings'][1]['axial_load_n']==0
    end=result['load_stations'][1]
    assert end['axial_displacement_mm']==pytest.approx(500*120/(200000*math.pi*(20**2-10**2)/4))
    assert end['twist_rad']==pytest.approx(-10000*120/(section.shear_modulus_mpa*math.pi*(20**4-10**4)/32))
    assert end['nominal_surface_torsion_mpa']==pytest.approx(16*10000*20/(math.pi*(20**4-10**4)))
    study.axial_locator='b'
    result=solve_shaft_case(study)
    assert result['bearings'][1]['axial_load_n']==500
    assert result['load_stations'][1]['axial_displacement_mm']==0


def test_plane_rotation_and_force_scaling():
    study=ShaftStudy()
    baseline=solve_shaft_case(study)
    load=study.cases[0].loads[0]
    load.force_y_n=-200*math.cos(.7);load.force_z_n=-200*math.sin(.7)
    rotated=solve_shaft_case(study)
    for key in baseline['maxima']:
        assert rotated['maxima'][key]['value']==pytest.approx(2*baseline['maxima'][key]['value'])
    study.sections[0].outer_diameter_mm*=2
    larger=solve_shaft_case(study)
    assert larger['maxima']['deflection_magnitude_mm']['value']==pytest.approx(rotated['maxima']['deflection_magnitude_mm']['value']/16)
    assert larger['maxima']['nominal_surface_von_mises_mpa']['value']==pytest.approx(rotated['maxima']['nominal_surface_von_mises_mpa']['value']/8)


def test_gears_transfer_axial_thrust_couple_and_all_duty_cases():
    source=EngineeringStudy(pair=GearPair(pinion_helix_angle_deg=20),duty=[
        DutyPoint(name='forward',duration_hours=7000),
        DutyPoint(name='reverse',input_rpm=-1500,input_torque_nm=-2,duration_hours=3000)])
    pinion=shaft_from_gear_study(source,'pinion')
    wheel=shaft_from_gear_study(source,'wheel')
    assert len(pinion.cases)==len(wheel.cases)==2
    p,w=pinion.cases[0].loads[0],wheel.cases[0].loads[0]
    assert (p.axial_n,p.force_y_n,p.force_z_n)==(-w.axial_n,-w.force_y_n,-w.force_z_n)
    assert p.moment_z_nm<0 and w.moment_z_nm==pytest.approx(p.moment_z_nm*5)
    assert w.torque_nm==pytest.approx(p.torque_nm*5)
    assert wheel.cases[0].rpm==-300
    assert p.axial_n>0>pinion.cases[1].loads[0].axial_n
    for study in (pinion,wheel):
        result=calculate_shaft_study(study)
        assert result['total_hours']==10000 and not result['production_approved']
        assert result['rated_life_hours'] is None
        assert all(abs(v)<1e-9 for case in result['cases'] for v in case['equilibrium_residual'].values())


@pytest.mark.parametrize('change',[
    {'bearing_a_mm':120},{'bearing_b_mm':float('nan')},{'axial_locator':'both'},
    {'length_mm':0},{'length_mm':100},{'cases':[]},{'sections':[]},{'schema_version':True},
    {'sections':[ShaftSection(end_mm=50),ShaftSection(start_mm=51)]},
    {'sections':[ShaftSection(inner_diameter_mm=12)]},
    {'sections':[ShaftSection(youngs_modulus_mpa=True)]},
    {'cases':[ShaftCase(loads=[ShaftLoad(torque_nm=1)])]},
    {'cases':[ShaftCase(loads=[ShaftLoad(position_mm=-1)])]},
    {'cases':[ShaftCase(loads=[ShaftLoad(force_y_n=float('inf'))])]},
    {'cases':[ShaftCase(),ShaftCase()]},
])
def test_invalid_models_do_not_calculate(change):
    with pytest.raises(ValueError):calculate_shaft_study(ShaftStudy(**change))


def test_saved_inputs_are_strict_and_source_is_provenance(tmp_path):
    study=shaft_from_gear_study(EngineeringStudy())
    path=tmp_path/'shaft.gearforge-shaft';study.save(path)
    loaded=ShaftStudy.load(path)
    assert asdict(study)==asdict(loaded)
    original=calculate_shaft_study(study)
    loaded.cases[0].loads[0].force_y_n*=2
    edited=calculate_shaft_study(loaded)
    assert original['study_sha256']!=edited['study_sha256']
    assert original['inputs']['source_study']==edited['inputs']['source_study']
    invalid=asdict(study);del invalid['sections'][0]['youngs_modulus_mpa']
    with pytest.raises(ValueError,match='Missing'):ShaftStudy.from_dict(invalid)
    before=path.read_bytes();study.cases[0].loads[0].torque_nm=999
    with pytest.raises(ValueError):study.save(path)
    assert path.read_bytes()==before


def test_shaft_export_integrity_and_safe_text(tmp_path):
    study=ShaftStudy(name='<script>unsafe()</script> 齿轮')
    result=calculate_shaft_study(study)
    assert '<script>' not in shaft_report_html(result)
    assert '&lt;script&gt;' in shaft_report_html(result)
    destination=tmp_path/'out';export_shaft_study(study,destination)
    assert verify_bundle(destination)['kind']=='gearforge-shaft-study'
    with pytest.raises(FileExistsError):export_shaft_study(study,destination)
    (destination/'calculation.json').write_text('changed')
    with pytest.raises(ValueError):verify_bundle(destination)


def test_compression_and_large_deformation_are_reported():
    study=ShaftStudy(cases=[ShaftCase(loads=[ShaftLoad(position_mm=120,axial_n=-1000),
                                           ShaftLoad(name='bending',force_y_n=-1e6)])])
    result=solve_shaft_case(study)
    assert any('Compression' in item for item in result['findings'])
    assert any('Small-deflection' in item for item in result['findings'])


def test_cli_shaft_transfer_calculation_and_replay(tmp_path):
    from gearforge.cli import main
    shaft=tmp_path/'shaft.gearforge-shaft';source=tmp_path/'gear.gearforge-study'
    EngineeringStudy().save(source)
    assert main(['shaft','new',str(shaft)])==0
    assert main(['shaft','new',str(shaft)])==1
    assert main(['shaft','from-study',str(source),'--role','wheel','--out',str(tmp_path/'wheel.gearforge-shaft')])==0
    assert ShaftStudy.load(tmp_path/'wheel.gearforge-shaft').cases[0].rpm==-300
    destination=tmp_path/'calculation'
    assert main(['shaft','calculate',str(shaft),'--out',str(destination)])==0
    assert main(['verify',str(destination)])==0
    assert ShaftStudy.load(destination/'design.gearforge-shaft')==ShaftStudy.load(shaft)


@pytest.mark.gui
def test_shaft_editor_rename_case_invalidation_and_failed_save(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from gearforge.shaft_ui import ShaftStudyDialog
    app=QApplication.instance() or QApplication([])
    dialog=ShaftStudyDialog(study=shaft_from_gear_study(EngineeringStudy()))
    errors=[];dialog.show_error=lambda error:errors.append(str(error))
    dialog.show();app.processEvents()
    assert dialog.calculate()
    for index in range(dialog.tabs.count()):
        dialog.tabs.setCurrentIndex(index);app.processEvents()
        assert not dialog.grab().isNull()
    dialog.cases.item(0,0).setText('Renamed duty')
    assert dialog.read_study().cases[0].name=='Renamed duty'
    assert len(dialog.read_study().cases[0].loads)==2
    assert dialog.result is None and not dialog.report.toPlainText() and dialog.dirty
    assert dialog.calculate()
    old=tmp_path/'old.gearforge-shaft';dialog.path=old
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(tmp_path/'new.gearforge-shaft'),''))
    def failed(*args):raise OSError('Disk full')
    monkeypatch.setattr(ShaftStudy,'save',failed)
    assert not dialog.save_study() and dialog.dirty and dialog.path==old
    assert errors==['Disk full']
    dialog.dirty=False;dialog.close();app.processEvents()


def test_independent_finite_element_reference():
    fixture=json.loads((Path(__file__).parent/'data/open_shaft_reference.json').read_text(encoding='utf-8'))
    assert fixture['reference_version']=='3.2.0' and fixture['passed']
    for case in fixture['cases']:
        result=solve_shaft_case(ShaftStudy.from_dict(case['study']))
        points={point['position_mm']:point for point in result['samples']}
        for expected in case['expected']:
            if expected['kind']=='reaction':
                actual=result['bearings'][expected['bearing_index']][f"reaction_on_shaft_{expected['plane']}_n"]
            else:
                actual=points[expected['position_mm']][expected['field']]
            assert actual==pytest.approx(expected['value'],rel=1e-8,abs=1e-8),(case['name'],expected)
