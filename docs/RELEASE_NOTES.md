# GearForge Studio 1.0.0rc8

This release candidate adds tooth-contact and surface-fatigue studies to the open
gear, shaft, bearing and shaft-fatigue workflows. Inspect external spur contact
pressure, half-width and ideal sliding across the path of contact, with explicit
load-sharing assumptions and separate material evidence for each gear.

- Calculate continuous peak pressure from exact interval limits, including
  load-sharing jumps. Display samples do not determine the maximum.
- Enter applicable pressure-life curves, temperatures, effective width and load
  factors. Interpolate only inside the curve; missing evidence stays unassessed.
- Count each tooth's gear revolutions and accumulate opposite torque flanks
  separately. Stationary peaks still receive elastic-pressure checks.
- Edit six desktop tabs and four diagrams, transfer a gear study, save strict
  inputs and export complete JSON/HTML assessments and integrity manifests.
- Compare 208 values against a pinned, separate MIT SlipPY reference. The app,
  adapter and original numerical fixtures can be published on GitHub; no paid
  standard, restricted material table or new runtime dependency is required.

See [tooth contact](CONTACT_ANALYSIS.md), [shaft fatigue](SHAFT_FATIGUE.md),
[bearings](BEARING_ANALYSIS.md), [shaft loads](SHAFT_ANALYSIS.md) and
[open geometry](OPEN_ENGINEERING.md). Root `VALIDATION.json` identifies the
version-specific software evidence. Native archives remain unsigned.

**Final production gearbox design and service-load ratings remain unqualified.**
Actual material data, tooth stiffness/load distribution, tooth-root and transient
fatigue, thermal/lubrication, manufacturing and physical durability qualification
remain. Production-required exports continue to reject unqualified designs.
