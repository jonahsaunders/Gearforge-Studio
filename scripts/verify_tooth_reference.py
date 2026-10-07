"""Independent numerical cutting check: ray/cutter intersections over rack poses.

This original adapter minimizes the first cutter intersection of each radial
ray. It never imports the application's envelope, derivatives or interpolation
in the reference process. SciPy supplies bounded optimization, not gear data.
"""
from dataclasses import asdict
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from gearforge.tooth_profile import RackProfile, synthetic_profile_example
from gearforge.models import atomic_text

ADAPTER=r'''
import json,math,sys
import scipy
from scipy.optimize import minimize_scalar

def reference(request):
    d=request['cutter'];R=d['reference_radius_mm'];a=d['alpha_rad'];h=d['depth_mm'];rho=d['radius_mm']
    shift=d['shift_mm'];pitch=d['pitch_mm'];s0=d['half_tooth_mm']
    vc=-h+rho;uc=s0+(h-rho)*math.tan(a)+rho/math.cos(a);vj=vc-rho*math.sin(a)
    def ray_entry(phi,theta):
        sx,sy=math.sin(phi+theta),math.cos(phi+theta)
        candidates=[]
        if sy>0:
            r=(R+shift-h)/sy;u=r*sx-R*theta
            if uc-1e-10<=u<=pitch-uc+1e-10:candidates.append(r)
        for side in (1,-1):
            center_u=uc if side==1 else pitch-uc
            cx=center_u+R*theta;cy=R+shift+vc
            projection=cx*sx+cy*sy;disc=projection**2-cx*cx-cy*cy+rho*rho
            if disc>=0:
                r=projection-math.sqrt(disc);u=r*sx-R*theta;v=r*sy-R-shift
                psi=math.atan2(vc-v,side*(center_u-u))
                if r>0 and a-1e-9<=psi<=math.pi/2+1e-9:candidates.append(r)
            # Left edge u+v*tan(a)=s0; right edge -u+v*tan(a)=s0-pitch.
            denominator=side*sx+sy*math.tan(a)
            if denominator>1e-12:
                r=(s0-(pitch if side<0 else 0)+side*R*theta+(R+shift)*math.tan(a))/denominator
                if r>0 and r*sy-R-shift>=vj-1e-10:candidates.append(r)
        return min(candidates,default=1e100)
    values=[]
    for phi in request['angles_rad']:
        low,high=-1-math.pi/d['teeth'],1.
        grid=[low+(high-low)*i/800 for i in range(801)]
        samples=[ray_entry(phi,t) for t in grid]
        best=min(samples)
        for i in range(1,800):
            if samples[i]<=samples[i-1] and samples[i]<=samples[i+1] and samples[i]<1e50:
                solved=minimize_scalar(lambda t:ray_entry(phi,t),bounds=(grid[i-1],grid[i+1]),method='bounded',options={'xatol':1e-14})
                best=min(best,float(solved.fun))
        if best>=1e50:raise RuntimeError('No independent cutter intersection')
        values.append(best)
    return values
print(json.dumps({'scipy_version':scipy.__version__,'radii_mm':[reference(r) for r in json.load(sys.stdin)]},allow_nan=False))
'''


def fixtures():
    result=[]
    for name,role,module,z,shift,alpha,depth,radius,reduction in [
        ('Development pinion','pinion',2,20,0,20,1.25,.38,0),
        ('Development wheel','wheel',2,100,0,20,1.25,.38,0),
        ('Positive shift avoids low-tooth undercut','pinion',2,12,.6,20,1.25,.3,.02),
        ('Negative shift and reduced thickness','pinion',.5,80,-.3,25,1.25,.3,.03),
        ('Deeper cutter','pinion',5,60,0,20,1.4,.1,0),
        ('Positive shift with large corner','pinion',2,70,.95,20,1.25,.38,0),
        ('Shallow cutter','pinion',1,80,0,15,.7,.1,0),
    ]:
        study=synthetic_profile_example();study.name=name;study.role=role
        pair=study.source.pair;pair.normal_module_mm=module;pair.normal_pressure_angle_deg=alpha
        setattr(pair,role+'_teeth',z);setattr(pair,role+'_profile_shift',shift)
        study.cutter_depth_coefficient=depth;study.cutter_tip_radius_coefficient=radius;study.tooth_thickness_reduction_mm=reduction
        profile=RackProfile(study)
        # Interior rays in every curved/flat generated region, plus both joins.
        angles=[profile.phia+(profile.phij-profile.phia)*i/12 for i in range(1,13)]
        angles += [profile.phij+(profile.phif-profile.phij)*i/20 for i in range(1,21)]
        angles += [profile.phif+(math.pi/profile.z-profile.phif)*i/6 for i in range(1,7)]
        cutter=dict(reference_radius_mm=profile.R,alpha_rad=profile.alpha,depth_mm=profile.h,
            radius_mm=profile.rho,shift_mm=profile.shift,pitch_mm=math.pi*profile.m,
            half_tooth_mm=profile.s0,teeth=profile.z)
        result.append(dict(name=name,study=asdict(study),cutter=cutter,angles_rad=angles))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-python',default=sys.executable)
    parser.add_argument('--out',type=Path,default=ROOT/'build/tooth-reference-comparison.json')
    parser.add_argument('--write-fixture',action='store_true');args=parser.parse_args()
    cases=fixtures()
    reference=json.loads(subprocess.run([args.reference_python,'-c',ADAPTER],input=json.dumps(cases),text=True,capture_output=True,check=True).stdout)
    count=0;maximum=0.
    for case,radii in zip(cases,reference['radii_mm'],strict=True):
        from gearforge.tooth_profile import ToothProfileStudy
        profile=RackProfile(ToothProfileStudy.from_dict(case['study']))
        case['expected_radii_mm']=radii
        for angle,expected in zip(case['angles_rad'],radii,strict=True):
            actual=profile.radius_at_angle(angle);error=abs(actual-expected);maximum=max(maximum,error);count+=1
            if not math.isclose(actual,expected,rel_tol=2e-9,abs_tol=2e-7):
                raise ValueError(f"{case['name']}: ray {angle} differs: {actual} vs {expected}")
    result=dict(passed=True,comparisons=count,reference='Independent ray intersections and SciPy bounded pose minimization',
        scipy_version=reference['scipy_version'],reference_license='BSD-3-Clause',
        maximum_absolute_error_mm=maximum,tolerance=dict(relative=2e-9,absolute_mm=2e-7),
        scope='Original seven non-undercut spur cutter fixtures; geometry only, no manufacturing or strength qualification.',cases=cases)
    args.out.parent.mkdir(parents=True,exist_ok=True);atomic_text(args.out,json.dumps(result,indent=2,allow_nan=False))
    if args.write_fixture:atomic_text(ROOT/'tests/data/open_tooth_reference.json',json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))


if __name__=='__main__':main()
