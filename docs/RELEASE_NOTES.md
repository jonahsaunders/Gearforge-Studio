# GearForge Studio 1.0.0rc7

This release candidate adds shaft fatigue and material evidence to the open
gear, shaft and bearing studies. Choose exact critical-section cuts, declare
material/operating data and application factors, and calculate bounded
rotating-bending/steady-torque fatigue blocks using a public NASA method.

- Edit material provenance, finite-life curve range, critical sections and
  duty conditions in five desktop tabs or batch commands.
- Recalculate retained shaft loads at exact left/right section cuts, including
  load and diameter discontinuities. Plot sampling cannot alter stress.
- Keep axial/hollow/transient fatigue, out-of-range curves and missing data
  explicit. No endurance plateau, infinite-life claim or strength from a name.
- Preserve stationary peaks in static checks. Rotation cycles do not count
  startup, reversal or load-transition fatigue.
- Save strict editable studies and export complete evidence, JSON, HTML and
  integrity manifests. Input edits invalidate prior results.
- Check 100 values against independent 60-digit Decimal arithmetic and the
  public NASA RP-1123 worked example. Historical numbers are not material
  allowables; no restricted source tables or paid standards are bundled.

See [shaft fatigue](SHAFT_FATIGUE.md), [bearing analysis](BEARING_ANALYSIS.md),
[shaft load paths](SHAFT_ANALYSIS.md) and [open geometry](OPEN_ENGINEERING.md).
Root `VALIDATION.json` identifies current software evidence; earlier records
are historical. Native archives remain unsigned.

**Final production gearbox design and service-load ratings remain unqualified.**
Actual material data, transient fatigue, tooth fatigue/contact, thermal and
lubrication, manufacturing and physical durability qualification remain.
Production-required exports continue to reject unqualified designs.
