"""Check original Q4/Q9 assembly against separately installed scikit-fem.

The reference builds its own basis, maps nodes by physical coordinates, assembles
the elasticity weak form and recovers strains through its own interpolation.
No application shape function, Jacobian, B matrix or stiffness enters that process.
"""
from dataclasses import asdict
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from gearforge.elasticity import PlaneElasticSystem
from gearforge.models import atomic_text
from gearforge.root_stress import synthetic_root_example,root_mesh,load_patches,patch_forces,RackProfile

ADAPTER=r'''
import json,sys
import numpy as np
import skfem
from skfem import MeshQuad,Basis,ElementVector,ElementQuad1,ElementQuad2,asm,condense,solve
from skfem.models.elasticity import linear_elasticity
from scipy.spatial import cKDTree
results=[]
for case in json.load(sys.stdin):
    p=np.array(case['nodes']);t=np.array(case['elements']);corners=np.unique(t[:,:4])
    index={value:i for i,value in enumerate(corners)}
    mesh=MeshQuad(p[corners].T,np.array([[index[n] for n in row[:4]] for row in t]).T)
    basis=Basis(mesh,ElementVector(ElementQuad1() if t.shape[1]==4 else ElementQuad2()),intorder=2 if t.shape[1]==4 else 4)
    for family in (basis.nodal_dofs,basis.facet_dofs,basis.interior_dofs):
        if family.size and (not np.all(family[0]%2==0) or not np.all(family[1]%2==1)):raise RuntimeError('Reference vector component layout changed')
    distance,mapping=cKDTree(basis.doflocs[:,::2].T).query(p)
    if max(distance)>1e-8 or len(set(mapping))!=len(p) or basis.N!=2*len(p):raise RuntimeError('Reference physical node mapping failed')
    mapping=(2*mapping[:,None]+[0,1]).ravel()
    e=case['youngs_mpa'];nu=case['poisson'];mu=e/(2*(1+nu))
    lam=e*nu/(1-nu*nu) if case['mode']=='plane_stress' else e*nu/((1+nu)*(1-2*nu))
    K=case['thickness_mm']*asm(linear_elasticity(lam,mu),basis)
    f=np.zeros(basis.N);f[mapping]=case['forces'];fixed=mapping[case['fixed_dofs']]
    x=np.zeros(basis.N)
    if case['prescribed'] is not None:x[fixed]=case['prescribed']
    u=solve(*condense(K,f,x=x,D=fixed));gradient=basis.interpolate(u).grad
    trace=gradient[0,0]+gradient[1,1]
    sx=2*mu*gradient[0,0]+lam*trace;sy=2*mu*gradient[1,1]+lam*trace
    shear=mu*(gradient[0,1]+gradient[1,0]);sz=lam*trace if case['mode']=='plane_strain' else np.zeros_like(trace)
    stress=np.stack([sx,sy,shear,sz],axis=1).mean(axis=2)
    results.append(dict(displacements=u[mapping].tolist(),reactions=(K@u-f)[mapping][case['fixed_dofs']].tolist(),
        gauss_sample_mean_stress=stress.tolist(),strain_energy_n_mm=float(.5*u@(K@u))))
print(json.dumps(dict(reference_version=skfem.__version__,results=results),allow_nan=False))
'''


def rectangular_mesh(quadratic=False,distorted=False):
    nodes=np.array([[x,y] for y in (0.,1.,2.) for x in (0.,2.,4.)])
    if distorted:nodes[4]+=[.25,-.2]
    cells=np.array([[3*j+i,3*j+i+1,3*j+i+4,3*j+i+3] for j in range(2) for i in range(2)])
    if not quadratic:return nodes,cells
    points=nodes.tolist();edges={};elements=[]
    for cell in cells:
        extra=[]
        for a,b in zip(cell,np.roll(cell,-1)):
            edge=tuple(sorted((int(a),int(b))))
            if edge not in edges:edges[edge]=len(points);points.append(((nodes[a]+nodes[b])/2).tolist())
            extra.append(edges[edge])
        center=len(points);points.append(nodes[cell].mean(axis=0).tolist());elements.append([*cell,*extra,center])
    return np.array(points),np.array(elements)


def fixtures():
    cases=[]
    def add(name,nodes,elements,force,fixed,e=210000.,nu=.3,width=3.,mode='plane_stress',prescribed=None,source=None):
        cases.append(dict(name=name,nodes=nodes.tolist(),elements=elements.tolist(),forces=force.tolist(),fixed_dofs=fixed.tolist(),
            youngs_mpa=e,poisson=nu,thickness_mm=width,mode=mode,prescribed=None if prescribed is None else prescribed.tolist(),source=source))
    for quadratic,mode in [(False,'plane_stress'),(True,'plane_stress'),(True,'plane_strain')]:
        nodes,cells=rectangular_mesh(quadratic);force=np.zeros(2*len(nodes))
        # Uniform end traction, consistent weights at quadratic edge midpoints.
        for cell in cells:
            if np.allclose(nodes[cell[[1,2]],0],4):
                edge=cell[[1,5,2]] if quadratic else cell[[1,2]]
                weights=np.array([1,4,1])/6 if quadratic else np.array([.5,.5])
                force[2*edge]+=100*3*weights
        fixed=np.array([2*i for i in range(len(nodes)) if nodes[i,0]==0]+[1])
        add(f'Uniform traction {"Q9" if quadratic else "Q4"} {mode}',nodes,cells,force,fixed,mode=mode)
    nodes,cells=rectangular_mesh(True,True);exact=np.column_stack((-.001*nodes[:,0]*nodes[:,1],.0005*(nodes[:,0]**2+.3*nodes[:,1]**2))).ravel()
    fixed=np.array([2*i+c for i,p in enumerate(nodes) if p[0] in (0,4) or p[1] in (0,2) for c in (0,1)])
    add('Distorted Q9 quadratic bending patch',nodes,cells,np.zeros(2*len(nodes)),fixed,prescribed=exact[fixed])
    for mode,shift,flank in [('plane_stress',0.,'left'),('plane_strain',.3,'right')]:
        study=synthetic_root_example();study.sector_teeth=3;study.angular_divisions_per_tooth=8;study.radial_layers=4
        study.load_positions=[.5];study.plane_mode=mode;study.source.source.pair.pinion_profile_shift=shift
        profile=RackProfile(study.source);patches=load_patches(study,profile);mesh=root_mesh(study,profile,patches)
        force=1000*patch_forces(study,profile,mesh,patches[0],flank)
        add('Generated root '+mode,mesh['nodes'],mesh['elements'],force,mesh['fixed_dofs'],width=20,mode=mode,source=asdict(study))
    return cases


def application_result(case):
    system=PlaneElasticSystem(case['nodes'],case['elements'],case['youngs_mpa'],case['poisson'],case['thickness_mm'],case['mode'])
    solved=system.solve(case['forces'],case['fixed_dofs'],case['prescribed']);u=solved['displacements'][:,0]
    stress=np.mean([system.stress_at(u,xi=x,eta=y) for x,y in system.gauss],axis=0)
    return dict(displacements=u.tolist(),reactions=solved['reactions'][:,0][case['fixed_dofs']].tolist(),
        gauss_sample_mean_stress=stress.tolist(),strain_energy_n_mm=float(solved['strain_energy_n_mm'][0]))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reference-python',default=sys.executable)
    parser.add_argument('--out',type=Path,default=ROOT/'build/elastic-reference-comparison.json');parser.add_argument('--write-fixture',action='store_true')
    args=parser.parse_args();cases=fixtures()
    process=subprocess.run([args.reference_python,'-c',ADAPTER],input=json.dumps(cases),text=True,capture_output=True)
    if process.returncode:raise RuntimeError(process.stderr)
    reference=json.loads(process.stdout);count=0;maximum={}
    tolerances={'displacements':(2e-8,2e-11),'reactions':(2e-8,2e-7),'gauss_sample_mean_stress':(2e-8,2e-7),'strain_energy_n_mm':(2e-8,2e-10)}
    for case,expected in zip(cases,reference['results'],strict=True):
        actual=application_result(case);case['expected']=expected
        for key,(rel,absolute) in tolerances.items():
            a=np.asarray(actual[key]);b=np.asarray(expected[key]);assert a.shape==b.shape
            if not np.allclose(a,b,rtol=rel,atol=absolute):raise ValueError(f"{case['name']} differs for {key}: {np.max(abs(a-b))}")
            maximum[key]=max(maximum.get(key,0),float(np.max(abs(a-b))));count+=a.size
    result=dict(passed=True,comparisons=count,reference='https://github.com/kinnala/scikit-fem',reference_version=reference['reference_version'],
        reference_license='BSD-3-Clause',scope='Six original Q4/Q9 plane-elastic fixtures; independent basis/weak-form assembly, loads and mesh supplied identically. No physical strength/fatigue qualification.',
        tolerances=tolerances,maximum_absolute_error=maximum,cases=cases)
    args.out.parent.mkdir(parents=True,exist_ok=True);atomic_text(args.out,json.dumps(result,indent=2,allow_nan=False))
    if args.write_fixture:atomic_text(ROOT/'tests/data/open_elastic_reference.json',json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))


if __name__=='__main__':main()
