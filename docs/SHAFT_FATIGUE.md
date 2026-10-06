# Shaft fatigue and material evidence

This is an open calculation study, not a production shaft or gearbox rating.
The implementation is original Apache-2.0 code. It uses the mathematical model
in Stuart H. Loewenthal, **NASA RP-1123, Design of Power-Transmitting Shafts**
(1984), printed pages 9 and 17–19, equations 16, 19 and 28–31.
[NASA's record](https://ntrs.nasa.gov/citations/19840018973) identifies this
NASA-authored work as US-government work with public use permitted.
The repository includes numerical benchmark inputs and an original adapter;
it does not bundle the scanned report, third-party illustrations, material
tables, notch charts, paid standards or proprietary reference software.

## Workflow

Open **Design → Shaft fatigue and material evidence…**, or **Assess fatigue…**
from a shaft study. A copy of the complete shaft input is retained and
recalculated for every assessment. It is not synchronized after later changes
to the source file. **New from shaft…** starts fresh material, factors and load
conditions. The midpoint section initially offered is only an editable
placeholder; it is not an automatic search for every critical section.

1. Enter exact material/heat-treatment evidence, operating-condition yield
   strength, stress–life coefficient, reference strength/cycles and a supported
   finite-life cycle interval. Record test/survival conditions and redistribution
   rights. A material name does not supply strengths or fatigue allowables.
2. Choose each critical X coordinate and its left or right cut. At a shoulder
   or point couple these may have different section dimensions or stress.
   A cut at X=0 must face right; at the far end it must face left.
3. Enter the combined fatigue strength reduction and separate elastic static
   stress-concentration factors, with their evidence. The fatigue product must
   account for surface, size, notch, fit, environment, temperature and survival
   assumptions as applicable. Do not count the notch factor twice.
4. Declare fixed-in-housing bending and steady torque within each modeled
   rotation block. Enter shaft operating temperature; ambient temperature is
   not substituted. Other motion/load histories remain unsupported.
5. Calculate, review the range and missing-evidence findings, save the
   `.gearforge-fatigue` study, or export editable inputs, numerical JSON, HTML
   and an integrity manifest. Changes invalidate the previous report.

```text
python -m gearforge fatigue new blank.gearforge-fatigue
python -m gearforge fatigue from-shaft input.gearforge-shaft --out fatigue.gearforge-fatigue
python -m gearforge fatigue new example.gearforge-fatigue --nasa-example
python -m gearforge fatigue calculate example.gearforge-fatigue --out fatigue-assessment
python -m gearforge verify fatigue-assessment
```

A successful calculate/export exit code means the files were produced, not
that entered limits passed. Read the result's checks and assessment state.
Blank inputs remain null and unassessed. Published and synthetic examples
remain examples, even when every numerical field is populated.

## Method: nasa-rp1123-rotating-shaft-1

The initial validated arithmetic scope is a solid, circular, metallic shaft
in elastic, high-cycle, fully reversed bending with nominal steady torsion.
Axial stress and hollow sections are computed by the shaft solver but are
explicitly unsupported by this fatigue method. No ISO/AGMA compliance is
claimed. The method is not a general multiaxial fatigue or rainflow solver.

The load path is evaluated at exact section cuts from equilibrium. Drawing
samples are not used for stress. With bending moment magnitude M, torque T,
outer diameter d, second moment I and area A:

```text
sigma_b = M d / (2 I)       [M in N mm]
tau_m   = T d / (4 I)       [T in N mm]
sigma_x = N / A
local static equivalent = sqrt((Kt_b sigma_b + Kt_a abs(sigma_x))²
                               + 3 (Kt_t tau_m)²)
```

Static surface yield is checked against the entered yield strength with the
static design factor. Stationary peaks remain in these checks. Transverse
shear, plastic redistribution, buckling and interior stress maxima are not
included. Elastic yield at the selected surface invalidates its fatigue result.

Let S0 be the stress–life coefficient at one cycle, Sr the uncorrected reference
fatigue strength at Nr cycles, Sy the yield strength, and k the entered fatigue
strength-reduction product. The NASA steady-torque construction gives:

```text
Sc = k Sr sqrt(1 - 3 (tau_m / Sy)²)
b  = ln(S0 / Sc) / ln(Nr)
Ni = exp((ln(S0) - ln(Fb sigma_b)) / b)
ni = 60 abs(rpm_i) hours_i
Di = ni / Ni
modeled block damage = sum(Di)
target modeled block damage = sum(Di) required_hours / sum(hours_i)
```

The steady-torque ellipse modifies the reference fatigue endpoint; **S0 stays
fixed**. This is the RP-1123 construction, not a generic Goodman correction
applied uniformly to an entire curve. The alternating bending design factor
Fb multiplies bending demand only. It does not multiply mean torque, change
the curve's survival probability, or replace the separate static check.

The entered cycle window must start at least at 1,000 cycles and include Nr.
Ni outside that window remains unassessed. A window extending beyond Nr is an
explicit claim about applicability of this power-law continuation and requires
evidence; the app never supplies an endurance plateau or infinite-life result.
Zero bending or zero rotation produces zero modeled rotation damage only,
with no finite physical life claim. A nonpositive torque-ellipse radicand or
an out-of-range material temperature makes fatigue unavailable.

The reported sum is **rotation-block damage**. Starts, stops, speed/torque
reversals, vibration and load transitions are not counted from rpm. Duty notes
cannot approve their coverage. Miner summation ignores sequence effects.
Every study retains an unresolved duty/critical-section coverage finding;
there is no override that turns this study into a production rating.

## Reproducible open comparison

```text
python scripts/verify_fatigue_reference.py
python -m pytest tests/test_fatigue.py -q
```

The adapter checks 100 values: five load/diameter variants against independent
60-digit Decimal scalar arithmetic, plus the published example's intermediate
and sizing values. Relative tolerance for unrounded arithmetic is 1e-10 and
absolute tolerance is 1e-12. The offline fixture is
`tests/data/open_fatigue_reference.json`; CI also reruns the comparison.

The NASA example uses a 55 mm initial diameter, 3,000 N m steady torque,
three bending moments of 2,000/1,500/1,000 N m over 15,000/35,000/50,000 cycles,
a 0.4 reduction product and bending factor 2. These are historical numerical
inputs, **not current SAE 1045 material allowables**. The application uses an
original 600 mm support span, 1,000 rpm, unit static factors, a 20–40°C window
and a 1e3–1e7 cycle window only to represent the arithmetic example. Those
adapter choices are not published or physically validated material conditions.

Using the report's rounded coefficient 77.8, its one-step sizing calculation
gives 55.7441 mm, compared with its reported approximately 56 mm. The peak-only
variant recomputes to 54.5947 mm; the publication reports approximately 54 mm.
That coarser result is retained with a stated 1 mm absolute tolerance, not
treated as an exact equality. Runtime uses the unrounded stress relation
`3 (16/pi)²` instead of 77.8. The fixture records both comparisons explicitly.

These checks verify implementation and example arithmetic. They do not verify
fatigue scatter, notch data, actual material batches, manufacturing condition,
corrosion, loading histories or life in service. Tooth fatigue/contact,
lubrication/thermal behavior, bearing arrangements, housing strength and
physical gearbox qualification remain separate production requirements.
