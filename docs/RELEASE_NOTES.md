# GearForge Studio 1.0.0rc3

This release candidate hardens the offline desktop app for controlled company
use and makes the missing production engineering qualification explicit.

- Upgrade the Qt desktop runtime to 6.11.2 for upstream security fixes.
- Upgrade CAD dependencies to CadQuery 2.8 / OCP 7.9.3 / VTK 9.6.2, removing the
  VTK advisories reported against the previous pinned environment.
- Validate project structure, duplicate JSON keys, finite values and file sizes;
  preserve documents after cancelled recovery or failed Save As.
- Lock each local data directory and provide verified catalog/profile/settings
  backup and restore into a new directory.
- Invalidate results on catalog changes, preserve Unicode and CSV formatting,
  and include original project metadata, catalog and runtime provenance in exports.
- Emit production qualification assessments and reject production-required
  exports when no verified service-load rating exists (all current families).
- Collect all runtime dependency notices, audit packages, emit a CycloneDX SBOM,
  pin workflow actions, and retain platform test/build evidence.

Python 3.12 is the validated runtime; 3.12–3.13 is the package range. Native
archives remain unsigned. See INTERNAL_VALIDATION.json for recorded software
checks and INTERNAL_DEPLOYMENT.md for workstation acceptance, backup and rollback.

**Not qualified for final production gearbox design or load ratings.** Existing
Lewis, shaft and generic bearing calculations remain preliminary screens;
bevel, worm and cycloidal geometry remains concept-only. Follow
PRODUCTION_QUALIFICATION.md to define the first production scope, verified
rating methods, material/supplier inputs, physical evidence and engineering release.
