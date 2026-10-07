from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from gearforge.annular_mesh import annular_gear_mesh
from gearforge.elasticity import PlaneElasticSystem
from gearforge.elastic_contact import elastic_influence,solve_contact_loads
from gearforge.root_stress import synthetic_root_example,RackProfile,load_patches,patch_forces


def gear_model():
    study=synthetic_root_example();study.load_positions=[.5];profile=RackProfile(study.source)
    patch=load_patches(study,profile)[0]
    mesh=annular_gear_mesh(profile,10,8,3,[(index,patch) for index in range(profile.z)])
    system=PlaneElasticSystem(mesh['nodes'],mesh['elements'],210000,.3,20)
    return study,profile,patch,mesh,system


def test_closed_ring_topology_and_seam():
    _,profile,_,mesh,system=gear_model()
    edges=Counter(tuple(sorted((int(a),int(b)))) for cell in mesh['elements'][:,:4] for a,b in zip(cell,np.roll(cell,-1)))
    corners=np.unique(mesh['elements'][:,:4]);boundary=[edge for edge,count in edges.items() if count==1]
    columns=len(mesh['angles'])-1
    assert set(edges.values())=={1,2} and len(boundary)==2*columns
    assert len(corners)-len(edges)+len(mesh['elements'])==0
    assert system.component_count==1 and mesh['outer_nodes'][0]==mesh['outer_nodes'][-1]
    assert len(set(mesh['outer_midpoints']))==columns and mesh['sector_teeth']==profile.z
    assert len(mesh['nodes'])==2*columns*(2*mesh['radial_layers']+1)
    assert system.minimum_scaled_jacobian>.01


def test_rotated_pressure_loads_reciprocity_and_neighbor_coupling():
    study,profile,patch,mesh,system=gear_model()
    columns=np.column_stack([profile.rb*patch_forces(study,profile,mesh,patch,'left',index) for index in (0,1,-1)])
    forces=columns.reshape(len(mesh['nodes']),2,-1)
    moments=np.sum(mesh['nodes'][:,0,None]*forces[:,1]-mesh['nodes'][:,1,None]*forces[:,0],axis=0)
    np.testing.assert_allclose(moments,-profile.rb,atol=1e-12)
    result=elastic_influence(system,columns,mesh['fixed_dofs']);c=result['compliance']
    assert result['relative_reciprocity_error']<1e-10 and np.linalg.eigvalsh(c).min()>0
    np.testing.assert_allclose(np.diag(c),c[0,0],rtol=1e-9)
    assert c[0,1]==pytest.approx(c[0,2],rel=1e-9)
    assert max(abs(c[0,1:]))>1e-4*c[0,0]
    contact=solve_contact_loads(c,[0,0,0],[profile.rb]*3,1000)
    force=np.array(contact['normal_forces_n']);u=result['displacements']@force
    direct=system.solve(columns@force,mesh['fixed_dofs'])['displacements'][:,0]
    np.testing.assert_allclose(u,direct,rtol=1e-8,atol=1e-12)
    assert contact['strain_energy_n_mm']==pytest.approx(.5*u@(system.K@u),rel=1e-9)


@pytest.mark.parametrize('mode',['plane_stress','plane_strain'])
def test_circular_annulus_agrees_with_lame_solution(mode):
    a,b,pressure,young,nu,width=1.,2.,10.,210000.,.3,3.
    profile=SimpleNamespace(z=4,rf=b,m=.1,phif=.55,phij=.35,phia=.15,radius_at_angle=lambda angle:b)
    errors=[]
    if mode=='plane_stress':coefficient=-pressure*(1-nu**2)/young/((1+nu)+(1-nu)*a*a/(b*b))
    else:coefficient=-pressure*(1+nu)/young/(1/(1-2*nu)+a*a/(b*b))
    for divisions,layers in ((12,4),(24,8),(48,16)):
        mesh=annular_gear_mesh(profile,a,divisions,layers);nodes=mesh['nodes'];force=np.zeros(2*len(nodes))
        for i,(first,last) in enumerate(zip(mesh['outer_nodes'],mesh['outer_nodes'][1:])):
            p,q=nodes[[first,last]];normal=(p+q)/np.linalg.norm(p+q);length=np.linalg.norm(q-p)
            for index,weight in zip((first,mesh['outer_midpoints'][i],last),(1/6,2/3,1/6)):
                force[2*index:2*index+2]-=pressure*width*length*weight*normal
        system=PlaneElasticSystem(nodes,mesh['elements'],young,nu,width,mode)
        u=system.solve(force,mesh['fixed_dofs'])['displacements'][:,0]
        exact=coefficient*(1-a*a/np.sum(nodes*nodes,axis=1))[:,None]*nodes
        errors.append(float(np.max(abs(u.reshape(-1,2)-exact))))
    assert errors[2]<errors[1]<errors[0]
    assert errors[-1]<abs(coefficient*(b-a*a/b))*.002


def test_whole_gear_resource_and_boundary_validation():
    study=synthetic_root_example();profile=RackProfile(study.source)
    for args in ((profile,profile.rf),(profile,10,True,4),(profile,10,256,96)):
        with pytest.raises(ValueError):annular_gear_mesh(*args)
