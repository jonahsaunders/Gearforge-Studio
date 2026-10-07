"""Small-strain elastic influence matrices and frictionless unilateral loads.

Original numerical primitives for the forthcoming loaded-gear cycle model.
No gear kinematics, pressure discretization, material strength or life is supplied
by this module. A caller must establish those inputs and their applicability.
"""
import math

import numpy as np

from .models import finite

METHOD='elastic-unilateral-torque-1'


def elastic_influence(system, force_columns, fixed_dofs):
    """F.T K^-1 F and displacement bases for work-conjugate unit loads.

    Each column is a nodal force distribution per unit generalized load, not
    necessarily a point force. For a scalar normal load in N, influence has
    units mm/N. The same columns must measure the corresponding displacements.
    """
    force=np.asarray(force_columns,dtype=float)
    if force.ndim!=2:raise ValueError('Unit load distributions must be a matrix')
    solved=system.solve(force,fixed_dofs)
    displacement=solved['displacements'];matrix=force.T@displacement
    scale=max(float(np.max(abs(matrix))),1e-30)
    error=float(np.max(abs(matrix-matrix.T)))/scale
    if error>1e-9:raise ValueError('Elastic influence violates reciprocal work')
    return dict(compliance=(matrix+matrix.T)/2,displacements=displacement,
                relative_reciprocity_error=error,elastic_checks=solved)


def solve_contact_loads(compliance_mm_per_n, gaps_mm, torque_arms_mm, applied_torque_n_mm):
    """Minimize .5 f.T C f + gaps.T f, with f>=0 and arms.T f=torque.

    KKT conditions give C f + gaps - arms*rotation >= 0, complementary
    to f. C must be symmetric positive definite; all arms are positive.
    Up to 64 generalized contact patches are supported. These are force/load
    distributions, not pressure values until a caller supplies contact areas.
    """
    raw=np.asarray(compliance_mm_per_n)
    gap_raw=np.asarray(gaps_mm);arms_raw=np.asarray(torque_arms_mm)
    if raw.dtype.kind not in 'fiu' or gap_raw.dtype.kind not in 'fiu' or arms_raw.dtype.kind not in 'fiu':
        raise ValueError('Contact inputs must be real numbers, not booleans or text')
    if any(isinstance(value,(bool,np.bool_)) for source in (compliance_mm_per_n,gaps_mm,torque_arms_mm)
           for value in np.asarray(source,dtype=object).flat):
        raise ValueError('Contact inputs must be real numbers, not booleans or text')
    c=raw.astype(float);gaps=gap_raw.astype(float);arms=arms_raw.astype(float)
    n=len(gaps) if gaps.ndim==1 else 0
    if not 1<=n<=64 or c.shape!=(n,n) or arms.shape!=(n,):
        raise ValueError('Contact input dimensions must agree for 1..64 patches')
    if not all(np.all(np.isfinite(v)) for v in (c,gaps,arms)) or np.any(arms<1e-9) or np.any(arms>1e9) or np.max(abs(gaps))>1e9 or np.max(abs(c))>1e12:
        raise ValueError('Finite bounded contact data and positive torque arms are required')
    torque=finite(applied_torque_n_mm,'Applied torque magnitude N mm',0,1e12)
    cscale=float(np.max(abs(c)))
    if cscale<=0 or np.max(abs(c-c.T))>1e-10*cscale:
        raise ValueError('Contact compliance must be symmetric positive definite')
    c=(c+c.T)/2
    eig=np.linalg.eigvalsh(c/cscale)
    if eig[0]<=0 or eig[-1]/eig[0]>1e12:
        raise ValueError('Contact compliance must be positive definite and numerically resolvable')
    if torque==0:
        # Zero force does not fix the free relative position. Record the limit
        # at which the first contact would touch instead of inventing a rotation.
        first_touch=float(np.min(gaps/arms))
        return dict(method=METHOD,normal_forces_n=[0.]*n,torque_shares=[0.]*n,
                    relative_rotation_rad=None,first_touch_rotation_rad=first_touch,
                    contact_residual_mm=None,active_indices=[],strain_energy_n_mm=0.,
                    torque_residual_n_mm=0.,relative_kkt_residual=0.,iterations=0)
    # x contains torque shares, so the equality is sum(x)=1. Scaling removes
    # physical units from the active-set solve without changing its minimizer.
    h=torque*c/np.outer(arms,arms);linear=gaps/arms
    offset=float(np.min(linear));shifted=linear-offset
    scale=max(float(np.max(abs(h))),float(np.max(abs(shifted))))
    if not math.isfinite(scale) or scale<=0:raise ValueError('Contact scaling is not finite')
    h=h/scale;d=shifted/scale
    if not np.all(np.isfinite(h)) or not np.all(np.isfinite(d)):
        raise ValueError('Contact scaling is not finite')
    x=np.full(n,1/n);active=list(range(n));maximum=100+20*n*n
    for iteration in range(1,maximum+1):
        local=h[np.ix_(active,active)];ones=np.ones(len(active))
        local_linear=d[active]-np.min(d[active])
        try:
            inverse=np.linalg.solve(local,np.column_stack((ones,local_linear)))
        except np.linalg.LinAlgError as exc:raise ValueError('Contact active stiffness is singular') from exc
        denominator=float(np.sum(inverse[:,0]))
        if not math.isfinite(denominator) or denominator<=0:raise ValueError('Contact active compliance is unresolved')
        dual=(1+float(np.sum(inverse[:,1])))/denominator
        candidate=np.zeros(n);candidate[active]=dual*inverse[:,0]-inverse[:,1]
        if not np.all(np.isfinite(candidate)):raise ValueError('Contact load distribution is unresolved')
        negative=[i for i in active if candidate[i]<-1e-12]
        if negative:
            leaving=min(negative,key=lambda i:x[i]/(x[i]-candidate[i]))
            fraction=x[leaving]/(x[leaving]-candidate[leaving])
            x+=fraction*(candidate-x);x[leaving]=0.;active.remove(leaving)
            if not active:raise ValueError('Contact active set lost its load-bearing patch')
            continue
        x=np.maximum(candidate,0.)
        if np.sum(x)<=0:raise ValueError('Contact load distribution is unresolved')
        x/=np.sum(x)
        gradient=h@x+d;dual=float(np.mean(gradient[active]))
        inactive=[i for i in range(n) if i not in active]
        entering=min(inactive,key=lambda i:gradient[i]) if inactive else None
        if entering is not None and gradient[entering]<dual-1e-11:
            active.append(entering);continue
        forces=torque*x/arms
        physical_gradient=c@forces+gaps
        rotation=float(np.dot(x,physical_gradient/arms))
        residual=physical_gradient-arms*rotation
        characteristic=max(float(np.max(abs(c@forces))),float(np.ptp(gaps/arms)*np.max(arms)),1e-30)
        positive=x>1e-10
        error=max(float(np.max(np.maximum(-residual,0.))),float(np.max(abs(residual[positive]))))/characteristic
        torque_residual=float(arms@forces-torque)
        if error>1e-8 or abs(torque_residual)>1e-10*torque or not np.all(np.isfinite(forces)):
            raise ValueError('Contact equilibrium or complementarity is unresolved')
        return dict(method=METHOD,normal_forces_n=forces.tolist(),torque_shares=x.tolist(),
                    relative_rotation_rad=rotation,first_touch_rotation_rad=float(np.min(gaps/arms)),
                    contact_residual_mm=residual.tolist(),active_indices=np.flatnonzero(positive).tolist(),
                    strain_energy_n_mm=float(.5*forces@(c@forces)),torque_residual_n_mm=torque_residual,
                    relative_kkt_residual=error,iterations=iteration)
    raise ValueError('Contact active-set iteration limit exceeded')
