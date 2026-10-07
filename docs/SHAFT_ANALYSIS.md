# Shaft and bearing load paths

Version 1.0.0rc5 adds an original analytical shaft model under the application's
Apache-2.0 license. It calculates loads and elastic response from explicitly
defined geometry instead of assuming that every gear acts at midspan. It is a
foundation for component selection and subsequent strength/life assessment;
neither a bearing life rating nor shaft fatigue approval is produced.

## Workflow

Open **Design → Shaft and bearing loads…**, or open an engineering study and
choose **Study shaft loads…** for its pinion or wheel. Gear-study transfer
preserves all duty cases, speeds, durations and source inputs. It adds the ideal
mesh force, its torque, the bending couple caused by off-axis axial thrust, and
a balancing coupling torque. Shaft dimensions and bearing positions are an
editable layout; they are not inferred supplier or production drawing dimensions.

1. Set the shaft length, both radial support positions and one axial locator.
2. Enter contiguous sections with actual outer/inner diameter and elastic moduli
   at operating temperature. The supplied steel values are illustrative.
3. Set operating cases and enter all applied forces/couples, including external
   coupling, belt or pulley forces. Applied torques must balance.
4. Calculate, then inspect individual bearing loads, the load-path diagrams,
   deflection at each gear, bearing slope and nominal section stress.
5. Save a `.gearforge-shaft` study and export its complete calculation package.
   Keep this file with the gearbox design; catalog backup does not include it.

The case selector changes the displayed diagram. The quantity selector shows
bending, shear, deflection, slope, torque, twist or nominal surface stress. Hover
for sampled values. The report includes calculated continuous extrema and their
positions; diagram samples do not define the maximum. Input edits invalidate
the old result. Renaming a case preserves its associated load rows.

```text
python -m gearforge shaft new input.gearforge-shaft
python -m gearforge shaft from-study gearbox.gearforge-study --role wheel --out output.gearforge-shaft
python -m gearforge shaft calculate input.gearforge-shaft --out shaft-calculation
python -m gearforge verify shaft-calculation
```

The export contains `design.gearforge-shaft`, `calculation.json`, `report.html`
and `manifest.json`. Its fingerprint covers sections, supports, every load case,
notes and retained source inputs. A gear study retained inside a shaft study is
initial provenance; later manual edits do not automatically synchronize loads
with that source. An integrity check is not a reviewer signature or approval.

## Coordinates and method: two-support-shaft-1

Use a right-handed frame with X along the shaft and Y/Z transverse. Forces use N,
applied moments/torques N·m, geometry mm, elastic moduli MPa, and rotations rad.
Internal moments are converted to N·mm before integration. For gear-study
transfer both shafts share axes: +Y points from the pinion to the wheel and +Z
completes the right-handed frame. The wheel rotates in the opposite direction.

Let bearing positions be `a < b`, and applied loads act at `xi`. Bearing reaction
vectors act **on the shaft**; loads acting on the bearing are their negatives.
With applied couples in N·mm, equilibrium gives:

```text
Rb_y = -(sum(Fy_i (xi-a)) + sum(Mz_i)) / (b-a)
Rb_z = (-sum(Fz_i (xi-a)) + sum(My_i)) / (b-a)
Ra_y = -sum(Fy_i) - Rb_y
Ra_z = -sum(Fz_i) - Rb_z
Rlocator_x = -sum(Fx_i)
```

The other support has zero axial reaction. Axial load sharing, preload and
bearing stiffness are not inferred. All applied shaft torques must balance:
free-running bearings do not supply an invented resisting torque. The output
retains force and moment equilibrium residuals in all three axes.

For outer diameter `D` and concentric inner diameter `d`:

```text
A = pi (D²-d²) / 4
I = pi (D⁴-d⁴) / 64
J = 2 I
```

Nodes occur at supports, point loads/couples and every section boundary. Between
nodes, the bending moment is linear. Curvature for Y displacement is
`(sum(Fy_i (x-xi)) - sum(Mz_i)) / (E I)` for loads/reactions to the left. Curvature
for Z displacement is `(sum(Fz_i (x-xi)) + sum(My_i)) / (E I)`. Exact polynomial
integration gives quadratic slope and cubic displacement within each interval.
Displacement/slope are continuous at section joins; integration constants enforce
zero transverse displacement at both supports, including overhung arrangements.

Internal axial force and torque are the negatives of the left-side sums.
Axial strain is `N/(EA)` and twist gradient is `T/(GJ)`. Axial movement is zero
at the chosen locator. Twist is reported relative to X=0; that reference does not
imply a bearing restrains torque. Diagram shear values are the left-side force
sums under this convention.

Deflection magnitude extrema include roots of `uy uy' + uz uz' = 0` within each
interval and both ends. Slope magnitude uses `uy' uy'' + uz' uz'' = 0`. Roots are
calculated on normalized intervals. Both sides of load/section discontinuities
are included in section stress and bending checks. Load-station motion is
continuous; section stress reported at a boundary uses its left side except at
X=0. The separate critical-point list retains both sides.

The largest nominal normal stress around a circular section is
`abs(N)/A + abs(Mresultant) D/(2I)`. Nominal torsional shear is `abs(T) D/(2J)`.
Their surface von Mises combination is `sqrt(sigma² + 3 tau²)`. This is an
elastic stress result, **not** a comparison against a material allowable.

## Independent numerical verification

The reference is [PyNiteFEA 3.2.0](https://github.com/JWock82/Pynite), under its
MIT license. A separate 3D finite-element model is assembled through its public
API, with independently defined section properties, nodal forces/couples and
support restraints. Its nodal reactions and movements are compared with the
analytical GearForge solver. The reference source is not copied or bundled.

Nine GearForge-authored synthetic cases cover centered/asymmetric loads,
two-plane loading, end couples, overhangs, two/three-section shafts, hollow
sections, axial movement and torque. There are **1,452 scalar comparisons**,
with relative and absolute tolerances of `1e-8`. The initial maximum absolute
discrepancy was below `2.431e-9` (mixed recorded units). Unit tests also check hand
solutions, load reversal/scaling, geometric scaling, an interior deflection
maximum, force/moment balance, invalid inputs, save failure and export integrity.

Use a separate environment: PyNite requires NumPy 2.4 or newer; the app's release
runtime remains pinned independently. From the repository:

```text
python -m venv reference-env
reference-env/Scripts/python -m pip install -r scripts/requirements-shaft-reference.txt
reference-env/Scripts/python -m pip check
reference-env/Scripts/python scripts/verify_shaft_reference.py
```

On Linux/macOS use `reference-env/bin/python` instead. CI runs this isolated
comparison and retains its JSON results. The offline fixture is
`tests/data/open_shaft_reference.json`; it contains original test inputs and
numerical outputs, not reference source or copied documentation. The check covers
the stated elastic beam quantities only, not every supported input combination.

## Scope and remaining component work

- Linear elastic Euler–Bernoulli bending, Saint-Venant torsion and axial extension;
  two ideal rigid radial supports, with one axial locating support.
- Circular solid or concentric hollow sections; discrete point loads and couples.
  No distributed load, bearing/housing flexibility, preload, gyroscopic response,
  critical-speed prediction or rotor dynamics.
- No transverse shear deformation/stress, shoulder/keyway notch concentration,
  residual stress, plasticity, fretting or fatigue. The span/diameter flag below
  10 and small-deflection flags (slope above 0.05 rad or displacement above 1% of
  support span) identify model concerns, not universal acceptance criteria.
- Compression is flagged; column buckling and beam-column effects are unassessed.
- Imported mesh forces are ideal. Assumed gear efficiency does not supply a
  verified friction-force or loss-torque distribution through the assembly.
- Bearing reactions still require actual supplier capacity, arrangement,
  lubrication, speed, clearance and permissible-misalignment assessment.
- Shaft yield/fatigue decisions need traceable material properties, stress
  concentrations, load history, acceptance criteria and independent review.
- Inputs are bounded to 200 cases, 100 loads per case, 50 contiguous sections,
  2 MB saved files and a conservative 2,000-interval calculation bound. Large duty
  datasets must be split into explicit studies instead of silently truncated.

Production service-load approval remains unavailable. These calculations make
the assembly load path reviewable and reproducible; material/supplier evidence,
remaining failure modes and physical qualification are still required.
