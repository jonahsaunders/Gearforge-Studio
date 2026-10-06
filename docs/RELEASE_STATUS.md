# Release status — 1.0.0rc3

This is an implemented and tested desktop **release candidate**. It is not a finished
commercially validated gearbox design product. The remaining work below is concrete
and material; no installer, model or calculation should imply it is already complete.

## Company-use hardening

The rc3 changes add strict project input validation, reliable recovery/save behavior,
per-user data locking, verified backup/restore, traceable exports, production-rating
status and dependency security/release evidence. See [deployment](INTERNAL_DEPLOYMENT.md),
[current software evidence](INTERNAL_VALIDATION.json) and the
[production qualification work](PRODUCTION_QUALIFICATION.md). The requested final
production gearbox design and load-rating scope is still unqualified.

## Implemented

- Native Qt desktop app with design, catalog, calibration, report and simulation pages.
- Offline project save/load, motor curves, advanced constraints, autosave/recovery.
- Printed/catalog/hybrid spur and helical searches, three-planet printed planetary search.
- Bevel, worm and cycloidal concept ratio/packaging searches.
- Continuous torque/load propagation, preliminary structural/kinematic/bearing screens.
- Component CSV import/export with validation, SQLite catalog, source provenance.
- Ranking, shortlist Pareto flags, comparison and infeasible-result diagnostics.
- Time-based rigid-body CAD/schematic animation, seek/reverse/tooth step, reduced
  motion, keyboard orbit/zoom and software-rendered exploded CAD preview.
- Motor/load sweeps, power balance, overload tables, sampled exact tooth-pair
  intersections over one input revolution and JSON/CSV simulation exports.
- Native platform styling, system/light/dark/text preferences, label buddies and
  accessibility names, standard shortcuts, document state and Finder open handler.
- Prototype spur/helical/planetary solids, carriers, mounts, housings and calibration coupon.
- STEP, STL/3MF, PDF/HTML, BOM, SVG references, assembly notes and manifests.
- Atomic export, static interference blocking and stale-input protection.
- Batch CLI, wheel/source packages, versioned launchers, macOS .app metadata,
  windowed file-protocol workers, native build/CI and draft GitHub release tooling.

## Required before a full commercial product claim

1. Implement and verify specialized bevel spherical tooth geometry, worm-wheel
   generated contact geometry and cycloidal contact/pin/roller geometry. Their current
   functionality is concept-only and manufacturing solids are disabled.
2. Implement detailed verified fatigue/contact rating methods, polymer wear/creep,
   thermal/lubrication, housing/pin/carrier/retention strength and external shaft loads.
   Current Lewis and generic bearing calculations are preliminary screens.
3. Obtain measured print-profile allowables with orientation, batch, temperature,
   duty, aging and uncertainty; test complete gearboxes through intended load/life.
4. Verify full-cycle contact, backlash and cumulative tolerance stacks with physical
   builds and independent engineering reference cases. Static and sampled CAD
   checks are insufficient; samples do not establish continuous contact.
5. Complete supplier-specific bearing catalogs, supplier rating conditions and pricing
   integrations. The six seed gears and generic bearing table are intentionally limited.
6. Produce production drawings with fits, surface finish, pin/keyway/retention details
   and GD&T. SVG outputs are reference layouts and schedules only.
7. Review current platform results in `INTERNAL_VALIDATION.json` and CI. Complete
   interactive acceptance on the actual company workstation image. Sign Windows packages and
   notarize macOS packages using the product owner's credentials. Native Linux smoke
   tests are recorded in the validation artifact when that bundle was built.
8. Review dependency-license notices for the exact distributed binary, release ownership,
   support policy, update/signing process and distribution terms. Application source
   is Apache-2.0, so paid distribution is possible subject to dependency obligations.

## Unimplemented commercial services

No payment processor, accounts, subscription licensing, online auto-update service,
crash-upload service or supplier purchasing workflow is connected. This app is an
offline desktop engineering tool. Such services need owner credentials and deployment
configuration; inventing endpoints or silently charging/purchasing would be incorrect.

## Evidence

See `VALIDATION.json` in the release kit for the actual test commands/results, checked
runtime, exported sample files and checksums. Tests cover all family searches, numerical
constraints, project/catalog round-trips, worker/desktop workflows, real CAD solids,
interference, real STEP imports, PDF signatures and output manifests. They do not
establish mechanical fatigue life, wear, real printer accuracy or production readiness.
