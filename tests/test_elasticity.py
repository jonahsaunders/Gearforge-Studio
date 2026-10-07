import json
from pathlib import Path

import numpy as np
import pytest

from gearforge.elasticity import PlaneElasticSystem,stress_measures


def reference_cases():
    return json.loads((Path(__file__).parent/'data/open_elastic_reference.json').read_text())


def test_independent_scikit_fem_displacements_reactions_stress_and_energy():
    fixture=reference_cases();count=0
    assert fixture['reference_license']=='BSD-3-Clause' and fixture['reference_version']=='12.0.2'
    for case in fixture['cases']:
        system=PlaneElasticSystem(case['nodes'],case['elements'],case['youngs_mpa'],case['poisson'],case['thickness_mm'],case['mode'])
        solved=system.solve(case['forces'],case['fixed_dofs'],case['prescribed']);u=solved['displacements'][:,0]
        actual=dict(displacements=u,reactions=solved['reactions'][:,0][case['fixed_dofs']],
            gauss_sample_mean_stress=np.mean([system.stress_at(u,xi=x,eta=y) for x,y in system.gauss],axis=0),
            strain_energy_n_mm=solved['strain_energy_n_mm'][0])
        for key,value in actual.items():
            relative,absolute=fixture['tolerances'][key]
            np.testing.assert_allclose(value,case['expected'][key],rtol=relative,atol=absolute);count+=np.asarray(value).size
    assert count==fixture['comparisons']==4582


@pytest.mark.parametrize('case_index',[0,1,2])
def test_exact_uniform_traction_displacement_stress_energy(case_index):
    c=reference_cases()['cases'][case_index];nodes=np.array(c['nodes'])
    system=PlaneElasticSystem(nodes,c['elements'],210000,.3,3,c['mode']);solved=system.solve(c['forces'],c['fixed_dofs'])
    ex=100/210000 if c['mode']=='plane_stress' else 100*(1-.3**2)/210000
    ey=-.3*100/210000 if c['mode']=='plane_stress' else -.3*(1+.3)*100/210000
    np.testing.assert_allclose(solved['displacements'][:,0].reshape(-1,2),nodes*[ex,ey],rtol=2e-10,atol=1e-13)
    for x,y in system.gauss:
        expected=np.tile([100,0,0,0 if c['mode']=='plane_stress' else 30],(len(system.elements),1))
        np.testing.assert_allclose(system.stress_at(solved['displacements'][:,0],xi=x,eta=y),expected,atol=1e-9)
    assert solved['strain_energy_n_mm'][0]==pytest.approx(.5*100*ex*4*2*3)
    assert solved['reactions'][::2].sum()==pytest.approx(-600)


def test_distorted_quadratic_patch_reproduces_pure_bending():
    c=reference_cases()['cases'][3];nodes=np.array(c['nodes']);system=PlaneElasticSystem(nodes,c['elements'],210000,.3,3)
    solved=system.solve(c['forces'],c['fixed_dofs'],c['prescribed']);u=solved['displacements'][:,0]
    exact=np.column_stack((-.001*nodes[:,0]*nodes[:,1],.0005*(nodes[:,0]**2+.3*nodes[:,1]**2))).ravel()
    np.testing.assert_allclose(u,exact,atol=2e-15)
    from gearforge.elasticity import shape
    for x,y in system.gauss:
        location=np.einsum('n,eni->ei',shape(x,y,9),system.coordinates)
        expected=np.zeros((len(system.elements),4));expected[:,0]=-210*location[:,1]
        np.testing.assert_allclose(system.stress_at(u,xi=x,eta=y),expected,atol=1e-9)


def test_affine_patch_and_stress_invariants():
    c=reference_cases()['cases'][0];nodes=np.array(c['nodes']);system=PlaneElasticSystem(nodes,c['elements'],210000,.3,3)
    exact=np.column_stack((.001*nodes[:,0]+.002*nodes[:,1],-.003*nodes[:,0]+.0005*nodes[:,1])).ravel()
    fixed=np.array([2*i+j for i,(x,y) in enumerate(nodes) if x in (0,4) or y in (0,2) for j in (0,1)])
    u=system.solve(np.zeros(system.ndof),fixed,exact[fixed])['displacements'][:,0]
    np.testing.assert_allclose(u,exact,atol=1e-15)
    np.testing.assert_allclose(system.stress_at(u),np.tile([265.38461538461536,184.6153846153846,-80.76923076923077,0],(4,1)),atol=1e-10)
    vm,tension=stress_measures([[0,0,12,0],[-20,-20,0,-20],[20,20,0,20]])
    np.testing.assert_allclose(vm,[12*np.sqrt(3),0,0]);np.testing.assert_allclose(tension,[12,0,20])


@pytest.mark.parametrize('nodes,elements',[
    ([[0,0],[1,0],[1,1],[0,1]],[[0,3,2,1]]),
    ([[0,0],[1,0],[.1,.1],[0,1]],[[0,1,2,3]]),
    ([[0,0],[1,0],[1,1],[0,1]],[[0.,1.,2.,3.]]),
    ([[0,0],[1,0],[1,1],[0,1]],[[0,1,1,3]]),
    ([[0,0],[1,0],[1,float('nan')],[0,1]],[[0,1,2,3]]),
])
def test_invalid_or_folded_mesh_rejected(nodes,elements):
    with pytest.raises(ValueError):PlaneElasticSystem(nodes,elements,210000,.3,1)


def test_wrong_quadratic_geometry_material_and_unsupported_bodies():
    c=reference_cases()['cases'][1];nodes=np.array(c['nodes']);nodes[c['elements'][0][4]]+=[.01,0]
    with pytest.raises(ValueError,match='midpoint'):PlaneElasticSystem(nodes,c['elements'],210000,.3,1)
    with pytest.raises(ValueError):PlaneElasticSystem(c['nodes'],c['elements'],210000,.499,1,'plane_strain')
    nodes=np.array([[0,0],[1,0],[1,1],[0,1],[2,0],[3,0],[3,1],[2,1]])
    s=PlaneElasticSystem(nodes,[[0,1,2,3],[4,5,6,7]],210000,.3,1)
    with pytest.raises(ValueError,match='Every connected body'):s.solve(np.zeros(16),[0,1,3])
    s=PlaneElasticSystem(nodes[:4],[[0,1,2,3]],210000,.3,1)
    with pytest.raises(ValueError,match='Every connected body'):s.solve(np.zeros(8),[0,2,4])
    for force,fixed in [(np.zeros(7),[0,1,3]),(np.full(8,np.inf),[0,1,3]),(np.zeros(8),[0,1,1])]:
        with pytest.raises(ValueError):s.solve(force,fixed)


def test_linearity_multiple_loads_and_prescribed_displacement_validation():
    c=reference_cases()['cases'][1];s=PlaneElasticSystem(c['nodes'],c['elements'],210000,.3,3)
    f=np.array(c['forces']);r=s.solve(np.column_stack([f,3*f,-f,np.zeros_like(f)]),c['fixed_dofs'])
    np.testing.assert_allclose(r['displacements'][:,1],3*r['displacements'][:,0],atol=1e-13)
    np.testing.assert_allclose(r['displacements'][:,2],-r['displacements'][:,0],atol=1e-13)
    assert r['strain_energy_n_mm'][1]==pytest.approx(9*r['strain_energy_n_mm'][0])
    assert r['strain_energy_n_mm'][3]==0
    with pytest.raises(ValueError):s.solve(f,c['fixed_dofs'],[float('nan')]*len(c['fixed_dofs']))
