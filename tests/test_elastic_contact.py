import itertools

import numpy as np
import pytest

from gearforge.elastic_contact import solve_contact_loads


def exhaustive_solution(c,g,a,torque):
    """Independent all-subset KKT equations; no active-set stepping/scaling."""
    for size in range(1,len(g)+1):
        for indices in itertools.combinations(range(len(g)),size):
            ids=np.array(indices);matrix=np.block([[c[np.ix_(ids,ids)],-a[ids,None]],
                                                 [a[None,ids],np.zeros((1,1))]])
            solved=np.linalg.solve(matrix,np.r_[-g[ids],torque]);f=np.zeros(len(g));f[ids]=solved[:-1]
            slack=c@f+g-a*solved[-1]
            if min(f)>=-1e-9 and min(slack)>=-1e-9:return f,solved[-1]
    raise AssertionError('No feasible independent contact state')


def test_exact_parallel_springs_and_separation():
    r=solve_contact_loads([[.1,0],[0,.2]],[0,0],[2,2],20)
    np.testing.assert_allclose(r['normal_forces_n'],[20/3,10/3],rtol=1e-13)
    assert r['relative_rotation_rad']==pytest.approx(1/3)
    r=solve_contact_loads([[.1,0],[0,.2]],[0,2],[2,2],20)
    assert r['normal_forces_n']==pytest.approx([10,0]) and r['active_indices']==[0]
    assert r['contact_residual_mm']==pytest.approx([0,1])
    r=solve_contact_loads(np.eye(2),[0,0],[1,3],5)
    assert r['normal_forces_n']==pytest.approx([.5,1.5])
    assert r['relative_rotation_rad']==pytest.approx(.5)


def test_contact_transition_and_single_patch():
    for torque in (19.999,20,20.001):
        r=solve_contact_loads([[.1,0],[0,.2]],[0,1],[2,2],torque)
        expected_second=max(0,(torque/2-10)/3)
        assert r['normal_forces_n'][1]==pytest.approx(expected_second,abs=1e-11)
        assert r['relative_kkt_residual']<1e-10
    r=solve_contact_loads([[.125]],[-.3],[4],8)
    assert r['normal_forces_n']==[2] and r['relative_rotation_rad']==pytest.approx(-.0125)
    assert r['strain_energy_n_mm']==pytest.approx(.25)
    gaps=np.linspace(0,4,64)
    for count in range(1,65):
        closure=(10+sum(gaps[:count]))/count
        if count==64 or closure<=gaps[count]:break
    r=solve_contact_loads(np.eye(64),gaps,np.full(64,2.),20)
    np.testing.assert_allclose(r['normal_forces_n'],np.maximum(closure-gaps,0),atol=1e-11)
    assert len(r['active_indices'])==count


def test_zero_torque_has_no_invented_relative_position():
    r=solve_contact_loads(np.eye(2),[-.3,1],[3,2],0)
    assert r['normal_forces_n']==[0,0] and r['relative_rotation_rad'] is None
    assert r['contact_residual_mm'] is None and r['first_touch_rotation_rad']==pytest.approx(-.1)


def test_independent_active_subsets_and_energy_optimality():
    random=np.random.default_rng(53142)
    for n in range(2,9):
        for _ in range(12):
            matrix=random.normal(size=(n,n));c=matrix.T@matrix+np.eye(n)*.2
            a=random.uniform(.5,3,n);g=random.uniform(-1,2,n);torque=float(random.uniform(.2,5))
            expected,rotation=exhaustive_solution(c,g,a,torque)
            result=solve_contact_loads(c,g,a,torque);f=np.array(result['normal_forces_n'])
            np.testing.assert_allclose(f,expected,rtol=2e-9,atol=1e-10)
            assert result['relative_rotation_rad']==pytest.approx(rotation,rel=2e-9,abs=1e-10)
            assert a@f==pytest.approx(torque) and min(f)>=0
            assert f@(c@f+g)==pytest.approx(torque*rotation)
            feasible=torque*random.dirichlet(np.ones(n))/a
            assert .5*f@c@f+g@f<=.5*feasible@c@feasible+g@feasible+1e-10


def test_permutation_compliance_and_load_scaling():
    c=np.array([[3.,-.5,.7],[-.5,2.,.2],[.7,.2,1.5]])
    g=np.array([.1,.9,-.2]);a=np.array([1.,2.,3.]);base=solve_contact_loads(c,g,a,8)
    indices=[2,0,1];permuted=solve_contact_loads(c[np.ix_(indices,indices)],g[indices],a[indices],8)
    np.testing.assert_allclose(permuted['normal_forces_n'],np.array(base['normal_forces_n'])[indices])
    for scale in (1e-9,1e-3,1e3,1e9):
        r=solve_contact_loads(c*scale,g*scale,a,8)
        np.testing.assert_allclose(r['normal_forces_n'],base['normal_forces_n'],rtol=1e-10)
        assert r['relative_rotation_rad']==pytest.approx(base['relative_rotation_rad']*scale)
    base=solve_contact_loads(c,np.zeros(3),a,8)
    r=solve_contact_loads(c,np.zeros(3),a,80)
    np.testing.assert_allclose(r['normal_forces_n'],10*np.array(base['normal_forces_n']))


@pytest.mark.parametrize('c,g,a,t',[
    ([[0]],[0],[1],1),([[-1]],[0],[1],1),([[1,2],[0,1]],[0,0],[1,1],1),
    ([[1,1],[1,1]],[0,0],[1,1],1),([[1]],[0],[0],1),([[1]],[0],[-1],1),
    ([[float('nan')]],[0],[1],1),([[1]],[float('inf')],[1],1),([[1]],[0],[1],-1),
    ([[True]],[0],[1],1),([[1]],[False],[1],1),([[1]],[0],[True],1),([[1]],[0],[1],True),
    ([[1,0],[0,1e-14]],[0,0],[1,1],1),(np.eye(65),np.zeros(65),np.ones(65),1),
    ([[True,0.],[0.,1.]],[0,0],[1,1],1),([[1]],[0],[1e-100],0),
])
def test_invalid_or_unresolved_compliance_rejected(c,g,a,t):
    with pytest.raises(ValueError):solve_contact_loads(c,g,a,t)
