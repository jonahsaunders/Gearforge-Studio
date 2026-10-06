# Unreleased

# 1.0.0rc4 — 2026-10-06

- Add a desktop engineering-study editor and batch commands for the agreed
  250 W, 1,500 rpm, 5:1 steel-spur development target.
- Calculate normal-system spur/helical geometry with profile shifts, operating
  center distance, contact ratios, tooth dimensions and geometric findings.
- Calculate signed quasi-static mesh loads, power balance and duty exposure;
  preserve editable inputs, method revision and a hash in calculation exports.
- Import a selected spur/helical stage using its required operating load.
- Correct helical contact-ratio and shaft-load screens to use the transverse
  pressure angle, consistent with the existing CAD implementation.
- Compare 72 dimensions/angles against a pinned, openly licensed FreeCAD Gears
  revision. The external reference is not a runtime dependency or bundled code.
- Require GitHub-publishable code, tests and bundled data. Proprietary standards
  are not a development dependency; production load/life ratings remain absent.

# 1.0.0rc3 — 2026-10-06

- Upgrade PySide6/Qt to 6.11.2 for upstream security fixes.
- Upgrade CadQuery/OCP/VTK to remove reported VTK advisories; pin the complete
  runtime dependency set and require Python 3.12–3.13.
- Reject malformed, duplicate-field, oversized and non-finite project inputs;
  validate saves and preserve the current document after failed Save As or
  cancelled recovery. Preserve CSV newlines and worker Unicode on Windows.
- Lock each application data directory; add verified offline backup/restore.
- Invalidate catalog search results on import and preserve project metadata,
  catalog snapshots, runtime provenance and hashes in design exports.
- Make unavailable production ratings explicit in machine-readable assessments
  and provide a production-required export guard. Final production engineering
  qualification remains outstanding; no load-rating method is newly claimed.
- Inventory all runtime dependency licenses and generate vulnerability/SBOM
  evidence; pin build actions and add deployment and qualification handoffs.

# Earlier unreleased improvements

- Install Qt's Linux runtime libraries in regression and release workflows,
  including the EGL library required by headless desktop tests.
- Exercise animation with Reduce Motion both enabled and disabled, independent
  of the CI host's accessibility preferences.
- Add six actual app captures to the README: exploded hybrid, planetary and
  helical CAD, component catalog, print calibration and design report. Refresh
  the design/simulation images and include a reproducible capture script.

# 1.0.0rc2 — 2026-10-06

Native appearance, accessible controls, keyboard/document behavior, deterministic
CAD playback and a simulation workspace with motor/load sweeps and sampled exact
tooth intersections. Windowed worker compatibility, macOS app metadata, version
checks, cross-platform CI and draft prerelease automation. See docs/RELEASE_NOTES.md
for details and platform validation limits.

# 1.0.0rc1

Initial working desktop release candidate. Adds bounded gearbox synthesis, component
catalogs, motor curves, engineering screens, native preview/comparison, calibration,
projects/autosave, CAD/report exports, CLI, tests and packaging. The CAD release scope
is prototype spur/helical/planetary; other families are concept-only. Commercial load
validation, specialized contact models and signed target-OS distributions remain open.
