# GearForge Studio 1.0.0rc12

This release candidate adds an original local signed stress-history study for
changing loads. All implementation and synthetic fixtures can be published with
this repository; no paid standards, restricted material tables or private solver
are required.

- Count exact finite cycles across ordered/repeated blocks without expanding
  billions of samples or losing block-transition cycles and endpoint halves.
- Assess explicit uniaxial elastic material curves with bounded interpolation,
  a selected mean-stress model and linear damage; retain missing/out-of-range
  conditions and lower bounds without inventing endurance or remaining life.
- Check duration/start coverage and retain source/revision/sharing declarations,
  imported CSV fingerprints, strict editable files and complete JSON/CSV exports.
- Use seven desktop tabs, three plots and cancellable calculation/export workers.
- Reproduce 25,788 checks with separately installed MIT rainflow and independent
  high-precision fatigue arithmetic. The reference is not an app dependency.

See [stress history methods and limits](STRESS_HISTORY.md). `VALIDATION.json`
identifies current build evidence; previous releases do not qualify a new build.
Native archives are unsigned and require company workstation acceptance.

Production gearbox design and service-load ratings remain unqualified. The
synthetic history is not a gear solution. Actual full-engagement stress histories,
material/process evidence, multiaxial effects, manufacturing and physical load/life
qualification remain. Existing root pressure-patch peaks are not treated as a
complete cyclic history.
