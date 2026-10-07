# Screenshot gallery

[Back to the overview](../README.md) · [User guide](USER_GUIDE.md)

These are unmodified captures of **GearForge Studio 1.0.0rc12**, running on Windows with Qt’s offscreen platform, light appearance and Segoe UI. All views use the repository’s example files. Native controls and fonts vary by platform. Click an image to inspect it at full resolution.

The fixed material-point view shows the current development addition documented in the changelog. Its separate capture record is [captures-probes.json](../screenshots/captures-probes.json).

**Example scope:** Synthetic inputs demonstrate calculations; they are not measured material, manufacturing or component allowables. The app does not provide qualified production gearbox ratings.

- [Design workspace](#design-workspace)
- [Exploded assembly](#exploded-assembly)
- [Helical prototype](#helical-prototype)
- [Planetary prototype](#planetary-prototype)
- [Motor and load simulation](#motor-and-load-simulation)
- [Component catalog](#component-catalog)
- [Print calibration](#print-calibration)
- [Design report](#design-report)
- [Geometry and operating duty](#geometry-and-operating-duty)
- [Shaft loads and motion](#shaft-loads-and-motion)
- [Bearing duty and capacity](#bearing-duty-and-capacity)
- [Shaft material and fatigue](#shaft-material-and-fatigue)
- [Tooth contact and surface fatigue](#tooth-contact-and-surface-fatigue)
- [Thermal network](#thermal-network)
- [Rack-generated tooth profile](#rack-generated-tooth-profile)
- [Elastic tooth-root stress](#elastic-tooth-root-stress)
- [Fixed material-point stresses](#fixed-material-point-stresses)
- [Signed stress history](#signed-stress-history)
- [Rainflow cycle distribution](#rainflow-cycle-distribution)

## Design workspace

Generate and compare a ranked shortlist, inspect modeled checks, and load the selected CAD assembly.

[Open example](../examples/12-to-1-hybrid.gearforge) · [Read the guide](USER_GUIDE.md#design-your-first-gearbox)

![Generate and compare a ranked shortlist, inspect modeled checks, and load the selected CAD assembly.](../screenshots/desktop.png)

## Exploded assembly

Separate gears, shafts and hardware in the rigid-body CAD view.

[Open example](../examples/12-to-1-hybrid.gearforge) · [Read the guide](USER_GUIDE.md#rigid-body-playback)

![Separate gears, shafts and hardware in the rigid-body CAD view.](../screenshots/exploded.png)

## Helical prototype

Inspect sampled involute teeth with opposite helix hands.

[Open example](../examples/helical-example.gearforge) · [Read the guide](USER_GUIDE.md#design-your-first-gearbox)

![Inspect sampled involute teeth with opposite helix hands.](../screenshots/helical.png)

## Planetary prototype

Explore a fixed ring, sun input, three planets and carrier output.

[Open example](../examples/planetary-example.gearforge) · [Read the guide](SIMULATION.md)

![Explore a fixed ring, sun input, three planets and carrier output.](../screenshots/planetary.png)

## Motor and load simulation

Review output torque versus speed, requested load, assumed power loss and operating-point tables.

[Open example](../examples/12-to-1-hybrid.gearforge) · [Read the guide](SIMULATION.md)

![Review output torque versus speed, requested load, assumed power loss and operating-point tables.](../screenshots/simulation.png)

## Component catalog

Inspect supplier dimensions, recorded rating conditions and source links; import or export validated CSV records.

[Open example](../examples/12-to-1-hybrid.gearforge) · [Read the guide](USER_GUIDE.md#component-catalogs)

![Inspect supplier dimensions, recorded rating conditions and source links; import or export validated CSV records.](../screenshots/catalog.png)

## Print calibration

Set clearances and material assumptions, export a coupon, and apply measured dimensional compensation.

[Open example](../examples/12-to-1-hybrid.gearforge) · [Read the guide](USER_GUIDE.md#print-calibration)

![Set clearances and material assumptions, export a coupon, and apply measured dimensional compensation.](../screenshots/calibration.png)

## Design report

Read the selected candidate’s calculations, bill of materials, assumptions and prototype status.

[Open example](../examples/12-to-1-hybrid.gearforge) · [Read the guide](USER_GUIDE.md#exported-files)

![Read the selected candidate’s calculations, bill of materials, assumptions and prototype status.](../screenshots/report.png)

## Geometry and operating duty

Edit an external spur/helical pair, profile shifts, design targets, operating cases and source evidence.

[Open example](../examples/steel-spur-250w.gearforge-study) · [Read the guide](OPEN_ENGINEERING.md)

![Edit an external spur/helical pair, profile shifts, design targets, operating cases and source evidence.](../screenshots/engineering.png)

## Shaft loads and motion

Inspect the explicit shaft load path, support reactions, deflection, slope, bending, twist and nominal stress.

[Open example](../examples/steel-spur-input.gearforge-shaft) · [Read the guide](SHAFT_ANALYSIS.md)

![Inspect the explicit shaft load path, support reactions, deflection, slope, bending, twist and nominal stress.](../screenshots/shaft.png)

## Bearing duty and capacity

Review per-bearing basic L10 arithmetic and declared static, speed, temperature and misalignment limits. The ratings in this example are synthetic.

[Open example](../examples/steel-spur-synthetic.gearforge-bearing) · [Read the guide](BEARING_ANALYSIS.md)

![Review per-bearing basic L10 arithmetic and declared static, speed, temperature and misalignment limits. The ratings in this example are synthetic.](../screenshots/bearing.png)

## Shaft material and fatigue

Review the public NASA worked example for a selected shaft section under rotating bending and steady torque. Benchmark inputs are not application material allowables.

[Open example](../examples/nasa-shaft-fatigue.gearforge-fatigue) · [Read the guide](SHAFT_FATIGUE.md)

![Review the public NASA worked example for a selected shaft section under rotating bending and steady torque. Benchmark inputs are not application material allowables.](../screenshots/fatigue.png)

## Tooth contact and surface fatigue

Plot spur Hertz pressure and sliding along the contact path, with explicit load sharing and bounded pressure-life inputs. Material data are synthetic.

[Open example](../examples/synthetic-contact.gearforge-contact) · [Read the guide](CONTACT_ANALYSIS.md)

![Plot spur Hertz pressure and sliding along the contact path, with explicit load sharing and bounded pressure-life inputs. Material data are synthetic.](../screenshots/contact.png)

## Thermal network

Follow a selected body through an ordered heating/cooling phase; assess continuous extrema, energy balance and repeated duty. Losses and cooling data are synthetic.

[Open example](../examples/synthetic-thermal.gearforge-thermal) · [Read the guide](THERMAL_ANALYSIS.md)

![Follow a selected body through an ordered heating/cooling phase; assess continuous extrema, energy balance and repeated duty. Losses and cooling data are synthetic.](../screenshots/thermal.png)

## Rack-generated tooth profile

See the generated root join the involute. The example declares a synthetic cutter; the app also checks undercut, folds and the nominal active contact path.

[Open example](../examples/synthetic-tooth.gearforge-tooth) · [Read the guide](TOOTH_PROFILES.md)

![See the generated root join the involute. The example declares a synthetic cutter; the app also checks undercut, folds and the nominal active contact path.](../screenshots/tooth.png)

## Elastic tooth-root stress

Inspect a finite-element stress map at a sampled pressure-patch position. Three mesh levels and a wider sector support numerical comparisons; this is not a full rolling-load fatigue history.

[Open example](../examples/synthetic-root.gearforge-root) · [Read the guide](ROOT_STRESS.md)

![Inspect a finite-element stress map at a sampled pressure-patch position. Three mesh levels and a wider sector support numerical comparisons; this is not a full rolling-load fatigue history.](../screenshots/root.png)

## Fixed material-point stresses

Track signed normal and shear stress at the same physical point as the sampled
pressure patch moves. Adjacent element values stay separate. The synthetic
example illustrates coordinates and directions; the trace has no time axis or
complete loading cycle.

[Open example](../examples/synthetic-root-probes.gearforge-root) · [Read the guide](ROOT_STRESS.md#fixed-material-points-and-signed-stresses)

![Signed normal and shear stresses at a fixed synthetic root point, plotted against sampled load-path fraction.](../screenshots/root-probes.png)

## Signed stress history

Inspect one template block of signed local normal stress. Repeated blocks retain cross-boundary cycles; the included waveform and material curve are invented.

[Open example](../examples/synthetic-history.gearforge-history) · [Read the guide](STRESS_HISTORY.md)

![Inspect one template block of signed local normal stress. Repeated blocks retain cross-boundary cycles; the included waveform and material curve are invented.](../screenshots/history.png)

## Rainflow cycle distribution

Compare cycle ranges, means and counts from the same finite history. The complete cycle table is available in CSV; bounded damage does not establish gearbox service life.

[Open example](../examples/synthetic-history.gearforge-history) · [Read the guide](STRESS_HISTORY.md)

![Compare cycle ranges, means and counts from the same finite history. The complete cycle table is available in CSV; bounded damage does not establish gearbox service life.](../screenshots/history-cycles.png)

## Reproduce the gallery

Run `python scripts/capture_screenshots.py` from an installed checkout. See the [capture instructions](DEVELOPMENT.md#updating-screenshots) and [capture metadata](../screenshots/captures-all.json).
