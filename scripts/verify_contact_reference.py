"""Independent Hertz line-contact comparison with a pinned MIT SlipPY checkout.

Only the published solve_hertz_line API is called, in a separate process. No
reference source or its dependencies are bundled with GearForge. Original
fixtures and numeric results can be retained for offline regression.
"""
from dataclasses import asdict
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from gearforge.contact import synthetic_contact_example,calculate_contact_study,hertz_line
from gearforge.models import atomic_text

REFERENCE_COMMIT='a4fbb447fc494d0480661ee41ef15fdc82e7423c'
ADAPTER=r'''
import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('open_hertz_reference',Path(sys.argv[1])/'slippy/contact/hertz.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
rows=[]
for case in json.load(sys.stdin):
    r1,r2,w,e1,e2,v1,v2=case
    # Use SI units independently of GearForge's mm / MPa implementation.
    radius=1/(1/(r1*.001)+1/(r2*.001))
    result=module.solve_hertz_line(r_rel=radius,e1=e1*1e6,e2=e2*1e6,v1=v1,v2=v2,load=w*1000)
    rows.append(dict(effective_radius_mm=radius*1000,effective_modulus_mpa=float(result.e_star)/1e6,
        half_width_mm=float(result.contact_width)*1000,peak_pressure_mpa=float(result.max_pressure)/1e6))
print(json.dumps(rows,allow_nan=False))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-checkout',type=Path,required=True)
    parser.add_argument('--reference-python',type=Path,default=Path(sys.executable))
    parser.add_argument('--out',type=Path,default=ROOT/'build/contact-reference-comparison.json')
    parser.add_argument('--write-fixture',type=Path);args=parser.parse_args()
    checkout=args.reference_checkout.resolve()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()
    if commit!=REFERENCE_COMMIT:raise SystemExit('Reference checkout does not match the recorded revision')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=checkout,text=True).strip():
        raise SystemExit('Reference checkout has tracked modifications')
    if 'MIT License' not in (checkout/'LICENSE').read_text():raise SystemExit('Expected reference license missing')
    inputs=[(5,20,4,210000,210000,.3,.3),(5,20,400,210000,70000,.3,.33),
        (1.2,50,.1,190000,170000,.27,.29),(20,20,100,210000,210000,0,.49),
        (12,80,30,2500,70000,.4,.33),(200,400,1000,200000,220000,.3,.28),
        (.01,2,.00001,180000,180000,.2,.2),(1000,1000,.0001,210000,210000,.3,.3)]
    contexts=[dict(kind='cylinders',name=f'Original cylinder case {i+1}') for i in range(len(inputs))]
    studies=[]
    # The existing geometry reference suite checks involute diameters/angles.
    # This comparison checks pressure/width for the study's actual critical cuts,
    # not supplier factors, load-sharing stiffness, pitting life or edge contact.
    for module,z1,z2,shift in ((2,20,100,0),(1.5,24,72,.3),(3,30,60,.2)):
        for sharing in ('full_load_envelope','equal_pairs'):
            study=synthetic_contact_example();pair=study.source.pair
            pair.normal_module_mm=module;pair.pinion_teeth=z1;pair.wheel_teeth=z2
            pair.pinion_profile_shift=shift;pair.wheel_profile_shift=-shift
            study.load_sharing=sharing
            result=calculate_contact_study(study);assert not result['geometry_findings'],result['geometry_findings']
            case=result['cases'][0];study_index=len(studies)
            studies.append(dict(study=asdict(study),expected=[]))
            for index,node in enumerate(case['profile']):
                if not node['critical']:continue
                inputs.append((node['pinion_curvature_mm'],node['wheel_curvature_mm'],node['line_load_n_per_mm'],210000,210000,.3,.3))
                contexts.append(dict(kind='gear_cut',study=study_index,profile_index=index))
    process=subprocess.run([str(args.reference_python.resolve()),'-c',ADAPTER,str(checkout)],input=json.dumps(inputs),
        capture_output=True,text=True,timeout=60,check=True)
    expected=json.loads(process.stdout);failures=[];comparisons=0;max_relative=0.;cylinders=[]
    for values,context,reference in zip(inputs,contexts,expected,strict=True):
        if context['kind']=='cylinders':actual=hertz_line(*values)
        else:
            from gearforge.contact import ContactStudy
            result=calculate_contact_study(ContactStudy.from_dict(studies[context['study']]['study']))
            actual=result['cases'][0]['profile'][context['profile_index']]
        for key,value in reference.items():
            got=actual[key];comparisons+=1
            if not math.isclose(got,value,rel_tol=1e-10,abs_tol=1e-12):failures.append(dict(context=context,field=key,expected=value,actual=got))
            if value:max_relative=max(max_relative,abs((got-value)/value))
        if context['kind']=='cylinders':cylinders.append(dict(inputs=values,expected=reference))
        else:studies[context['study']]['expected'].append(dict(profile_index=context['profile_index'],values=reference))
    report=dict(reference='https://github.com/FrictionTribologyEnigma/slippy',reference_commit=commit,reference_license='MIT',
        scope='Effective modulus/radius, Hertz contact half-width and peak pressure in original cylinder cases and critical cuts of six spur-study fixtures. Does not independently validate geometry, physical sharing, factors or fatigue life.',
        provenance='Original GearForge inputs and adapter; separate pinned reference process in SI units; no reference source bundled',
        comparisons=comparisons,maximum_relative_error=max_relative,tolerance=dict(relative=1e-10,absolute=1e-12),
        passed=not failures,failures=failures,cylinder_cases=cylinders,gear_studies=studies)
    atomic_text(args.out,json.dumps(report,indent=2,allow_nan=False))
    if args.write_fixture:
        if failures:raise SystemExit('Comparison failed; fixture not written')
        atomic_text(args.write_fixture,json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({key:report[key] for key in ('comparisons','maximum_relative_error','passed','failures')}))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
