import copy
import csv
import io
import math

import numpy as np
import pytest

from gearforge.engineering import pair_geometry
from gearforge.mesh_kinematics import spur_mesh_contacts
from gearforge.root_stress import synthetic_root_example,RackProfile,calculate_root_study,root_csv_files,root_report_html


def profiles():
    study=synthetic_root_example();pinion=RackProfile(study.source)
    study.source.role='wheel';wheel=RackProfile(study.source)
    return pinion,wheel,pair_geometry(study.source.source.pair)['operating_center_distance_mm']


def rotate(point,angle):
    return np.array([[math.cos(angle),math.sin(angle)],[-math.sin(angle),math.cos(angle)]])@point


@pytest.mark.parametrize('direction',['forward','reverse'])
def test_mating_positions_normals_and_torque_signs_over_revolutions(direction):
    p,w,center=profiles();sign=1 if direction=='forward' else -1
    for phase in np.linspace(0,w.z,181):
        r=spur_mesh_contacts(p,w,center,float(phase),direction)
        assert r['continuous_nominal_contact'] and 1<=len(r['contacts'])<=2
        for contact in r['contacts']:
            for profile,member,origin in ((p,'pinion',np.array([0,0])),(w,'wheel',np.array([0,center]))):
                local=np.array(contact[member+'_local_point_mm'])
                angle=r[member+'_clockwise_rotation_rad']+contact[member+'_tooth_index']*2*math.pi/profile.z
                point=rotate(local,angle);normal=np.array(r['normal_on_'+member])
                np.testing.assert_allclose(point+origin,contact['point_mm'],rtol=0,atol=2e-11)
                torque_arm=point[0]*normal[1]-point[1]*normal[0]
                assert torque_arm==pytest.approx(-sign*profile.rb,rel=1e-11)
                radius=float(np.linalg.norm(local))
                # Independent surface tangent: derivative of the analytic flank.
                dr=1e-6;left=np.array(profile.flank(radius-dr));right=np.array(profile.flank(radius+dr))
                tangent=(right-left)/(2*dr);tangent[0]*=-sign
                assert abs(rotate(tangent,angle)@normal)<2e-7
            np.testing.assert_allclose(np.array(r['normal_on_pinion'])+r['normal_on_wheel'],[0,0],atol=1e-14)


def test_base_pitch_shift_rotations_and_contact_events():
    p,w,center=profiles()
    a=spur_mesh_contacts(p,w,center,.17);b=spur_mesh_contacts(p,w,center,1.17)
    assert b['pinion_clockwise_rotation_rad']-a['pinion_clockwise_rotation_rad']==pytest.approx(-2*math.pi/p.z)
    assert b['wheel_clockwise_rotation_rad']-a['wheel_clockwise_rotation_rad']==pytest.approx(2*math.pi/w.z)
    for x,y in zip(a['contacts'],b['contacts'],strict=True):
        assert y['sequence_index']==x['sequence_index']+1
        np.testing.assert_allclose(x['point_mm'],y['point_mm'],atol=1e-12)
    initial=spur_mesh_contacts(p,w,center,0)
    assert any(c['at_entry'] for c in initial['contacts'])
    exiting=spur_mesh_contacts(p,w,center,initial['nominal_contact_ratio'])
    assert any(c['at_exit'] and c['sequence_index']==0 for c in exiting['contacts'])
    final=spur_mesh_contacts(p,w,center,p.z)
    assert final['pinion_clockwise_rotation_rad']-initial['pinion_clockwise_rotation_rad']==pytest.approx(-2*math.pi)
    assert final['wheel_clockwise_rotation_rad']-initial['wheel_clockwise_rotation_rad']==pytest.approx(2*math.pi*p.z/w.z)


def test_invalid_mating_geometry_and_phase():
    p,w,center=profiles()
    for args in ((p,w,center,-1),(p,w,p.rb+w.rb,0),(p,w,center,True),(p,w,center,0,'sideways')):
        with pytest.raises(ValueError):spur_mesh_contacts(*args)
    w.rb*=1.01
    with pytest.raises(ValueError,match='base pitches'):spur_mesh_contacts(p,w,center,0)


def test_driven_wheel_stress_uses_retained_external_rotation():
    s=synthetic_root_example();s.source.role='wheel';s.support_radius_mm=60.;s.sector_teeth=3
    s.angular_divisions_per_tooth=8;s.radial_layers=4;s.load_positions=[.5]
    s.source.source.duty[0].duration_hours/=2
    reverse=copy.deepcopy(s.source.source.duty[0]);reverse.name='Reverse';reverse.input_rpm*=-1;reverse.input_torque_nm*=-1
    s.source.source.duty.append(reverse);case=copy.deepcopy(s.cases[0]);case.case_name='Reverse';s.cases.append(case)
    r=calculate_root_study(s);assert r['calculation_available']
    forward,reverse=r['cases'];assert forward['flank']=='left' and reverse['flank']=='right'
    assert forward['member_speed_rpm']==pytest.approx(-300) and reverse['member_speed_rpm']==pytest.approx(300)
    assert forward['signed_mesh_torque_n_mm']<0<reverse['signed_mesh_torque_n_mm']
    assert forward['positions'][0]['root_von_mises_mpa']==pytest.approx(reverse['positions'][0]['root_von_mises_mpa'],rel=1e-8)
    rows=list(csv.DictReader(io.StringIO(root_csv_files(r)[0])))
    assert float(rows[0]['signed_mesh_torque_n_mm'])==pytest.approx(forward['signed_mesh_torque_n_mm'])
    assert float(rows[0]['member_speed_rpm'])==-300
    assert 'Signed mesh torque:' in root_report_html(r) and 'Positive is counterclockwise' in root_report_html(r)
