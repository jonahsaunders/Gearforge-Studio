# GearForge Studio 1.0.0rc6

This release candidate connects the explicit shaft load path to bearing duty and
capacity assessment. Enter exact bearing ratings, applicable limits and case
factors, then review per-bearing basic fatigue exposure and operating checks.

- Carry every shaft duty case into a saved bearing study and recalculate the
  source load path for each assessment. Input edits invalidate old results.
- Sum rolling-contact fatigue exposure using absolute speed; preserve stationary
  and short-duration peak loads in static checks. Keep missing ratings/factors
  unassessed and unsupported oscillation/axial arrangements explicit.
- Check declared speed, minimum load, axial load, temperature, nominal bore and
  misalignment limits. Bearing operating temperature is not ambient temperature.
- Use five desktop tabs or batch commands; export complete inputs, source
  declarations, numerical results, HTML and an integrity manifest.
- Compare 218 values against separate 60-digit Decimal arithmetic for seven
  original synthetic cases. This verifies arithmetic, not physical bearing life.
- Include bearing tabs, save/reload, numerical results and verified exports in
  each native package's desktop checks.

The prior open gear/shaft studies, 72 FreeCAD Gears geometry comparisons, 1,452
PyNiteFEA shaft comparisons, project hardening and deployment controls remain.
See [bearing methods](BEARING_ANALYSIS.md), [shaft analysis](SHAFT_ANALYSIS.md),
[open geometry](OPEN_ENGINEERING.md) and the [deployment guide](INTERNAL_DEPLOYMENT.md).

All added source, examples and fixtures are intended for public GitHub
distribution. No paid standard, private package or restricted supplier table is
required. Numerical bearing examples are explicitly synthetic.

**Production gearbox design and service-load ratings remain unqualified.**
Basic L10 is a per-bearing population fatigue estimate, not adjusted service
life, assembly reliability or a warranty. Actual supplier selection, material
fatigue/contact, thermal/lubrication, manufacturing and physical qualification
remain. Production-required exports still reject unqualified designs.

Python 3.12 is the build/test runtime. Native archives remain unsigned. Root
`VALIDATION.json` links current evidence; prior version records are historical.
