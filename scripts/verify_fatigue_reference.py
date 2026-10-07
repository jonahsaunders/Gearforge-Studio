"""Compare shaft fatigue with a public NASA example and independent Decimal math.

RP-1123 printed pp17-19, equations 28-31. NTRS identifies the NASA-authored
work as US government work, public use permitted. Only numerical example
inputs/results are retained; no copied material/factor tables or implementation.
"""
from dataclasses import asdict
from decimal import Decimal,localcontext
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from gearforge.fatigue import nasa_example,calculate_fatigue_study,REFERENCE
from gearforge.models import atomic_text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'build/fatigue-reference-comparison.json')
    parser.add_argument('--write-fixture',type=Path);args=parser.parse_args()
    cases=[];failures=[];comparisons=0;max_relative=0.
    with localcontext() as context:
        context.prec=60;D=lambda value:Decimal(str(value))
        pi=D('3.14159265358979323846264338327950288419716939937510582097494')
        # Independent scalar formulas from the source, not the shaft beam solver.
        for diameter,torque,demand in ((55,3000,2),(56,3000,2),(55,-3000,2),(55,0,2),(50,3000,1.5)):
            study=nasa_example();study.shaft.sections[0].outer_diameter_mm=diameter;study.bending_design_factor=demand
            for case in study.shaft.cases:
                case.loads[0].torque_nm=-torque;case.loads[1].torque_nm=torque
            result=calculate_fatigue_study(study);station=result['stations'][0];expected=[];damage_sum=D(0)
            d=D(diameter);tau=D(16)*D(torque)*D(1000)/(pi*d**3)
            endpoint=D(323)*D('.4')*(1-D(3)*(tau/D(634))**2).sqrt()
            exponent=(D(1227)/endpoint).ln()/D(1000000).ln()
            for i,(moment,count) in enumerate(((2000,15000),(1500,35000),(1000,50000))):
                sigma=D(32)*D(moment)*D(1000)/(pi*d**3)
                life=((D(1227)/(D(demand)*sigma)).ln()/exponent).exp()
                damage=D(count)/life;damage_sum+=damage
                for field,value in dict(corrected_reference_strength_mpa=endpoint,exponent=exponent,cycles_to_failure=life,damage=damage).items():
                    expected.append(dict(case=i,field=field,value=float(value)))
                expected.extend([dict(case=i,stress='nominal_bending_mpa',value=float(sigma)),dict(case=i,stress='nominal_torsion_mpa',value=float(-tau))])
            expected.append(dict(case=None,field='modeled_block_damage',value=float(damage_sum)))
            for item in expected:
                row=station if item['case'] is None else station['cases'][item['case']]
                actual=row['stress'][item['stress']] if 'stress' in item else row[item['field']]
                comparisons+=1;value=item['value']
                if actual is None or not math.isclose(actual,value,rel_tol=1e-10,abs_tol=1e-12):failures.append(dict(expected=item,actual=actual,diameter_mm=diameter,torque_nm=torque))
                if actual is not None and value:max_relative=max(max_relative,abs((actual-value)/value))
            cases.append(dict(study=asdict(study),expected=expected))
        # Printed source rounds coefficient 77.8, endpoint 313/125 MPa,
        # exponent .165 and final diameter to 56 mm. Reproduce its one-step
        # Eq31 sizing with the 55 mm mean-torque correction, no hidden iteration.
        corrected_unscaled=D(323)*(1-D('77.8')*(D(3000)/(D('.055')**3*D(634000000)))**2).sqrt()
        corrected=corrected_unscaled*D('.4');b=(D(1227)/corrected).ln()/D(1000000).ln()
        def diameter_for(spectrum):
            summation=sum(D(n)/D(1000000)*D(m)**(1/b) for m,n in spectrum)
            return (D(32)*D(2)/(pi*corrected*D(1000000))*summation**b)**(D(1)/D(3))*D(1000)
        computed=dict(mean_corrected_reference_mpa=float(corrected_unscaled),corrected_reference_mpa=float(corrected),
            exponent=float(b),diameter_mm=float(diameter_for(((2000,15000),(1500,35000),(1000,50000)))),
            peak_only_diameter_mm=float(diameter_for(((2000,15000),))))
        published=dict(mean_corrected_reference_mpa=(313,.6),corrected_reference_mpa=(125,.3),exponent=(.165,.0005),
            diameter_mm=(56,.5),peak_only_diameter_mm=(54,1.0))
        for key,(value,tolerance) in published.items():
            comparisons+=1
            if abs(computed[key]-value)>tolerance:failures.append(dict(field=key,actual=computed[key],published=value,tolerance=tolerance))
    report=dict(reference=REFERENCE,source='NASA RP-1123 (1984), printed pp17-19, equations 28-31',
        provenance='Public US-government-authored reference example; original Apache-2.0 load-path adapter and independent 60-digit Decimal implementation',
        scope='Selected exact shaft cuts, steady-torque correction, finite-life exponent, block cycles/damage; published rounded one-step sizing example. No physical material qualification.',
        published_example=dict(computed=computed,rounded_values_and_absolute_tolerances=published),
        tolerance=dict(relative=1e-10,absolute=1e-12),comparisons=comparisons,maximum_relative_error=max_relative,
        passed=not failures,failures=failures,cases=cases)
    atomic_text(args.out,json.dumps(report,indent=2,allow_nan=False))
    if args.write_fixture:
        if failures:raise SystemExit('Reference comparison failed; fixture not written')
        atomic_text(args.write_fixture,json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:report[k] for k in ('comparisons','maximum_relative_error','passed','failures','published_example')}))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
