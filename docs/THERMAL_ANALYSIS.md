# Open thermal-network studies

GearForge calculates heating and cooling through an editable network of thermal
bodies, heat-transfer paths and ordered duty phases. The original implementation,
examples and numerical fixtures are Apache-2.0 and intended for GitHub publication.
No material property table, empirical loss map or restricted standard is bundled.

**This is a conditional thermal calculation, not a qualified gearbox thermal or
service-load rating.** A fitted or measured network still requires independent
review and validation over the actual operating envelope.

## Workflow and evidence

Open **Design → Thermal network and cooling duty…**, or **Study temperatures…**
from an engineering study. The transferred source retains geometry and operating
cases. Capacities, heat losses and conductances start unknown. Assumed source
efficiency is reported for context; it never supplies the thermal heat inputs.

- Define up to 12 bodies, such as pinion, wheel, bearings, oil and housing. Enter
  each heat capacity in J/K, initial temperature, allowable temperature range,
  model-validity temperature range, source/revision and redistribution basis.
- Define undirected paths between bodies or from a body to the imposed **Ambient**
  bath. Combine parallel paths into a justified equivalent conductance.
- Enter chronological phases, durations in seconds, ambient temperatures, heat
  allocation in W and every path's conductance in W/K. Each phase can use different
  conductances and heat sources; zero is an explicit input, not a missing value.
- Record loss and cooling evidence and the relation between this sequence and the
  retained lifetime duty. Reference cases provide context, not automatic losses.
  An aggregate exposure table does not establish the actual thermal chronology.
- Calculate the entered sequence, the settled repeated cycle when unique, and a
  conservative envelope over every repeated cycle from known initial temperatures.
  Inspect each body's trajectory, continuous extrema and energy balance.

The synthetic example uses invented capacities, conductances, heat inputs and
limits. Its 1 h running / 0.5 h cooling sequence corresponds to 10,000 running
hours plus 5,000 stopped hours when repeated 10,000 times. This is an arithmetic
fixture, not a selected gearbox or a measured thermal dataset. The synthetic
gear body's settled-cycle maximum is about 60.79234545°C, not a real product rating.

```text
python -m gearforge thermal new example.gearforge-thermal --synthetic-example
python -m gearforge thermal from-study target.gearforge-study --out target.gearforge-thermal
python -m gearforge thermal calculate example.gearforge-thermal --out thermal-calculation
python -m gearforge verify thermal-calculation
```

Six desktop tabs cover bodies, paths, phases, histories, evidence and assessment.
Renaming a body/path preserves its phase data; deleting a body removes its
incident paths. Input edits invalidate calculated histories and reports. Study
files retain exact inputs and declarations. Exports contain editable inputs,
complete JSON results, an HTML report and an integrity manifest.

## Method: passive-thermal-network-1

For an isothermal body `i`, with positive heat capacity `Ci`, declared heat input
`Qi >= 0`, symmetric passive conductances `Gij >= 0` and ambient conductance `GiA`:

```text
Ci dTi/dt = Qi + sum_j Gij (Tj - Ti) + GiA (TA - Ti)
C dT/dt = f - L T
f = Q + GA TA
u = sqrt(C) T
A = C^(-1/2) L C^(-1/2) = V diag(lambda) V^T
du_modal/dt = b - lambda u_modal
u_modal(t) = u_modal(0) + [b - lambda u_modal(0)] phi1(lambda,t)
phi1(lambda,t) = (1-exp(-lambda t))/lambda
phi1(0,t) = t
```

`L` is the conductance Laplacian plus the ambient conductances on its diagonal.
The weighted matrix is symmetric positive semidefinite. The solver decomposes
each connected component separately; topology identifies insulated zero modes.
Nonzero mode ratios above `1e12` fail the numerical-conditioning guard. It uses
small-argument series for exponential integrals and does not step through every
second of a long duty phase.

Each body's derivative is a finite sum of real decaying exponentials, including
constant terms for insulated heating modes. The solver divides by the slowest
exponential, differentiates to remove one term, and recursively isolates stationary
boundaries. Each resulting interval is monotone and has at most one sign-changing
root. Tangencies are retained. Endpoints and these roots establish continuous
temperature extrema; drawing samples cannot change the calculated maximum.
Finite-precision arithmetic and stated conditioning/tolerances still apply.

The modal integral uses `phi2=(t-phi1)/lambda`, with limit `t²/2` at zero. The
reported energy balance for each phase is:

```text
generated energy = sum(Qi) duration
rejected energy = integral sum_i GiA (Ti - TA) dt
stored energy change = sum_i Ci [Ti(end) - Ti(start)]
residual = generated - rejected - stored
```

Rejected energy can be negative when a warmer ambient bath heats the gearbox.
Internal paths exchange energy between bodies and do not count as ambient loss.
The numerical residual must satisfy a relative `1e-7` energy tolerance with a
1 J reference floor. This numerical check does not validate the entered losses.

## Repeated duty and warm-up bounds

Each phase defines an affine temperature transition. Composing them gives
`T_next = P T_start + d`. A unique settled cycle solves `(I-P) T*=d`. The solver
rejects singular/poorly conditioned closure or a contraction below numerical
resolution. A component without cooling may heat indefinitely and has no unique
settled absolute temperature. The entered finite-duration response can still be
calculated. Unknown initial temperatures prevent an entered trajectory, but do
not by themselves prevent a unique settled-cycle calculation.

The settled cycle is not automatically the worst warm-up cycle. For the same
passive network and repeated inputs, differences between two trajectories obey
the homogeneous heat equation. Its maximum principle bounds every future
temperature difference between the minimum/maximum initial difference and zero.
For known initial temperatures:

```text
upper_offset = max(0, max_i [T_initial_i - T*_i])
lower_offset = min(0, min_i [T_initial_i - T*_i])
upper bound_i = periodic_maximum_i + upper_offset
lower bound_i = periodic_minimum_i + lower_offset
```

Because heat inputs are nonnegative, the lower bound is also no lower than the
coldest initial body or imposed ambient bath. These conservative bounds cover
all repetitions without pretending to calculate every warm-up cycle. A bound
that exceeds an allowable is **unresolved**, not proof that the actual trajectory
crosses it. Entered/settled extrema and all-cycle bounds are reported separately.

## Domain and production limits

Capacities and conductances are constant within each phase; each node has uniform
temperature. Ambient is one imposed infinite bath per phase. An equivalent linear
coefficient may represent conduction/convection or justified linearized effects
only over its documented model range. The solver does not infer natural-convection
coefficients, fan performance, oil flow or the network topology from the CAD model.

It does not solve nonlinear radiation, viscosity-dependent losses, local tooth
flash temperature, bearing race hot spots, lubricant film, aeration, scuffing,
wear or thermal distortion. Material allowables, measured loss maps and heat-transfer
coefficients require applicable public/redistributable evidence when bundled.
Missing inputs or prior temperature history leave dependent results unavailable.
Known model/allowable range violations are reported; unchecked conditions do not
become passes. Every overall assessment remains incomplete and production torque/
life fields remain null.

## Independent numerical verification

The comparison adapter assembles heat flows directly from the declared topology
in a **separate process**. It uses the BSD-licensed
[SciPy Radau ODE solver](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html)
and an independent shooting solution for periodic closure. It does not import
GearForge's matrices, modes or extremum isolator. No new runtime dependency is
added and no third-party solver implementation is copied.

```text
python -m venv thermal-reference-env
# Use Scripts/python.exe instead of bin/python on Windows.
thermal-reference-env/bin/python -m pip install -r scripts/requirements-thermal-reference.txt
python scripts/verify_thermal_reference.py --reference-python thermal-reference-env/bin/python
```

Eight original fixtures cover a closed-form single body, insulated heating and
exchange, changing ambient/cooling, mixed initial temperatures with internal peaks,
separated time constants, 10,000-hour operation and a bearing branch. The current
fixture compares **3,539 temperatures and energy quantities** for entered and
independently solved settled cycles. Offline tests preserve the numerical results;
CI repeats the live reference check. Further tests check analytical exponentials,
multiple/tangent stationary roots, continuous peaks, warm-up bounds, chronology,
unknown inputs, topology editing, failed saves and export integrity.

These comparisons verify numerical behavior for the stated networks. They do not
verify actual gearbox loss/cooling data, uniform-node approximations or physical
temperature predictions. See `THERMAL_VALIDATION.json` for exact version-specific
evidence and [production qualification](PRODUCTION_QUALIFICATION.md) for remaining work.
