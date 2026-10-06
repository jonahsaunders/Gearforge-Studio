# GearForge Studio 1.0.0rc9

This release candidate adds thermal networks and chronological heating/cooling
studies to the open gear, shaft, bearing, fatigue and contact workflows.

- Define thermal bodies, capacities and temperature limits, connect heat paths,
  and enter phase-specific heat sources, conductances, ambient and durations.
- Calculate continuous temperature extrema and energy balance from exact modal
  phase solutions. Plot samples cannot change the calculated maximum.
- Inspect entered and settled repeated cycles, and conservative warm-up bounds
  for every repetition. A bound crossing is unresolved, not a proved exceedance.
- Edit topology and ordered phases, view temperature histories, save strict
  studies and export complete JSON/HTML evidence with integrity manifests.
- Compare 3,539 values against independent SciPy Radau/shooting calculations.
  Source and original examples remain GitHub-publishable; no restricted data,
  property tables or new runtime dependency are required.

See [thermal methods](THERMAL_ANALYSIS.md), [tooth contact](CONTACT_ANALYSIS.md),
[shaft fatigue](SHAFT_FATIGUE.md), [bearings](BEARING_ANALYSIS.md),
[shaft loads](SHAFT_ANALYSIS.md) and [open geometry](OPEN_ENGINEERING.md).
Root `VALIDATION.json` identifies current software evidence. Native archives
remain unsigned and require acceptance on actual company workstation images.

**Final production gearbox design and service-load ratings remain unqualified.**
Actual material evidence, tooth-root/transient fatigue, load distribution, measured
loss/cooling data, lubrication, manufacturing and physical durability qualification
remain. Production-required exports continue to reject unqualified designs.
