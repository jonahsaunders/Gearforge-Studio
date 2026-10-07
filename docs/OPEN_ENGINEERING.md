# Open engineering development

The product owner requires the app, tests and bundled reference data to be
publishable on GitHub. The project does not depend on access to paid standards,
proprietary calculation packages, confidential material databases or unpublished
reference results. Public availability alone is not an open-source license.

GearForge's new calculation implementation is original application code under
the repository's Apache-2.0 license. It implements mathematical geometry and
statics relations; no third-party implementation, document, illustration or
standard text is copied into the runtime. Existing runtime dependencies retain
their licenses and release notices. New dependencies or copied datasets must
have an explicit redistribution license and retained attribution before inclusion.

The shaft fatigue extension uses an original implementation of a publicly
available NASA-authored method and a numerical worked example. See
[shaft fatigue and its redistribution basis](SHAFT_FATIGUE.md). Public access
does not by itself authorize copying third-party tables from a document.

The [tooth-contact extension](CONTACT_ANALYSIS.md) uses original Hertz arithmetic,
original synthetic pressure-life inputs and a separate MIT SlipPY reference solver.
Its numerical fixtures contain no copied implementation or restricted tables.

The [thermal-network extension](THERMAL_ANALYSIS.md) uses original heat-balance
and modal arithmetic, with independent BSD-licensed SciPy ODE verification.
Synthetic losses, capacities and cooling inputs are not material/property data.

The [rack-generated tooth profile](TOOTH_PROFILES.md) uses original rolling
kinematics and a rounded cutter. Independent ray/cutter intersections verify
266 radii using BSD SciPy numerical minimization; no cutter table or restricted
manufacturing data is bundled.

## Accepted development target

Start with an enclosed, single-stage steel spur gearbox at 250 W input,
1,500 rpm, 5:1 reduction, 10,000 operating hours and 20–40°C ambient. Extend to
two-stage spur/helical, polymers and printed processes, planetary and finally
the other gear families. This is a development target, not a measured rating.

The included study uses 20/100 teeth, 2 mm normal module and 20 mm face width
as an editable calculation fixture. These are not selected supplier parts.
The initial 95% mesh efficiency is an explicit assumption. The actual material
grade, heat treatment, lubricant, bearing part numbers, reliability requirements,
overload duty and qualification acceptance criteria remain to be established.

## Use the engineering study

In the desktop **Design → Engineering study…** opens the target fixture.
**Design → Study selected stage…** transfers a generated spur/helical stage's
geometry, required operating torque, speed, life and source declarations.
For a multistage candidate, select a stage explicitly. The study covers that
stage only and does not imply verification of the rest of the assembly.

Edit geometry, allocate the complete operating life across duty rows, and
record material/process and evidence references. Both negative speed and
negative torque represent reverse motoring. Zero speed records a stationary
load. Regenerative/braking operation requires another loss model and is rejected.
Starts are recorded here without inventing transient stresses. The separate
[local stress history study](STRESS_HISTORY.md) accepts explicit signed samples,
checks duration/start coverage and assesses bounded uniaxial cyclic damage.
It does not infer a local history from these quasi-static gear loads.

```text
python -m gearforge study new target.gearforge-study
python -m gearforge study calculate target.gearforge-study --out target-calculation
python -m gearforge verify target-calculation
```

The dedicated `.gearforge-study` format keeps analytical studies separate from
prototype `.gearforge` projects. An export contains editable inputs, complete
JSON results, a readable HTML report and an integrity manifest. Recalculation is
required after any edit. The input fingerprint includes geometry, duty and source
declarations; it is an integrity identifier, not a reviewer signature.

## Analytical method: external-involute-1

Inputs use millimetres, degrees, N·m, rpm, hours and °C. Internal angles use
radians. The scope is a compatible external, parallel-axis involute gear pair
in the normal system, with opposite helix hands, standard unit addendum and
0.25-module clearance. Normal profile shifts and tip shortening are explicit.

For normal module `mn`, normal pressure angle `an`, helix angle `b`, tooth
counts `z1/z2` and normal profile shifts `x1/x2`:

```text
mt = mn / cos(b)
at = atan(tan(an) / cos(b))
inv(a) = tan(a) - a
inv(aw) = inv(at) + 2 tan(an) (x1 + x2) / (z1 + z2)
a0 = mt (z1 + z2) / 2
a = a0 cos(at) / cos(aw)
y = (a - a0) / mn
k = x1 + x2 - y
di = mt zi
dbi = di cos(at)
dwi = 2 a zi / (z1 + z2)
dai = di + 2 mn (1 + xi - k)
dfi = di - 2 mn (1.25 - xi)
```

The operating angle uses a bracketed inverse-involute solution. Contact ratio
comes from the available involute path divided by the transverse base pitch;
overlap is `face_width * abs(sin(b)) / (pi * mn)`. Below-base-circle contact,
pointed tips and approximate rack-generation undercut are reported. The helical
undercut check uses an equivalent spur approximation and does not replace cutter
simulation. The initial development envelope is 15–25° normal pressure angle,
up to 30° helix and transverse contact ratio 1–2.5; bounds are scope controls,
not proof that all designs within them have been validated.

Mesh loads follow torque equilibrium on the operating pitch circle:

```text
Ft = 2000 T / dw1
|Fr| = abs(Ft) tan(aw)
bw = atan((a / a0) tan(b))
Fa = Ft tan(bw)
power_W = T rpm 2 pi / 60
revolutions = abs(rpm) 60 hours
```

The force signs use pinion torque/helix-hand convention. They are not global
shaft-coordinate reactions. The common mesh force is ideal and quasi-static;
assumed efficiency only estimates transmitted power/torque and loss power.
Stationary output torque after efficiency is left unavailable. Friction force
distribution, dynamics, load sharing, misalignment and external shaft forces are
outside this calculation. Revolutions are exposure, not fatigue damage. Loss
power is not a temperature or thermal-capacity prediction.

## Reproduce the independent geometry comparison

[FreeCAD Gears](https://github.com/looooo/freecad.gears) is an openly licensed
GPL-3.0-or-later reference. The comparison runs its pure Python geometry in a
separate process from a clean checkout pinned to
`83ec154b1925347622b61812f75d2ed51e956b9f`. It is not installed or bundled as a
GearForge runtime dependency. Its source and license remain in its own checkout.

```text
git clone https://github.com/looooo/freecad.gears.git reference/freecad.gears
git -C reference/freecad.gears checkout 83ec154b1925347622b61812f75d2ed51e956b9f
python scripts/verify_open_reference.py --reference-checkout reference/freecad.gears
```

The script compares 72 scalar dimensions/angles across six GearForge-authored
spur/helical cases, including profile shifts and both helix hands. Its output
records the exact reference revision, inputs, outputs, scope and tolerances.
`tests/data/open_geometry_reference.json` retains these numerical results for
offline regression. It contains no copied implementation or document text.
The reference's profile-shift inputs are converted to the transverse system;
its independently calculated center distance determines tip shortening.

The comparison verifies reference/base/tip/root diameters, pressure angles and
operating center distance within the recorded tolerance. It does **not** verify
fatigue strength, tooth contact under deformation, material allowables or life.
Additional tests check hand-derived power/force/exposure cases, reversal/rest,
invalid inputs, edit invalidation, save failures and export integrity.

Public manufacturer explanations of the same relations are linked for context:
[geometry](https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html)
and [gear forces](https://khkgears.net/new/gear_knowledge/gear_technical_reference/gear_forces.html).
Their documents and images are not bundled or represented as openly licensed.

## Remaining production work

The [shaft and bearing load-path study](SHAFT_ANALYSIS.md) now connects these
mesh loads to explicit support geometry, stepped shaft sections and elastic
response. Its independent verification uses a separately installed MIT-licensed
finite-element reference. It does not infer fatigue allowables or bearing capacity.

Develop and independently verify open fatigue/contact, bearing, shaft, assembly,
thermal and manufacturing methods, with explicit supported domains and uncertainty.
Use redistributable material and test datasets whose provenance is known; never
derive a production allowable from a material name or free-text note. Provide a
reviewed physical-test protocol and record actual results. Engineering approval
must bind the exact inputs, method version and manufacturing definition.

No ISO/AGMA compliance or certification is claimed. If a future customer requires
a specific standard, that requirement needs an explicit, separately supported
compliance assessment. It is not silently satisfied by similar formulas or an
open-source implementation's name.

The [bearing duty assessment](BEARING_ANALYSIS.md) uses the recalculated load path
with explicit bearing capacities, case factors and operating limits. Its open
verification adapter checks basic fatigue arithmetic against 60-digit Decimal
results from original synthetic cases; supplier factors and service life remain
outside that verification. No restricted supplier table is included.

## Open tooth-root elasticity

The [generated-root stress study](ROOT_STRESS.md) uses original Q4/Q9 plane
elasticity, explicit support/loading assumptions and synthetic material fixtures.
A separate BSD-3-Clause scikit-fem 12.0.2 process verifies 4,582 quantities with
its own basis/weak-form assembly. It is a test reference, not an app dependency.
No material allowables, standard text or reference implementation is copied.
SciPy, already present through CAD dependencies, is now an explicit direct
dependency for the original sparse elastic solver. Root fatigue remains unqualified.
