# Rack-generated spur tooth profiles

Method `rolling-rack-spur-1` defines the root geometry needed before a meaningful
tooth-root stress calculation can be developed. It is an original implementation
of rigid rolling kinematics and a rounded straight rack cutter. **Geometry is
not a tooth bending, fatigue or production gearbox rating.** No proprietary
standard, cutter table, external gear implementation or material data is required.

## Desktop and command line

Open **Design → Rack-generated tooth roots…**, or **Study tooth roots…** from an
engineering study. The latter retains the exact geometry/duty/source inputs.
Select pinion or wheel, declare cutter depth and tip radius divided by module,
and record cutter source/revision and the basis for sharing that data. A fresh
study leaves the actual tip radius unknown. **Synthetic example** explicitly
loads an original invented cutter for numerical verification.

The four tabs contain cutter inputs, tooth/whole-gear views, the retained source
and the assessment. Changing an input clears the old result. The source geometry
is read-only here; edit its engineering study and transfer it again to create a
fresh cutter study. Save/reopen `.gearforge-tooth` files without rounding numeric
inputs. Declared provenance is not independent verification of that evidence.

```text
python -m gearforge tooth new cutter.gearforge-tooth
python -m gearforge tooth new example.gearforge-tooth --synthetic-example
python -m gearforge tooth from-study target.gearforge-study --role wheel --out wheel.gearforge-tooth
python -m gearforge tooth calculate example.gearforge-tooth --out tooth-calculation
python -m gearforge verify tooth-calculation
```

An available profile exports editable inputs, calculation JSON, an HTML report,
sampled closed DXF, SVG and CSV coordinates, plus a SHA-256 integrity manifest.
An unsupported profile exports inputs/report/JSON only, with the reason; it never
exports a misleading outline. Export uses a new directory and a staged rename.
No output approves production, rated torque or gearbox life.

DXF uses R2000 `LWPOLYLINE`, a closed flag and `$INSUNITS=4` for millimetres.
Coordinates use +Y for the central tooth and +X to its right. Repeated sectors
traverse clockwise. CSV omits a duplicate closing vertex; consumers must close
the last-to-first edge. These are unbored transverse profiles, not complete gear
drawings or solids. Check units and import behavior in the intended CAD/CAM tool.

## Explicit cutter and pair geometry

The retained external spur pair supplies module `m`, tooth count `z`, pressure
angle `a`, profile shift `x` and tip radius including pair tip shortening. The
cutter supplies depth `h`, corner radius `rho` and individual reference-circle
tooth-thickness reduction `b`. All lengths below are millimetres; angles radians.

```text
R = m z / 2                         rolling/reference radius
rb = R cos(a)                      base radius
s0 = pi m / 4 - b / 2             unshifted half reference tooth thickness
vc = -h + rho
uc = s0 + (h-rho) tan(a) + rho / cos(a)
D = h - rho - xm
rf = R + xm - h                    generated root radius
```

The right-hand tooth space is cut by a rack whose left straight flank is
`u + v tan(a) = s0`. Its rounded lower-left corner is
`u=uc-rho cos(psi), v=vc-rho sin(psi)`, for `a <= psi <= pi/2`.
The flat tip has width `pi m - 2uc`; overlap is rejected. The geometry includes
no protuberance, finishing/grinding stock, edge breaks, asymmetric flank or
helical hob. Tooth-thickness reduction is for this one member; it is not an
assembled backlash value. Tolerances, thermal growth and elastic motion are separate.

## Rolling envelope and tangent joins

At rack pose `theta`, transform a cutter point into gear coordinates by

```text
P = Rot(theta) (u + R theta, R + xm + v)
```

The instantaneous normal relative velocity vanishes on the generated envelope:

```text
(xm + v) cos(psi) - (u + R theta) sin(psi) = 0
theta = ((xm + v) cot(psi) - u) / R
```

Substitution gives the analytic root curve. At `psi=pi/2` it is tangent to the
root circle; at `psi=a` it meets the involute. The involute half-angle at radius
`r` is

```text
half(r) = [s0 + xm tan(a)] / R + inv(a) - inv(acos(rb/r))
inv(t) = tan(t) - t
```

The join position is checked numerically against this separate involute relation.
The reference thickness is therefore `pi m/2 + 2xm tan(a) - b`, and actual root
diameter can differ from the source pair's conventional `1.25m` cutter depth.
That difference is reported, not silently propagated into other studies.

## Continuous regularity and undercut rejection

The supported envelope must be regular and strictly monotone in polar angle.
This is checked over the full corner, not just sampled vertices. For
`s=sin(psi)` on `[sin(a),1]`, its tangent speed and polar derivative depend on

```text
Q(s) = R rho s^3 + rho D s + D^2
H(s) = R s^2 - rho s - D
```

Both must remain positive, with small scale-relative numerical margins.
The exact minima are evaluated at endpoints and any interior stationary point:
`sqrt(-D/(3R))` for `Q` when `D<0`, and `rho/(2R)` for `H`.
The resulting curve has decreasing radius and increasing polar angle from the
involute join toward the root land. Join/tip/root ordering and positive tip
thickness then prevent self-intersection within this supported sector.

If these checks fail, the study records undercut/cusp/fold as unsupported.
Trimming an undercut envelope requires another method and is not approximated
by drawing a straight radial segment. Higher positive shifts with negative `D`
remain supported when the continuous minima and other geometry checks pass.

The nominal active-start radius follows the retained pair's ideal line of
action and the other gear's tip. If that contact reaches below the generated
involute start, the report identifies it. This is a member-specific geometric
check, not loaded tooth contact, complete pair interference or strength analysis.
Source geometry findings are retained in the assessment.

## Sampling and verification

The analytic profile is independent of exported polylines. Each segment is
adaptively subdivided using three interior chord-distance probes and half the
requested tolerance as a safety factor. This is **not a certified maximum
chord-error bound**. Tests additionally check dense off-probe locations and
refinement. Export is limited to 200,000 vertices. Use a tolerance appropriate
to later meshing/import and establish manufacturing tolerances independently.

The separate original cutting adapter intersects each radial ray with the
actual rack's straight edges, rounded corners and flat tip at many poses. It
uses [SciPy bounded minimization](https://docs.scipy.org/doc/scipy/reference/optimize.minimize_scalar-bounded.html)
to find the first cutting radius. The reference process does not import the
application's envelope, its derivatives, regularity checks or ray interpolation.
It shares only physical cutter definitions and requested ray angles.

```text
python -m venv reference-env
reference-env/Scripts/python -m pip install -r scripts/requirements-tooth-reference.txt
python scripts/verify_tooth_reference.py --reference-python reference-env/Scripts/python
```

On Unix use `reference-env/bin/python`. The reference pins NumPy 2.4.6 and SciPy
1.18.1 in its separate environment. Seven original fixtures compare 266 radii,
including both joins, pinion/wheel, low-tooth positive shift, negative shift,
deeper/shallow cutters, thickness reduction and negative `D`. Tolerance is
`2e-9` relative or `2e-7 mm` absolute. Original numeric results are retained in
`tests/data/open_tooth_reference.json`; no third-party implementation or document
content is copied. Existing dependency licenses/notices apply.

Other tests check rolling-contact closure, both tangent joins, continuous-domain
rejection, periodic symmetry, sampled closure/convergence, strict files, editing,
save failures, CLI and manifest integrity. Numerical agreement establishes this
geometry calculation only. The [root elastic study](ROOT_STRESS.md) now adds
numerically checked stresses. Actual cutter/process evidence, root fatigue, 3D load distribution, manufacturing tolerances and physical qualification
remain. The earlier prototype CAD retains its distinct approximate root outline.

Use **Study root stress…** to retain this profile in the elastic editor with
fresh material/support/load evidence. This does not modify the prototype CAD.
