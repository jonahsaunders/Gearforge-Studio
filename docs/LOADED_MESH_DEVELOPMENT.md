# Loaded mesh and full-cycle development

The requested production gearbox ratings require stresses at fixed material
points through an actual loading cycle. The [root study](ROOT_STRESS.md) currently
samples prescribed patches on a truncated sector. The following numerical
building blocks are implemented and independently checked in the development
tree. **They are not yet an integrated loaded-mesh desktop study or a validated
gear fatigue history.** There is no new production approval or life calculation.

## Whole-gear elasticity

`annular_mesh.annular_gear_mesh` meshes the complete generated spur outline with
conforming Q9 displacement elements on bilinear geometry. Tooth zero points
along +Y; tooth indices increase clockwise. The circular bore is fully clamped.
The circumferential seam shares corner and edge-midpoint nodes, so it introduces
neither a free cut face nor duplicate material. A breakpoint at every tooth
boundary keeps rotationally identical teeth identically subdivided, including
the closing seam. Geometry joins and requested load-patch ends are retained.

All teeth remain in the elastic system. Neighboring and remote tooth loads can
therefore contribute to stress at the selected material point. The existing
prescribed pressure-patch integrator now supports any tooth index and rotates
its normal loads consistently. The scalar pressure weights preserve the signed
moment about the gear center. The 40,000-cell / 90,000-node resource limit remains
explicit; an oversized mesh is rejected rather than silently coarsened.

This model still has a rigid bore and uniform effective width. It does not model
a flexible shaft, keyway, spoke/web thickness changes, interference fit or 3D
face effects. These support assumptions matter: NASA's openly available
[spur-gear finite-element study](https://ntrs.nasa.gov/citations/19820020770)
examines how support and rim thickness change calculated root stress. That paper
provides context; its figures and numerical results are not bundled or claimed
as verification of this implementation.

## Work-conjugate elastic influence

For nodal force distributions `F` per unit generalized contact load, the solver
computes displacement bases `U = K^-1 F` with the declared bore constraints and
influence `C = F.T U`. The same force weights measure the generalized contact
deflection. For unit loads in N, `C` has units mm/N. Off-diagonal entries retain
the coupling through the gear body; they are not discarded to create independent
tooth springs. The reciprocal-work discrepancy must be below `1e-9` before the
matrix is symmetrized within that numerical tolerance.

`elastic_contact.solve_contact_loads` accepts a symmetric positive-definite
combined compliance matrix, signed unloaded gaps `g`, positive torque arms `a`,
and applied torque magnitude `T`. It solves the convex problem

```text
minimize  0.5 f.T C f + g.T f
subject to f >= 0 and a.T f = T
```

Its conditions are `r = C f + g - a theta >= 0` and `f_i r_i = 0`.
Loaded patches close; unloaded patches cannot transmit a tensile force. The
active-set calculation uses torque shares, checks equilibrium and complementarity,
and retains forces, gaps after elastic approach, relative rotation, active
contacts and strain energy. At zero torque, forces are zero but relative
rotation is nonunique: the result leaves it unknown and records only the
first-touch bound. A singular or poorly conditioned compliance is rejected.

There are at most 64 contact variables, a compliance condition limit of `1e12`,
arms between `1e-9` and `1e9` mm, absolute gaps at most `1e9` mm, compliance entries
at most `1e12` mm/N and torque at most `1e12` N mm. Those broad numerical bounds
are not physical validity or safe operating limits. The existing elastic solve
accepts up to 24 simultaneous unit-load columns. More detailed surface-contact
discretizations will need a separately bounded assembly strategy.

## Mating geometry and direction

`mesh_kinematics.spur_mesh_contacts` enumerates nominal involute contact candidates
after a stated number of base pitches. Gear centers are `(0,0)` and `(0,a_w)` in
one right-handed frame. Both generated involutes must cover the complete nominal
tip-to-tip active path, and their base pitches must match. Unsupported engagement
is rejected rather than shortened to conceal interference.

If `q1` is the pinion roll distance from its base-circle tangent, the wheel roll
distance is `q2 = a_w sin(alpha_w) - q1`. Adjacent contact pairs are separated by
one base pitch. The pinion rotates by minus one tooth pitch and the wheel by plus
one tooth pitch per forward mesh period when angles are measured clockwise.
Reverse motion reflects the geometry and changes the loaded flank. Entry/exit
events remain explicit, including contact points at tooth tips.

The implementation checks coincidence of the two transformed flank points,
opposite surface normals, tangency, tooth indexing and signed torque arms through
complete revolutions. These checks exposed and corrected the driven-wheel flank
selection in root method revision 3; see its [migration note](ROOT_STRESS.md#fixed-material-points-and-signed-stresses).

## Independent checks

The separate BSD-3-Clause scikit-fem 12.0.2 process solves original full 20-tooth
pinion and 100-tooth wheel meshes, covering plane stress and plane strain with
three independently rotated loads on each. **159,456 live comparisons** cover
nodal displacements, support reactions, compliance, selected point tensors and
energy. The compact regression fixture retains the input studies, mesh counts,
compliance, point stresses and energies; it does not store every displacement.
Relative tolerance is `2e-8`; absolute tolerances are `2e-11 mm` for displacement,
`2e-8 N` for reaction, `2e-11 mm/N` for compliance, `2e-9 MPa` for point stress and
`2e-11 N mm` for energy.

A separate SciPy 1.18.1 SLSQP process identifies contact sets in 110 original
positive-definite examples with 2–12 patches. It resolves each identified set's
equations and independently checks nonpenetration and equilibrium. **1,760
comparisons** cover force, rotation, residual gap and energy, at `2e-8` relative
and `2e-9` absolute tolerance in the corresponding units. Exhaustive enumeration
of all possible contact sets on additional small fixtures, exact parallel-spring
solutions, contact transitions, scaling and permutation tests supplement it.

Analytic Lamé solutions for a clamped circular annulus check mesh convergence in
both plane modes. Topology, reciprocal work, rotational symmetry, superposition,
invalid inputs and resource limits have separate regression checks.

```text
python scripts/verify_loaded_mesh_reference.py --reference-python reference-env/Scripts/python
```

Use the same openly licensed reference environment as the root-stress checks.
No reference package is added to the application's runtime dependencies.
The [development validation record](LOADED_MESH_VALIDATION.json) retains exact
source hashes, test results, reference versions and the current packaging scope.

## Work remaining before a full-cycle result

The next integration must construct and independently verify the common contact
interface for both gears, including unloaded geometric gaps and a pressure/area
discretization that remains meaningful near entry and exit. Prescribing one
patch width and solving its total force does not by itself solve contact pressure.
Then it must traverse complete revolutions, retain simultaneous tooth loads,
evaluate fixed material points, establish spatial/contact/time refinement, and
record a real chronology for the entered duty. Starts, reversals and dynamic
effects need their own applicable model. Qualified material/process curves,
fatigue applicability, manufacturing/assembly evidence, independent engineering
review and physical qualification are still needed for production load/life ratings.
