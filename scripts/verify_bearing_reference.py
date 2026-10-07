"""Independent high-precision arithmetic for original synthetic bearing cases.

Uses Decimal from the Python standard library, no restricted tables or reference
implementation. This verifies formulas/arithmetic, not supplier factors or life.
"""
from dataclasses import asdict
from decimal import Decimal, localcontext
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gearforge.bearings import synthetic_bearing_example,calculate_bearing_study
from gearforge.shafts import ShaftStudy,ShaftCase,ShaftLoad
from gearforge.models import atomic_text


def reference_cases():
    # speed, hours, applied radial force magnitude, applied axial force, load X.
    return [
        ('ball-constant','deep_groove_ball',[(1000,1,200,0,60)],None),
        ('ball-reverse-stop','deep_groove_ball',[(1000,1,200,0,60),(-500,2,400,0,60),(0,1,1400,0,60)],None),
        ('roller-spectrum','cylindrical_roller_radial',[(1500,3,246,0,30),(-700,2,582,0,90)],None),
        ('ball-combined','deep_groove_ball',[(1300,7,200,120,60),(-650,3,360,-200,30)],(.56,1.6,.6,.5)),
        ('ball-radial-envelope','deep_groove_ball',[(1000,2,200,5,60)],(1,0,.6,.5)),
        ('ball-stationary','deep_groove_ball',[(0,1,400,0,60)],None),
        ('ball-unloaded','deep_groove_ball',[(1000,1,0,0,60)],None),
    ]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'build/bearing-reference-comparison.json')
    parser.add_argument('--write-fixture',type=Path);args=parser.parse_args()
    fixtures=[];failures=[];comparisons=0;max_relative_error=0.;max_absolute_error=0.
    with localcontext() as context:
        context.prec=60
        D=lambda value:Decimal(str(value))
        for name,kind,loads,factors in reference_cases():
            source=ShaftStudy(cases=[ShaftCase(name=f'Case {i+1}',rpm=n,duration_hours=h,
                loads=[ShaftLoad(position_mm=x,force_y_n=-force,axial_n=axial)]) for i,(n,h,force,axial,x) in enumerate(loads)])
            study=synthetic_bearing_example(source);study.name=name;study.required_hours=10000
            for bearing in study.bearings:
                bearing.kind=kind;bearing.dynamic_capacity_n=1000;bearing.static_capacity_n=1000
            if factors:
                for case in study.cases:
                    case.dynamic_x,case.dynamic_y,case.static_x,case.static_y=factors
                    case.factor_basis='Original synthetic case-specific factors; not a supplier table'
            actual=calculate_bearing_study(study);expected=[]
            exponent=D(3) if kind=='deep_groove_ball' else D(10)/D(3)
            total_time=sum(D(row[1]) for row in loads)
            for index,position in enumerate(('a','b')):
                damage_sum=D(0)
                for case_index,(n,h,force,axial,x) in enumerate(loads):
                    # Independent closed-form reactions for a 120 mm beam with
                    # one force, no applied bending couples, axial locator A.
                    radial=D(force)*(D(120)-D(x) if position=='a' else D(x))/D(120)
                    axial_load=abs(D(axial)) if position=='a' else D(0)
                    if axial_load and factors:
                        xx,y,x0,y0=map(D,factors)
                        dynamic=max(radial,xx*radial+y*axial_load)
                        static=max(radial,x0*radial+y0*axial_load)
                    else:dynamic=static=radial
                    revolutions=D(60)*abs(D(n))*D(h)
                    damage=revolutions/D(1000000)*(dynamic/D(1000))**exponent
                    damage_sum+=damage
                    values=dict(radial_load_n=radial,axial_load_n=axial_load,equivalent_dynamic_n=dynamic,
                        equivalent_static_n=static,revolutions=revolutions,cycle_damage=damage,
                        basic_l10_revolutions=None if dynamic==0 else D(1000000)*(D(1000)/dynamic)**exponent,
                        static_safety=None if static==0 else D(1000)/static)
                    for field,value in values.items():expected.append(dict(bearing=index,case=case_index,field=field,value=None if value is None else float(value)))
                for field,value in dict(cycle_damage=damage_sum,target_damage=damage_sum*D(10000)/total_time,
                    basic_l10_repeated_duty_hours=None if damage_sum==0 else total_time/damage_sum).items():
                    expected.append(dict(bearing=index,case=None,field=field,value=None if value is None else float(value)))
            for item in expected:
                row=actual['bearings'][item['bearing']]
                if item['case'] is not None:row=row['cases'][item['case']]
                got=row[item['field']];value=item['value'];comparisons+=1
                passed=got is None if value is None else got is not None and math.isclose(got,value,rel_tol=1e-10,abs_tol=1e-12)
                if got is not None and value is not None:
                    max_absolute_error=max(max_absolute_error,abs(got-value))
                    if value:max_relative_error=max(max_relative_error,abs((got-value)/value))
                if not passed:failures.append(dict(name=name,expected=item,actual=got))
            fixtures.append(dict(name=name,study=asdict(study),expected=expected))
    report=dict(reference='Original closed-form beam reactions and 60-digit Decimal bearing arithmetic',
        provenance='GearForge-authored synthetic inputs and independent adapter; Apache-2.0; Python standard library Decimal',
        scope='Equivalent loads, per-case basic life/damage/static safety, repeated-duty fatigue sums; no supplier-factor validation or physical life evidence',
        tolerance=dict(relative=1e-10,absolute=1e-12),comparisons=comparisons,
        maximum_absolute_error=max_absolute_error,maximum_relative_error=max_relative_error,
        passed=not failures,failures=failures,cases=fixtures)
    atomic_text(args.out,json.dumps(report,indent=2,allow_nan=False))
    if args.write_fixture:
        if failures:raise SystemExit('Arithmetic comparison failed; fixture not published')
        atomic_text(args.write_fixture,json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({key:report[key] for key in ('comparisons','maximum_relative_error','passed','failures')}))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
