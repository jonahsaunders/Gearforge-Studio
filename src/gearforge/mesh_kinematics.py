"""Nominal external-spur engagement geometry in a common right-handed frame.

No elastic approach, pressure, profile error, backlash reversal or dynamic load
is solved here. This defines the contact candidates for the loaded-cycle model.
"""
import math

from .models import finite


def spur_mesh_contacts(pinion,wheel,center_distance_mm,mesh_phase,direction='forward'):
    """Enumerate contacts after mesh_phase base pitches from tooth-zero entry.

    Centers are (0,0) and (0,center_distance). Both gears use +X right, +Y up,
    and positive torque counterclockwise. Tooth-local angles and returned body
    rotations increase clockwise. Forward is counterclockwise pinion motion.
    """
    center=finite(center_distance_mm,'Center distance mm',.001,100000)
    phase=finite(mesh_phase,'Elapsed mesh pitches',0,1000000)
    if direction not in ('forward','reverse'):raise ValueError('Choose forward or reverse rotation')
    pitch=2*math.pi*pinion.rb/pinion.z;other_pitch=2*math.pi*wheel.rb/wheel.z
    if not math.isclose(pitch,other_pitch,rel_tol=1e-11,abs_tol=1e-12):
        raise ValueError('Mating involute base pitches must agree')
    cosine=(pinion.rb+wheel.rb)/center
    if not 0<cosine<1:raise ValueError('Operating center distance must exceed the sum of base radii')
    pressure=math.acos(cosine);sine=math.sin(pressure)
    length=center*sine;lower=length-math.sqrt(wheel.ra**2-wheel.rb**2)
    upper=math.sqrt(pinion.ra**2-pinion.rb**2)
    start_p=math.sqrt(max(0.,pinion.rj**2-pinion.rb**2));start_w=math.sqrt(max(0.,wheel.rj**2-wheel.rb**2))
    tolerance=1e-10*max(1.,pinion.m,wheel.m)
    if lower<start_p-tolerance or length-upper<start_w-tolerance or upper<=lower:
        raise ValueError('Nominal engagement extends below a generated involute or has no active path')
    pitch_radius_p=center*pinion.rb/(pinion.rb+wheel.rb)
    pitch_radius_w=center*wheel.rb/(pinion.rb+wheel.rb)
    pitch_roll=pitch_radius_p*sine;reference_roll=lower+phase*pitch
    sign=1 if direction=='forward' else -1
    beta_p=sign*(pinion.flank_angle(pitch_radius_p)-(reference_roll-pitch_roll)/pinion.rb)
    beta_w=sign*(math.pi+wheel.flank_angle(pitch_radius_w)+(reference_roll-pitch_roll)/wheel.rb)
    first=math.ceil((reference_roll-upper)/pitch-1e-10)
    last=math.floor((reference_roll-lower)/pitch+1e-10)
    contacts=[]
    for sequence in range(first,last+1):
        roll=reference_roll-sequence*pitch
        if roll<lower-tolerance or roll>upper+tolerance:continue
        roll=min(upper,max(lower,roll));other=length-roll
        radius_p=math.hypot(pinion.rb,roll);radius_w=math.hypot(wheel.rb,other)
        p=pinion.flank(radius_p);w=wheel.flank(radius_w)
        contacts.append(dict(sequence_index=sequence,pinion_tooth_index=(sign*sequence)%pinion.z,
            wheel_tooth_index=(-sign*sequence)%wheel.z,pinion_roll_mm=roll,wheel_roll_mm=other,
            pinion_path_fraction=(roll-lower)/(upper-lower),wheel_path_fraction=(upper-roll)/(upper-lower),
            point_mm=[sign*(pitch_roll-roll)*cosine,pitch_radius_p+(roll-pitch_roll)*sine],
            pinion_local_point_mm=[-sign*p[0],p[1]],wheel_local_point_mm=[-sign*w[0],w[1]],
            at_entry=abs(roll-lower)<=tolerance,at_exit=abs(roll-upper)<=tolerance))
    return dict(mesh_phase=phase,direction=direction,flank='left' if sign>0 else 'right',
                operating_pressure_angle_rad=pressure,base_pitch_mm=pitch,active_path_mm=upper-lower,
                nominal_contact_ratio=(upper-lower)/pitch,continuous_nominal_contact=upper-lower>=pitch,
                pinion_clockwise_rotation_rad=beta_p,wheel_clockwise_rotation_rad=beta_w,
                normal_on_pinion=[sign*cosine,-sine],normal_on_wheel=[-sign*cosine,sine],contacts=contacts)
