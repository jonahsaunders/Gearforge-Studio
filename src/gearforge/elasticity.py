"""Original fully integrated Q4/Q9 plane elasticity on bilinear geometry.

Units: mm, N, MPa. Engineering strain order is xx, yy, xy (gamma).
The solver has no gear factors or strength/life model. SciPy supplies only
sparse matrix assembly/factorization, independently checked with scikit-fem.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import splu

from .models import finite

METHOD = 'bilinear-geometry-q4-q9-plane-1'
MAX_ELEMENTS = 40000


def constitutive(youngs_mpa, poisson, mode):
    youngs_mpa=finite(youngs_mpa,'Young modulus',1,1e6)
    poisson=finite(poisson,'Poisson ratio',0,.45 if mode=='plane_strain' else .49)
    if mode=='plane_stress':
        return youngs_mpa/(1-poisson**2)*np.array([[1,poisson,0],[poisson,1,0],[0,0,(1-poisson)/2]])
    if mode=='plane_strain':
        return youngs_mpa/((1+poisson)*(1-2*poisson))*np.array([[1-poisson,poisson,0],[poisson,1-poisson,0],[0,0,(1-2*poisson)/2]])
    raise ValueError('Choose plane stress or plane strain')


def shape(xi,eta,count=4):
    if count==9:
        x=np.array([xi*(xi-1)/2,1-xi*xi,xi*(xi+1)/2]);y=np.array([eta*(eta-1)/2,1-eta*eta,eta*(eta+1)/2])
        return np.array([x[i]*y[j] for i,j in [(0,0),(2,0),(2,2),(0,2),(1,0),(2,1),(1,2),(0,1),(1,1)]])
    return np.array([(1-xi)*(1-eta),(1+xi)*(1-eta),(1+xi)*(1+eta),(1-xi)*(1+eta)])/4


def strain_matrix(coordinates,xi,eta):
    """Return B, Jacobian determinant and Jacobian for an array of CCW Q4s."""
    derivatives=np.array([[-(1-eta),-(1-xi)],[(1-eta),-(1+xi)],[(1+eta),(1+xi)],[-(1+eta),(1-xi)]])/4
    jacobian=np.einsum('eni,nj->eij',coordinates[:,:4],derivatives)
    determinant=np.linalg.det(jacobian)
    if np.any(determinant<=0) or not np.all(np.isfinite(determinant)):
        raise ValueError('Nonpositive or nonfinite element Jacobian')
    if coordinates.shape[1]==9:
        x=np.array([xi*(xi-1)/2,1-xi*xi,xi*(xi+1)/2]);y=np.array([eta*(eta-1)/2,1-eta*eta,eta*(eta+1)/2])
        dx=np.array([xi-.5,-2*xi,xi+.5]);dy=np.array([eta-.5,-2*eta,eta+.5])
        derivatives=np.array([[dx[i]*y[j],x[i]*dy[j]] for i,j in [(0,0),(2,0),(2,2),(0,2),(1,0),(2,1),(1,2),(0,1),(1,1)]])
    gradients=np.einsum('ni,eij->enj',derivatives,np.linalg.inv(jacobian))
    matrix=np.zeros((len(coordinates),3,2*coordinates.shape[1]))
    matrix[:,0,0::2]=gradients[:,:,0];matrix[:,1,1::2]=gradients[:,:,1]
    matrix[:,2,0::2]=gradients[:,:,1];matrix[:,2,1::2]=gradients[:,:,0]
    return matrix,determinant,jacobian


def stress_measures(stress):
    """xx, yy, xy, zz -> three-dimensional von Mises and tensile principal."""
    sx,sy,txy,sz=np.moveaxis(np.asarray(stress,dtype=float),-1,0)
    principal=(sx+sy)/2+np.sqrt(((sx-sy)/2)**2+txy*txy)
    tensile=np.maximum(0,np.maximum(principal,sz))
    vm=np.sqrt(.5*((sx-sy)**2+(sy-sz)**2+(sz-sx)**2)+3*txy*txy)
    return vm,tensile


class PlaneElasticSystem:
    def __init__(self,nodes,elements,youngs_mpa,poisson,thickness_mm,mode='plane_stress'):
        self.D=constitutive(youngs_mpa,poisson,mode);self.E=float(youngs_mpa);self.nu=float(poisson);self.mode=mode
        self.thickness=finite(thickness_mm,'Model thickness',.001,1000)
        self.nodes=np.asarray(nodes,dtype=float);raw=np.asarray(elements)
        if self.nodes.ndim!=2 or self.nodes.shape[1]!=2 or not 4<=len(self.nodes)<=90000 or not np.all(np.isfinite(self.nodes)):
            raise ValueError('Finite two-dimensional mesh nodes are required')
        if raw.ndim!=2 or raw.shape[1] not in (4,9) or not 1<=len(raw)<=MAX_ELEMENTS or raw.dtype.kind not in 'iu':
            raise ValueError('Mesh requires 1..40,000 integer Q4 or Q9 elements')
        if raw.min()<0 or raw.max()>=len(self.nodes) or any(len(set(e))!=raw.shape[1] for e in raw):raise ValueError('Invalid element connectivity')
        self.elements=raw.astype(int);self.coordinates=self.nodes[self.elements]
        graph=coo_matrix((np.ones(raw.size),(np.repeat(self.elements[:,0],raw.shape[1]),self.elements.ravel())),shape=(len(self.nodes),len(self.nodes))).tocsr()
        self.component_count,self.components=connected_components(graph,directed=False)
        self.element_dofs=2*raw.shape[1]
        if raw.shape[1]==9:
            corners=self.coordinates[:,:4]
            expected=np.stack(((corners[:,0]+corners[:,1])/2,(corners[:,1]+corners[:,2])/2,
                (corners[:,2]+corners[:,3])/2,(corners[:,3]+corners[:,0])/2,corners.mean(axis=1)),axis=1)
            if not np.allclose(self.coordinates[:,4:],expected,rtol=0,atol=1e-10*max(1.,float(np.max(abs(self.nodes))))):
                raise ValueError('Q9 displacement elements require midpoint/center nodes on bilinear geometry')
        self.dofs=(2*self.elements[:,:,None]+np.array([0,1])).reshape(-1,self.element_dofs)
        self.ndof=2*len(self.nodes);self.minimum_scaled_jacobian=1.;self.maximum_jacobian_condition=1.
        # det(J) is affine in xi/eta for a bilinear quadrilateral. Its four
        # corner values therefore also check positivity throughout each cell.
        for xi,eta in [(-1,-1),(1,-1),(1,1),(-1,1)]:
            _,det,jac=strain_matrix(self.coordinates,xi,eta)
            scaled=det/(np.linalg.norm(jac[:,:,0],axis=1)*np.linalg.norm(jac[:,:,1],axis=1))
            self.minimum_scaled_jacobian=min(self.minimum_scaled_jacobian,float(scaled.min()))
            self.maximum_jacobian_condition=max(self.maximum_jacobian_condition,float(np.linalg.cond(jac).max()))
        if self.minimum_scaled_jacobian<.01 or self.maximum_jacobian_condition>2000:
            raise ValueError('Excessive element distortion; change the domain, patch or mesh resolution')
        local=np.zeros((len(raw),self.element_dofs,self.element_dofs))
        points,weights=np.polynomial.legendre.leggauss(2 if raw.shape[1]==4 else 3)
        self.gauss=[(x,y) for x in points for y in points]
        for (xi,eta),weight in zip(self.gauss,[x*y for x in weights for y in weights]):
            b,det,_=strain_matrix(self.coordinates,xi,eta)
            local+=np.einsum('eai,ab,ebj,e->eij',b,self.D,b,det*self.thickness*weight,optimize=True)
        self.K=coo_matrix((local.ravel(),(np.repeat(self.dofs,self.element_dofs,axis=1).ravel(),np.tile(self.dofs,(1,self.element_dofs)).ravel())),shape=(self.ndof,self.ndof)).tocsr()
        if np.any(self.K.diagonal()<=0) or not np.all(np.isfinite(self.K.data)):raise ValueError('Invalid elastic stiffness')

    def solve(self,forces,fixed_dofs,prescribed=None):
        force=np.asarray(forces,dtype=float)
        if force.ndim==1:force=force[:,None]
        if force.ndim!=2 or force.shape[0]!=self.ndof or not 1<=force.shape[1]<=24 or not np.all(np.isfinite(force)):
            raise ValueError('Finite load vectors must match the mesh degrees of freedom')
        raw=np.asarray(fixed_dofs)
        if raw.ndim!=1 or raw.dtype.kind not in 'iu' or len(raw)<3 or raw.min()<0 or raw.max()>=self.ndof or len(set(raw))!=len(raw):
            raise ValueError('Unique valid constrained degrees of freedom are required')
        fixed=raw.astype(int);free=np.setdiff1d(np.arange(self.ndof),fixed)
        if not len(free):raise ValueError('The model has no free degrees of freedom')
        for component in range(self.component_count):
            body=self.nodes[self.components==component];center=body.mean(axis=0);length=max(float(np.ptp(body,axis=0).max()),1e-12)
            constraints=fixed[self.components[fixed//2]==component]
            rigid=np.zeros((len(constraints),3))
            for row,dof in enumerate(constraints):
                x,y=(self.nodes[dof//2]-center)/length
                rigid[row]=[1,0,-y] if dof%2==0 else [0,1,x]
            if len(constraints)<3 or np.linalg.matrix_rank(rigid,tol=1e-10)<3:
                raise ValueError('Every connected body needs supports that restrain both translations and rotation')
        u=np.zeros_like(force)
        if prescribed is not None:
            values=np.asarray(prescribed,dtype=float)
            if values.ndim==1:values=values[:,None]
            if values.shape not in ((len(fixed),1),(len(fixed),force.shape[1])) or not np.all(np.isfinite(values)):
                raise ValueError('Invalid prescribed displacement')
            u[fixed]=values
        try:
            factor=splu(self.K[free][:,free].tocsc())
            u[free]=factor.solve(force[free]-self.K[free][:,fixed]@u[fixed])
        except RuntimeError as exc:raise ValueError('Singular elastic support/stiffness system') from exc
        if not np.all(np.isfinite(u)):raise ValueError('Elastic displacements are not finite')
        internal=self.K@u;residual=internal-force
        scale=np.maximum(1e-12,np.maximum(np.max(abs(force),axis=0),np.max(abs(internal),axis=0)))
        relative=np.max(abs(residual[free]),axis=0)/scale
        if np.max(relative)>1e-7:raise ValueError('Elastic equation residual exceeds tolerance')
        reaction=np.zeros_like(force);reaction[fixed]=residual[fixed]
        energy=.5*np.sum(u*internal,axis=0)
        if np.any(energy< -1e-12) or not np.all(np.isfinite(energy)):raise ValueError('Invalid elastic strain energy')
        net=(force+reaction).reshape(len(self.nodes),2,-1)
        balance=np.sum(net,axis=0)
        moment=np.sum(self.nodes[:,0,None]*net[:,1,:]-self.nodes[:,1,None]*net[:,0,:],axis=0)
        total=(abs(force)+abs(reaction)).reshape(len(self.nodes),2,-1)
        force_scale=np.maximum(1e-12,total.sum(axis=(0,1)))
        moment_scale=np.maximum(1e-12,np.sum(abs(self.nodes[:,0,None])*total[:,1,:]+abs(self.nodes[:,1,None])*total[:,0,:],axis=0))
        if np.any(np.max(abs(balance),axis=0)>1e-7*force_scale) or np.any(abs(moment)>1e-7*moment_scale):
            raise ValueError('Elastic force or moment equilibrium exceeds tolerance')
        return dict(displacements=u,reactions=reaction,strain_energy_n_mm=energy,
            relative_equation_residual=relative,force_balance_n=balance,moment_balance_n_mm=moment)

    def stress_at(self,displacement,element_indices=None,xi=0.,eta=0.):
        if not -1<=xi<=1 or not -1<=eta<=1:raise ValueError('Stress coordinates are outside the element')
        indices=np.arange(len(self.elements)) if element_indices is None else np.asarray(element_indices,dtype=int)
        b,_,_=strain_matrix(self.coordinates[indices],xi,eta)
        u=np.asarray(displacement,dtype=float)
        if u.shape!=(self.ndof,) or not np.all(np.isfinite(u)):raise ValueError('Invalid displacement vector')
        strain=np.einsum('eij,ej->ei',b,u[self.dofs[indices]])
        in_plane=strain@self.D.T
        zz=np.zeros(len(indices)) if self.mode=='plane_stress' else self.E*self.nu/((1+self.nu)*(1-2*self.nu))*(strain[:,0]+strain[:,1])
        return np.column_stack((in_plane,zz))
