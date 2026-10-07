"""Independent checks for whole-gear elasticity and unilateral load primitives.

scikit-fem supplies separate closed-ring solves. SciPy SLSQP identifies contact
sets, then the reference resolves their KKT equations and checks every gap.
Fixtures are original mathematical examples, not a validated gearbox duty.
"""
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import subprocess
import sys

from verify_elastic_reference import ROOT, ADAPTER
import numpy as np
from gearforge.annular_mesh import annular_gear_mesh
from gearforge.elastic_contact import elastic_influence,solve_contact_loads
from gearforge.elasticity import PlaneElasticSystem
from gearforge.models import atomic_text
from gearforge.root_stress import RootStressStudy,synthetic_root_example,RackProfile,load_patches,patch_forces

CONTACT_ADAPTER=r'''
import json,sys
import numpy as np
import scipy
from scipy.optimize import minimize
results=[]
for case in json.load(sys.stdin):
    c=np.array(case['compliance']);g=np.array(case['gaps']);a=np.array(case['arms']);t=case['torque']
    objective=lambda f:.5*f@c@f+g@f
    result=minimize(objective,np.full(len(g),t/sum(a)),jac=lambda f:c@f+g,
        method='SLSQP',bounds=[(0,None)]*len(g),constraints=[dict(type='eq',fun=lambda f:a@f-t,jac=lambda f:a)],
        options=dict(ftol=1e-12,maxiter=2000))
    if not result.success:raise RuntimeError(result.message)
    active=np.flatnonzero(result.x>1e-7)
    kkt=np.block([[c[np.ix_(active,active)],-a[active,None]],[a[None,active],np.zeros((1,1))]])
    polished=np.linalg.solve(kkt,np.r_[-g[active],t]);f=np.zeros(len(g));f[active]=polished[:-1]
    residual=c@f+g-a*polished[-1]
    if min(f)<-1e-9 or min(residual)<-1e-9 or abs(a@f-t)>1e-9 or np.max(abs(residual[active]))>1e-9:
        raise RuntimeError('Reference contact set failed equilibrium/complementarity')
    if np.max(abs(f-result.x))>1e-4:raise RuntimeError('Reference polishing changed the optimization result')
    results.append(dict(forces=f.tolist(),rotation=float(polished[-1]),residual=residual.tolist(),energy=float(.5*f@c@f)))
print(json.dumps(dict(reference_version=scipy.__version__,results=results),allow_nan=False))
'''


def ring_model(case):
    study=RootStressStudy.from_dict(case['study']);profile=RackProfile(study.source)
    patches=load_patches(study,profile)
    indices=[0,1,-1];flanks=['left','right','left']
    mesh=annular_gear_mesh(profile,study.support_radius_mm,case['angular_divisions'],case['radial_layers'],list(zip(indices,patches)))
    forces=np.column_stack([profile.rb*patch_forces(study,profile,mesh,patch,flank,index)
                            for patch,flank,index in zip(patches,flanks,indices)])
    points=[]
    for tooth in (0,1,profile.z-1):
        index=int(mesh['root_elements'][np.flatnonzero(mesh['root_tooth_indices']==tooth)[0]])
        # Original fixture point, strictly inside a known root element.
        xy=np.array([.12,.18,.42,.28])@mesh['nodes'][mesh['elements'][index,:4]]
        points.append(dict(element_index=index,xy_mm=xy.tolist()))
    return study,mesh,forces,points


def ring_application(case):
    from gearforge.stress_probes import locate_point
    study,mesh,forces,points=ring_model(case)
    system=PlaneElasticSystem(mesh['nodes'],mesh['elements'],study.youngs_modulus_mpa,study.poisson_ratio,
                              study.effective_face_width_mm,study.plane_mode)
    influence=elastic_influence(system,forces,mesh['fixed_dofs']);u=influence['displacements'];stress=[]
    for column in range(forces.shape[1]):
        values=[]
        for point in points:
            side=next(v for v in locate_point(mesh['nodes'],mesh['elements'],*point['xy_mm']) if v['element_index']==point['element_index'])
            values.append(system.stress_at(u[:,column],[side['element_index']],side['xi'],side['eta'])[0].tolist())
        stress.append(values)
    return dict(compliance=influence['compliance'].tolist(),point_stress=stress,
                strain_energy=influence['elastic_checks']['strain_energy_n_mm'].tolist(),
                nodes=len(mesh['nodes']),elements=len(mesh['elements'])),influence


def run_reference(python,adapter,request):
    process=subprocess.run([python,'-c',adapter],input=json.dumps(request),text=True,capture_output=True)
    if process.returncode:raise RuntimeError(process.stderr)
    return json.loads(process.stdout)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-python',default=sys.executable)
    parser.add_argument('--out',type=Path,default=ROOT/'build/loaded-mesh-reference-comparison.json')
    parser.add_argument('--write-fixture',action='store_true');args=parser.parse_args()
    rings=[];requests=[]
    for role,mode in [('pinion','plane_stress'),('wheel','plane_strain')]:
        study=synthetic_root_example();study.source.role=role;study.plane_mode=mode;study.load_positions=[.3,.5,.7]
        profile=RackProfile(study.source);study.support_radius_mm=.6*profile.rf
        case=dict(name=f'Whole {profile.z}-tooth {role}, {mode}',study=asdict(study),angular_divisions=8,radial_layers=3)
        rings.append(case);study,mesh,forces,points=ring_model(case)
        for column in range(3):
            requests.append(dict(name=case['name']+f' load {column}',nodes=mesh['nodes'].tolist(),elements=mesh['elements'].tolist(),
                youngs_mpa=study.youngs_modulus_mpa,poisson=study.poisson_ratio,thickness_mm=study.effective_face_width_mm,mode=study.plane_mode,
                forces=forces[:,column].tolist(),fixed_dofs=mesh['fixed_dofs'].tolist(),prescribed=None,fixed_points=points))
    reference=run_reference(args.reference_python,ADAPTER,requests);comparisons=0;maximum={}
    for number,case in enumerate(rings):
        actual,influence=ring_application(case);study,mesh,forces,points=ring_model(case)
        values=reference['results'][3*number:3*number+3];u=np.array([v['displacements'] for v in values]).T
        expected=dict(compliance=(forces.T@u).tolist(),point_stress=[v['fixed_point_stress'] for v in values],
                      strain_energy=[v['strain_energy_n_mm'] for v in values],nodes=len(mesh['nodes']),elements=len(mesh['elements']))
        for key,absolute in [('compliance',2e-11),('point_stress',2e-9),('strain_energy',2e-11)]:
            a=np.asarray(actual[key]);b=np.asarray(expected[key]);np.testing.assert_allclose(a,b,rtol=2e-8,atol=absolute)
            comparisons+=a.size;maximum[key]=max(maximum.get(key,0.),float(np.max(abs(a-b))))
        np.testing.assert_allclose(influence['displacements'],u,rtol=2e-8,atol=2e-11);comparisons+=u.size
        reactions=influence['elastic_checks']['reactions'][mesh['fixed_dofs']]
        expected_reactions=np.array([v['reactions'] for v in values]).T
        np.testing.assert_allclose(reactions,expected_reactions,rtol=2e-8,atol=2e-8);comparisons+=reactions.size
        case['expected']=expected
    rng=np.random.default_rng(74329);contacts=[]
    for n in range(2,13):
        for index in range(10):
            matrix=rng.normal(size=(n,n));c=matrix.T@matrix+np.eye(n)*.25
            contacts.append(dict(name=f'Original SPD {n} patches, case {index}',compliance=c.tolist(),gaps=rng.uniform(-2,3,n).tolist(),
                                 arms=rng.uniform(.5,4,n).tolist(),torque=float(rng.uniform(.2,10))))
    contact_reference=run_reference(args.reference_python,CONTACT_ADAPTER,contacts);contact_count=0
    for case,expected in zip(contacts,contact_reference['results'],strict=True):
        actual=solve_contact_loads(case['compliance'],case['gaps'],case['arms'],case['torque'])
        for key,actual_key in [('forces','normal_forces_n'),('rotation','relative_rotation_rad'),('residual','contact_residual_mm'),('energy','strain_energy_n_mm')]:
            a=np.asarray(actual[actual_key]);b=np.asarray(expected[key]);np.testing.assert_allclose(a,b,rtol=2e-8,atol=2e-9)
            contact_count+=a.size;maximum[key]=max(maximum.get(key,0.),float(np.max(abs(a-b))))
        case['expected']=expected
    result=dict(passed=True,elastic_comparisons=comparisons,contact_comparisons=contact_count,
                elastic_reference='https://github.com/kinnala/scikit-fem',elastic_reference_version=reference['reference_version'],
                contact_reference='https://scipy.org/',contact_reference_version=contact_reference['reference_version'],
                reference_license='BSD-3-Clause',maximum_absolute_error=maximum,
                scope='Original whole-gear elastic and convex contact-load benchmarks. No completed moving-contact cycle, pressure solution or physical gearbox qualification.',
                rings=rings,contacts=contacts)
    args.out.parent.mkdir(parents=True,exist_ok=True);atomic_text(args.out,json.dumps(result,indent=2,allow_nan=False))
    if args.write_fixture:atomic_text(ROOT/'tests/data/open_loaded_mesh_reference.json',json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k not in ('rings','contacts')},indent=2))


if __name__=='__main__':main()
