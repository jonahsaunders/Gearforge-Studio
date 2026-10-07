"""Compare fixed physical-point stresses with a separate BSD scikit-fem solve.

Uses the six retained original elastic fixtures, with interior, edge and vertex
points. The reference inverts its own coordinate map and differentiates its own
basis; application inverse coordinates and stress values never enter it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from verify_elastic_reference import ROOT, ADAPTER
import numpy as np
from gearforge.elasticity import PlaneElasticSystem
from gearforge.models import atomic_text
from gearforge.stress_probes import locate_point


def source_hash(case):
    return hashlib.sha256(json.dumps({k:v for k,v in case.items() if k not in ('expected','fixed_points')},
                                    sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def application_points(case, points):
    system=PlaneElasticSystem(case['nodes'],case['elements'],case['youngs_mpa'],case['poisson'],case['thickness_mm'],case['mode'])
    u=system.solve(case['forces'],case['fixed_dofs'],case['prescribed'])['displacements'][:,0]
    output=[]
    for point in points:
        locations=locate_point(system.nodes,system.elements,*point['xy_mm'])
        side=next((v for v in locations if v['element_index']==point['element_index']),None)
        if side is None:raise ValueError(f"Fixed material point omitted its containing element side: {case['name']}, {point}")
        output.append(system.stress_at(u,[side['element_index']],side['xi'],side['eta'])[0].tolist())
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-python',default=sys.executable)
    parser.add_argument('--out',type=Path,default=ROOT/'build/stress-probe-reference-comparison.json')
    parser.add_argument('--write-fixture',action='store_true');args=parser.parse_args()
    cases=json.loads((ROOT/'tests/data/open_elastic_reference.json').read_text())['cases']
    for case in cases:
        points=[];nodes=np.array(case['nodes'])
        for index,cell in enumerate(case['elements']):
            corners=nodes[cell[:4]]
            for xi,eta in ((-.67,-.31),(.24,.79),(0,0),(-1,0),(1,1)):
                weights=np.array([(1-xi)*(1-eta),(1+xi)*(1-eta),(1+xi)*(1+eta),(1-xi)*(1+eta)])/4
                points.append(dict(element_index=index,xy_mm=(weights@corners).tolist()))
        case['fixed_points']=points
    request=[{k:v for k,v in case.items() if k!='expected'} for case in cases]
    process=subprocess.run([args.reference_python,'-c',ADAPTER],input=json.dumps(request),text=True,capture_output=True)
    if process.returncode:raise RuntimeError(process.stderr)
    reference=json.loads(process.stdout);count=0;maximum=0.;stored=[]
    for case,expected in zip(cases,reference['results'],strict=True):
        actual=np.array(application_points(case,case['fixed_points']));ref=np.array(expected['fixed_point_stress'])
        if actual.shape!=ref.shape or not np.allclose(actual,ref,rtol=2e-8,atol=2e-7):
            raise ValueError(f"Fixed-point stress mismatch in {case['name']}: {np.max(abs(actual-ref))}")
        count+=actual.size;maximum=max(maximum,float(np.max(abs(actual-ref))))
        stored.append(dict(name=case['name'],elastic_case_sha256=source_hash(case),points=case['fixed_points'],expected_stress_mpa=ref.tolist()))
    result=dict(passed=True,comparisons=count,reference='https://github.com/kinnala/scikit-fem',
                reference_version=reference['reference_version'],reference_license='BSD-3-Clause',
                scope='Signed tensors at fixed interior, edge and vertex points in six original elastic fixtures. No fatigue or physical strength qualification.',
                relative_tolerance=2e-8,absolute_tolerance_mpa=2e-7,maximum_absolute_error_mpa=maximum,cases=stored)
    args.out.parent.mkdir(parents=True,exist_ok=True);atomic_text(args.out,json.dumps(result,indent=2,allow_nan=False))
    if args.write_fixture:atomic_text(ROOT/'tests/data/open_stress_probe_reference.json',json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))


if __name__=='__main__':main()
