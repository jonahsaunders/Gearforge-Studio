# GearForge Studio 1.0.0rc4

This release candidate adds an open engineering study to the hardened offline
desktop application. It establishes the calculation foundation for the agreed
250 W, 1,500 rpm, 5:1 steel spur development target.

- Edit external spur/helical geometry, normal profile shifts and an operating-duty
  spectrum; calculate tooth dimensions, contact ratios, quasi-static mesh forces,
  power balance and revolution exposure.
- Open a new target study or transfer a selected design stage with its actual
  required load. Save/reopen studies and export complete inputs, JSON results,
  readable reports and an integrity manifest.
- Compare 72 geometry quantities against a pinned FreeCAD Gears checkout. Retain
  openly reproducible numerical fixtures and run comparisons in CI without
  bundling the GPL reference implementation into the Apache-2.0 application.
- Correct transverse pressure-angle usage in existing helical contact-ratio and
  shaft-force screens. Reject incomplete saved study inputs instead of silently
  supplying defaults, and invalidate calculation results after edits.
- Extend native package smoke checks to the four study tabs, save/reload,
  calculation export and integrity verification.

All added code, examples and bundled comparison results are intended for public
GitHub distribution. No paid standard, proprietary calculation package or private
data is required. See [open engineering](OPEN_ENGINEERING.md) for formulas,
provenance, reproducibility and verification limits.

**Final production gearbox design and service-load ratings remain unqualified.**
Geometry comparisons and force balances do not establish fatigue strength,
material allowables, assembly durability or thermal capacity. Production-required
exports continue to reject unqualified designs. See
[remaining engineering work](PRODUCTION_QUALIFICATION.md).

Python 3.12 is the build/test runtime; the supported package range is 3.12–3.13.
Native archives remain unsigned. Root `VALIDATION.json` links version-specific
evidence; rc3 evidence remains historical. The
[deployment guide](INTERNAL_DEPLOYMENT.md) covers workstation acceptance and rollback.
