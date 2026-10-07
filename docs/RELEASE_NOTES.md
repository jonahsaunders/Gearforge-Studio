# GearForge Studio 1.0.0rc11

This release candidate adds explicit two-dimensional elastic stress analysis of
the generated spur tooth root, with cancellable calculations and reproducible
open-source verification.

- Retain actual cutter/profile inputs; declare material, temperature, effective
  width, support radius, pressure-patch width and per-duty factors.
- Calculate Q9 elastic fields on three meshes and a wider sector. Keep numerical
  sensitivity checks separate from material evidence and production approval.
- Inspect seven desktop tabs, mesh/stress maps, sampled root curves and optional
  displacement exaggeration. Save strict inputs and export JSON/HTML/CSV/VTK plus
  an integrity manifest through cancellable workers.
- Compare 4,582 displacement, reaction, stress and energy values against a
  separate BSD-3-Clause scikit-fem implementation, supplemented by analytic tests.
  No paid standard, restricted property dataset or reference runtime is bundled.

See [root stress methods and limits](ROOT_STRESS.md). `VALIDATION.json` identifies
current build evidence; older records do not qualify a new build. Native archives
are unsigned and require acceptance on company workstation images.

Production gearbox design and service-load ratings remain unqualified. Actual
material/cutter evidence, 3D load distribution, tooth-root/transient fatigue,
lubrication, manufacturing tolerances and physical qualification remain.
