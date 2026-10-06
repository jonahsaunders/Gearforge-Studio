import math
from dataclasses import asdict

import pytest

from gearforge.engine import synthesize
from gearforge.simulation import SimulationClock, operating_point, operating_sweep, part_motion, sampled_mesh_check, shaft_rates


def test_clock_rpm_elapsed_time_and_frame_independence():
    a,b=SimulationClock(60),SimulationClock(60)
    a.time_scale=b.time_scale=1
    a.advance(1.25)
    for delta in [.01,.03,.21,.5,.5]:b.advance(delta)
    assert a.input_angle==pytest.approx(2.5*math.pi)
    assert b.input_angle==pytest.approx(a.input_angle)
    assert b.time_s==pytest.approx(1.25)
    b.speed_factor=-1;b.advance(.25)
    assert b.input_angle==pytest.approx(2*math.pi)
    b.seek(2)
    assert b.input_angle==pytest.approx(-4*math.pi)


def test_slow_motion_changes_wall_time_not_mechanical_ratio(catalog,profile,light_requirements):
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    clock=SimulationClock(400);clock.advance(10)
    assert clock.time_s==pytest.approx(.1)
    rates=shaft_rates(c,400)
    assert rates[-1]==pytest.approx(-100)
    driver=next(item for item in c.layout if item['role']=='driver')
    driven=next(item for item in c.layout if item['role']=='driven')
    a,_=part_motion(c,driver['name'],driver['shaft'],(driver['x'],driver['y'],0),clock.input_angle)
    b,_=part_motion(c,driven['name'],driven['shaft'],(driven['x'],driven['y'],0),clock.input_angle)
    assert a*c.stages[0].driver.teeth+b*c.stages[0].driven.teeth==pytest.approx(0)


def test_planetary_willis_equation_and_planet_orbit(catalog,profile,light_requirements):
    light_requirements.families=['planetary']
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0];s=c.stages[0]
    sun,carrier=shaft_rates(c,400)
    assert (sun-carrier)*s.driver.teeth+(0-carrier)*s.driven.teeth==pytest.approx(0)
    planet=next(item for item in c.layout if item['role']=='planet')
    angle=1.7;center=(planet['x'],planet['y'],0)
    spin,(dx,dy)=part_motion(c,planet['name'],planet['shaft'],center,angle)
    assert math.hypot(center[0]+dx-c.size_mm[0]/2,center[1]+dy-c.size_mm[1]/2)==pytest.approx(s.center_mm)
    carrier_angle=angle/c.ratio
    assert (spin-carrier_angle)*s.planet.teeth+(angle-carrier_angle)*s.driver.teeth==pytest.approx(0)
    assert part_motion(c,'ring',-1,center,angle)==(0.,(0.,0.))


def test_power_balance_overload_and_motor_curve(catalog,profile,light_requirements):
    req=light_requirements;req.motor_curve=[[800,.01],[0,.12],[400,.08]]
    c=synthesize(req,profile,catalog,limit=1).candidates[0]
    p=operating_point(c,req,400)
    assert p['input_power_w']==pytest.approx(.08*400*2*math.pi/60)
    assert p['input_power_w']==pytest.approx(p['output_power_w']+p['loss_power_w'])
    assert p['output_power_w']==pytest.approx(p['available_output_nm']*p['output_rpm']*2*math.pi/60)
    assert operating_point(c,req,600)['motor_torque_nm']==pytest.approx(.045)
    assert operating_point(c,req,800,1)['status']=='Overload'
    assert operating_point(c,req,900)['status']=='Outside motor curve'
    sweep=operating_sweep(c,req)
    assert len(sweep['points'])==25 and sweep['points'][-1]['input_rpm']==800
    assert 'no inertia' in sweep['method']


@pytest.mark.cad
def test_sampled_real_tooth_intersections(catalog,profile,light_requirements):
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    result=sampled_mesh_check(asdict(c),asdict(light_requirements),asdict(profile),samples=3)
    assert result['candidate_id']==c.id and len(result['frames'])==3
    assert result['maximum_overlap_mm3']<=.05,result
    assert 'not continuous' in result['method']
    driven=next(item for item in c.layout if item['role']=='driven')
    driven['rotation_deg']+=180/c.stages[0].driven.teeth
    bad=sampled_mesh_check(asdict(c),asdict(light_requirements),asdict(profile),samples=3)
    assert bad['status']=='Interference detected' and bad['maximum_overlap_mm3']>.05


@pytest.mark.gui
def test_accessible_controls_native_appearance_and_preserved_mesh(tmp_path,catalog,profile,light_requirements):
    from PySide6.QtWidgets import QApplication,QLabel
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from gearforge.app import MainWindow
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path);w.show();app.processEvents()
    assert w.fields['input_rpm'].accessibleName()=='Input speed'
    assert any(label.buddy()==w.fields['input_rpm'] for label in w.findChildren(QLabel))
    assert w.viewer.focusPolicy()==Qt.StrongFocus
    assert 'font-family' not in app.styleSheet()
    assert not w.command_actions['Load CAD preview'].isEnabled()
    c=synthesize(light_requirements,profile,catalog,limit=1).candidates[0]
    w.viewer.set_candidate(c)
    mesh={'name':c.layout[0]['name'],'center':[0,0,0],'shaft':0,'source':'print','color':[.1,.5,.9],'vertices':[[0,0,0],[1,0,0],[0,1,0]],'triangles':[[0,1,2]]}
    w.viewer.set_meshes([mesh]);w.viewer.animate(True)
    assert w.viewer.timer.isActive() and len(w.viewer.meshes)==1
    w.viewer.reduced_motion=True;w.viewer.animate(True)
    assert not w.viewer.timer.isActive()
    w.viewer.step();assert w.viewer.phase!=0 and len(w.viewer.meshes)==1
    yaw=w.viewer.yaw;QTest.keyClick(w.viewer,Qt.Key_Right)
    assert w.viewer.yaw>yaw
    w.dirty=False;w.close();app.processEvents()
