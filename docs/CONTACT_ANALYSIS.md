# Open tooth-contact and surface-fatigue studies

GearForge implements original external-spur Hertz line-contact calculations and
bounded interpolation of explicitly entered pressure-life curves. It bundles no
material allowables, supplier tables, paid standards or proprietary calculations.
All example inputs and numerical fixtures are original, GitHub-publishable data
under the repository's Apache-2.0 license. They are not measured material data.

**This is an elastic contact study, not a production tooth or gearbox rating.**
The software evaluates declared conditions; it does not validate their physical
applicability. Actual load distribution, surface treatment, lubricant, temperature,
survival probability and durability evidence remain necessary.

## Workflow

Open **Design → Tooth contact and surface fatigue…**, or **Study tooth contact…**
from an engineering study. The transfer retains the complete geometry and duty,
then starts with unknown material properties and load factors. The six tabs cover
each material, duty conditions, contact-path diagrams, provenance and assessment.
**Synthetic example** demonstrates the arithmetic using invented material data.

```text
python -m gearforge contact new example.gearforge-contact --synthetic-example
python -m gearforge contact from-study target.gearforge-study --out target.gearforge-contact
python -m gearforge contact calculate example.gearforge-contact --out contact-calculation
python -m gearforge verify contact-calculation
```

Save/reopen `.gearforge-contact` retains every numeric input and source declaration.
Changes clear calculated results. The export contains editable inputs, complete
JSON results, a readable HTML report and an integrity manifest. A fingerprint is
an integrity identifier, not evidence of engineering approval.

## Method: external-spur-line-contact-1

The scope is smooth, frictionless, nominally aligned external spur teeth with
positive involute curvatures and isotropic linear elasticity. Helical and other
families are unsupported. Geometry findings from the retained engineering study
prevent calculation, including undercut and below-base-circle contact. No generated
root profile, tooth stiffness, contact deformation or edge relief is inferred.

With operating center distance `a`, operating pressure angle `aw`, base radii
`rb1/rb2` and tip radii `ra1/ra2`, define:

```text
C = a sin(aw)
u1 = sqrt(ra1² - rb1²); u2 = sqrt(ra2² - rb2²)
rho1_start = C - u2
L = u1 + u2 - C
rho1(t) = rho1_start + t; rho2(t) = C - rho1(t), 0 <= t <= L
R* = rho1 rho2 / (rho1 + rho2)
E* = 1 / [(1 - nu1²)/E1 + (1 - nu2²)/E2]
w = Fn K_normal K_face q / effective_face_width
b = sqrt(4 w R* / (pi E*))
p0 = sqrt(w E* / (pi R*))
```

Lengths are mm, force N, moduli and pressure MPa (N/mm²), and line load N/mm.
`b` is the contact **half-width**, not the full contact width. `Fn` is the
retained quasi-static normal mesh force. Normal and face multipliers and effective
width must be entered; blank values prevent pressure results. Unity factors in
the synthetic example are assumptions, not validated application factors.

Two explicit load-sharing models are available:

- **Full mesh-load envelope:** `q=1` for each examined tooth pair separately.
  It is a local envelope, not a simultaneous distribution of the mesh force.
- **Ideal equal sharing:** `q=1/n`, where `n` counts geometric contacts separated
  by the transverse base pitch. This conserves mesh force across ideal pairs,
  but does not resolve their relative stiffness, errors or actual entry/exit load.

Pair counts change at multiples of base pitch and their offsets from `L`. The
calculation splits the path at these exact locations and retains both one-sided
limits. Within each interval `rho1 + rho2` and `q` are constant, so `p0²` is
proportional to `1/[rho1 (C-rho1)]`. The pressure maximum occurs at an interval
endpoint. Exact limits determine maxima; display samples cannot change them.
The pitch point and curvature-balance point are also retained.

A development guard requires half-width <=5% of both local curvature radii and
effective face width. A violation leaves fatigue damage unavailable. Passing this
guard does not establish edge-contact or elastic validity. Each material needs
its own declared maximum elastic pressure and applicable temperature range.
Missing limits remain explicitly unassessed even when conditional arithmetic
can be calculated. Known exceeded limits suppress fatigue damage.

Ideal surface speeds are `abs(omega1) rho1` and `abs(omega2) rho2`, converted to
m/s. Sliding is their absolute difference; the slide/roll ratio is
`2(v1-v2)/(v1+v2)` and is unavailable at rest. These are kinematics, not a film
thickness, frictional heating, lubrication or thermal-capacity prediction.

## Pressure-life data and cycle accounting

Each material requires its own curve, source/revision, redistribution basis and
applicable surface, lubricant, slide/roll, temperature and survival conditions.
The curve contains 2–50 points, strictly increasing cycles and decreasing peak
Hertz pressure. Interpolation is linear in log(cycles) versus log(pressure), only
inside the entered range. There is no extrapolation or assumed endurance plateau.
An empty curve stays unknown. A material name supplies no strength.

The pressure design factor multiplies peak pressure, separately from load factors.
It changes the curve demand, not the displayed physical pressure. For each duty
block, cycles per tooth equal that member's absolute revolutions. A tooth is loaded
once per revolution in this single-mesh model. Pinion/wheel counts differ by ratio;
mesh frequency, tooth count and spatial drawing samples add no extra fatigue cycles.
Opposite torque flanks accumulate separately.

Modeled damage is `sum(n_i/N_i)` on each flank. The geometry and sharing shape are
fixed across duty, and the factors act as scalar multipliers, so the worst pressure
station is common to all blocks. Damage is not summed over spatial nodes. A loaded
block outside its curve makes its flank damage unavailable. Zero-load or stationary
blocks add no rotation-fatigue damage within the supported contact domain; stationary
pressure still participates in elastic-limit checks. No infinite-life claim follows.

Starts, reversal transitions, sequence effects, tooth-root bending, micropitting,
wear, scuffing and actual assembly life are not modeled. The overall assessment
remains incomplete even when every entered limit passes. `production_approved`
stays false and rated gearbox torque/life remain null.

## Independent open reference

[SlipPY](https://github.com/FrictionTribologyEnigma/slippy), MIT licensed,
provides a [documented Hertz line-contact solver](https://slippy.readthedocs.io/en/latest/generated/slippy.contact.solve_hertz_line.html).
The comparison runs its solver from a clean, separate checkout pinned to
`a4fbb447fc494d0480661ee41ef15fdc82e7423c`. It is not a GearForge runtime dependency.
No reference implementation, document text or images are copied into the app.

```text
git clone https://github.com/FrictionTribologyEnigma/slippy.git reference/slippy
git -C reference/slippy checkout a4fbb447fc494d0480661ee41ef15fdc82e7423c
python -m venv reference-env
# Use reference-env's Python for the next commands (Scripts/python.exe on Windows).
reference-env/bin/python -m pip install -r scripts/requirements-contact-reference.txt
python scripts/verify_contact_reference.py --reference-checkout reference/slippy --reference-python reference-env/bin/python
```

The original adapter converts mm/MPa inputs into SI units for the reference API.
It compares effective radius/modulus, half-width and pressure for eight cylinder
cases and critical cuts in six spur-study fixtures: **208 scalar comparisons**.
The offline fixture records inputs, numerical outputs, scope and tolerances.
GitHub CI repeats the live reference comparison in a separate job.

This verifies the Hertz arithmetic. GearForge supplies the gear curvatures and
loads to the reference, so the comparison does not independently verify those
quantities, load sharing, tooth stiffness, factors or fatigue life. Other tests
check curvature against parametric involute derivatives, pressure integration,
pair-force conservation, continuous maxima, curve boundaries, reversals, stationary
loads, different member cycle counts, saved inputs and desktop invalidation.
The existing independent geometry suite remains separate.

See `CONTACT_VALIDATION.json` for version-specific evidence and
[production qualification](PRODUCTION_QUALIFICATION.md) for the remaining work.
