# Architecture

## Modules

- `models.py`: finite input validation, units, schema versioning, atomic project writes.
- `catalog.py`: SQLite records, atomic CSV import, provenance and profile storage.
- `engine.py`: gearbox templates, bounded tooth-count enumeration, component matching,
  load propagation, checks, scoring and Pareto flags for the displayed shortlist.
- `geometry.py`: sampled involute profiles, helical extrusion, internal rings, shafts,
  bearing references, cross-pin hubs, carrier, ring posts and split housings.
- `simulation.py`: elapsed-time rigid kinematics, motor/load/power sweep and optional
  sampled exact B-rep tooth intersections; no transient/elastic/thermal solver.
- `appearance.py`: system styling, palette/text preferences and reduced motion.
- `exporting.py`: exact static interference checks, STEP/print meshes, reports, reference
  drawings, assembly instructions and checksums published as one atomic directory.
- `calibration.py`: uncompensated coupon and separate dimensional fit estimation.
- `viewer.py`: native software mesh projection and kinematic schematic view.
- `app.py`: Qt desktop pages and one-shot QProcess background jobs.
- `cli.py`: headless batch commands and a JSON worker protocol.

No network request is made during synthesis, preview, project loading or export.
Supplier URLs open only in response to a user double-click in the catalog.

## Units and loads

All geometry is millimetres. Forces are newtons; torques are N m; stress is MPa.
Spur stage reduction is `z_driven / z_driver`. Total reduction and efficiency are the
products of stage values. Fixed-ring planetary reduction is `1 + z_ring / z_sun`.
Conventional equally spaced planets require `(z_sun + z_ring) % planet_count == 0`.
Ring teeth equal sun teeth plus twice planet teeth; neighbor planet clearance is checked.

Required stage input loads are derived backward from desired output torque and
assumed downstream losses, then propagated forward into the reports. Available motor
output torque is checked separately. A motor curve is linearly interpolated only
inside its supplied speed domain. Peak motor capability is not modeled.

The external tooth screen uses the 20-degree Lewis factor `0.484 - 2.87/z_virtual`,
where helical virtual teeth use `z / cos(beta)^3`. This approximation is insufficient
for final fatigue/contact ratings and is not presented as ISO 6336/AGMA certification.
The model applies tangential peak loading, a speed-based assumed dynamic multiplier,
and the user's safety factor. Contact ratio adds transverse and helical overlap terms.

Shaft stress combines elastic bending with torsion assuming simply supported central
gear loads. Deflection uses steel E = 200 GPa. The bearing table gives generic dimension
codes and assumed C/C0/speed values, not manufacturer-specific certification. Basic
ball-bearing L10 is preliminary and uses an approximate combined-load factor.

## Design/search boundaries

Module choices are 0.8, 1, 1.25, 1.5, 2, 2.5 and 3 mm. Printed spur/helical tooth choices
are enumerated from a fixed finite set from 18–100; per-stage ratios are at most 6:1.
Face widths are 8, 12, 18 and 24 mm, with separate planetary templates. Two-stage
search groups ratios and caps the number of source variants per ratio bucket.
User-visible scores are preference-weighted heuristics. Pareto flags refer to the
first 80 ranked candidates, not to an exhaustive mathematical global frontier.

Commercial synthesis supports parallel spur/helical catalog pairs. Catalog records
for other families can be retained but are not used without the specialized complete
contact/model data. Missing data produces an explanation rather than fabricated parts.
Catalog gears sharing a shaft must have the same bore. A requested shaft diameter is
a minimum; printed bores adapt to a selected standard bearing diameter.

## CAD fidelity

External and internal flanks are sampled from an involute. Root relief is radial and
is not a hob-generated trochoid. Helical gears use opposite-hand constant-twist
extrusion. Bearings are ring-shaped reference solids. Catalog gear bodies reproduce
nominal module/teeth/face/hub/bore dimensions, not supplier keyway or tolerance details.

Mesh files are emitted from print-local solids; STEP retains assembled nominal
geometry. Shrink correction is print-only, while bore/seat clearances are part of the
prototype nominal geometry. Exact solid intersection checks run on assembled geometry.
Fits involving bearings/shafts are labeled for review; unexpected other intersections
block solid export. A static pass does not prove a full revolution is collision-free.

## Data and failure handling

Project JSON has a schema version and size limit, validates finite values and rejects
unknown top-level fields. It never imports or executes user scripts. Imports validate
every catalog row before a single transactional update. SQLite uses parameterized SQL.
Reports HTML-escape user values; BOM CSV neutralizes executable spreadsheet strings.
Native worker inputs are generated by the application; one child task runs at a time.
Cancellation kills that child without hanging the UI. Export staging occurs adjacent
to the destination so publishing is an atomic rename. Existing export directories are
never overwritten. Output manifests record SHA-256 for each file.

## Extension points

Add a family generator that yields stages, a specialized load model with explicit
validity limits, a validated CAD builder, regression reference data, and physical
verification fixtures. Promote export status only after those checks pass. Supplier
adapters should generate the existing normalized CSV schema with provenance, declared
units, rated-load conditions, retrieval date and non-fabricated price/stock fields.
