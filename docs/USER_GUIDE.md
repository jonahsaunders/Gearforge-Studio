# User guide

[Back to the overview](../README.md) · [Screenshot gallery](GALLERY.md)

Install the app using the [quick start](../README.md#install-and-launch). This guide covers the prototype design workflow, controls, data and exports. The nine engineering workspaces have dedicated [method guides and examples](../README.md#engineering-workspaces).

- [Design your first gearbox](#design-your-first-gearbox)
- [Simulation workspace](#simulation-workspace)
- [Component catalogs](#component-catalogs)
- [Print calibration](#print-calibration)
- [Exported files](#exported-files)
- [Command-line interface](#command-line-interface)
- [Projects, local data and privacy](#projects-local-data-and-privacy)
- [Engineering methods and limitations](#engineering-methods-and-limitations)
- [Troubleshooting](#troubleshooting)

## Design your first gearbox

1. Launch the app and open [the 12:1 hybrid example](../examples/12-to-1-hybrid.gearforge)
   through **File → Open project**.
2. Review input speed, available motor torque, desired output speed and required
   output torque. Values use rpm, N·m and millimetres.
3. Select the manufacturing mode, families, maximum stage count and envelope.
   Use **Advanced constraints** for peak/safety factors, bearing life, ratio
   tolerance, motor curve, module limits, shaft sizes and supplier filtering.
4. Choose a ranking priority and select **Generate designs**.
5. Select a candidate. Review its engineering checks, stage data, bill of
   materials and assumptions. `PASS` means a modeled screen passed under those
   assumptions; `WARN` identifies an unverified condition.
6. Select **Load 3D CAD** for a prototype family. Inspect tooth geometry, shafts,
   carrier where applicable, housing and exploded arrangement.
7. Open **Simulation workspace** for the operating sweep and optional sampled
   tooth check. See the methods and limits below.
8. Compare multiple rows using Ctrl/Cmd or Shift selection, calibrate dimensional
   print compensation if needed, then export to a new directory.

The default example targets **1200 rpm input, 100 rpm output, 0.08 N·m motor
torque and 0.65 N·m required output**. Your resulting shortlist depends on the
project constraints and current catalog. Loading a saved project requires a new
search against the current catalog before CAD/export.

Examples also cover [helical](../examples/helical-example.gearforge),
[planetary](../examples/planetary-example.gearforge),
[commercial gears](../examples/commercial-example.gearforge),
[bevel](../examples/bevel-example.gearforge), [worm](../examples/worm-example.gearforge)
and [cycloidal concepts](../examples/cycloidal-example.gearforge).

## Simulation workspace

![Motor/load envelope and operating-point table](../screenshots/simulation.png)

### Rigid-body playback

Playback integrates measured elapsed time and input RPM rather than advancing a
fixed angle per rendered frame. External gear pairs counterrotate; compound
shafts use accumulated stage ratios. The planetary configuration uses the Willis
relation for a fixed ring, sun input and carrier output, with planet spin and orbit.

| Control | Behavior |
| --- | --- |
| Play / pause | Start explicitly; retain the current pose when paused |
| Time scale | `.001×`, `.01×`, `.1×` or `1×` simulated seconds per wall-clock second |
| Reverse | Reverse the input direction |
| Time field | Seek using the current speed from time zero |
| Step tooth | Advance one input-tooth pitch while paused |
| Arrow keys / drag | Orbit the CAD view |
| `+` / `−` / scroll | Zoom the CAD view |
| `R` / Space | Reset view / toggle playback when the viewer has focus |
| Reduce motion | Disable continuous play while retaining seek and stepping |

Playback scale changes display time, not the operating RPM used in the design.
Bearings are stationary reference rings; rolling elements are not simulated.

### Motor/load and power sweep

With a supplied motor curve, torque is interpolated only within its recorded
speed range. The curve format is `[[rpm, torque_Nm], ...]`, with distinct speed
samples. Without a curve, the sweep assumes constant motor torque from 0.25 to
2 times design input speed, bounded by the supported speed limits.

For ratio `R`, assumed total efficiency `eta` and motor torque `T`:

- Available output torque: `T_out = T × R × eta`.
- Input power: `P_in = T × rpm × 2π / 60`.
- Output power: `P_out = eta × P_in`; modeled loss: `P_in − P_out`.
- Load margin: available output torque minus the requested output load.

Displayed powers describe full modeled motor capability at the prescribed speed.
They are not a partial-load power-consumption prediction. An overload flag marks
an unsustainable prescribed operating point under this model; it does not solve
stall or deceleration. Off-design sweep points do not rerun every stress,
bearing or temperature screen.

### Sampled tooth intersections

The optional cancellable background check builds real B-rep tooth solids and
checks mating gear pairs at **12 discrete poses over one input revolution**.
Its JSON evidence includes phases, pair overlap volumes and a 0.05 mm³ reporting
threshold. A passing sample check does not cover continuous contact, unsampled
interference or a complete assembly repeat cycle.

These are rigid kinematic and quasi-static models. They do not solve inertia,
impact, elastic contact pressure, lubrication, wear, fatigue, temperature or
planetary load sharing. See [simulation methods](SIMULATION.md) and the
[recorded example evidence](mesh-sampling-evidence.json).

## Component catalogs

The seed catalog includes **six KHK gear records** with dimensional/rating facts,
source URLs and retrieval dates. Price and stock are not fabricated. The generic
bearing table provides screening references rather than supplier-verified ratings.

In **Component catalog**, export a CSV/template, edit compatible records and
import it. The exact ordered columns are:

```text
sku,supplier,family,module_mm,teeth,pressure_deg,helix_deg,width_mm,bore_mm,hub_diameter_mm,hub_width_mm,material,bending_nm,contact_nm,price,currency,source_url,rating_conditions,retrieved_date
```

Preserve column order, use HTTPS source URLs, unique SKUs and finite values in
supported ranges. Leave unknown prices blank. Imports validate all rows before
updating SQLite; an invalid row rejects the transaction. Catalog changes require
regenerating previous designs. Double-click a record to open its supplier source.

Supplier bending/contact ratings are conditional on mating gears, speed,
lubrication, life and other stated conditions. A comparison with those values is
not a certified rating for your application.

## Print calibration

In **Print calibration**, save a material profile, export the dimensional coupon,
measure its outside size and bore, and apply the measured compensation. Reprint
the coupon to verify the correction. Profiles include backlash, bore and bearing
clearance, shrink compensation, print orientation and recorded test evidence.

A dimensional coupon establishes dimensional compensation only. It does not
measure allowable strength, fatigue, creep or wear. Initial material allowables
are illustrative inputs and need independent characterization for the intended
printer, orientation, temperature, batch and duty.

## Exported files

Exports publish a new directory atomically and refuse to overwrite an existing
one. Use report-only export when reviewing a concept or a geometry issue.

| File or folder | Purpose |
| --- | --- |
| `assembly.step` / `step/` | Nominal assembly and individual-part CAD for prototype families |
| `print/` | Print-local STL/3MF for printed parts, with optional shrink compensation |
| `bom.csv` | Quantities, component sources and known/unknown quotations |
| `report.html` / `report.pdf` | Calculations, assumptions, checks and limitations |
| `layout.svg` / `shafts.svg` | Reference layout and shaft schedule |
| `cad-interference.json` | Static solid-intersection results when CAD is exported |
| `simulation-sweep.json` / `.csv` | Quasi-static operating sweep and power/load data |
| `design.gearforge` | Requirements, profile and selected design snapshot |
| `catalog.csv` / `provenance.json` | Catalog snapshot, project metadata, calculation inputs and runtime versions |
| `qualification.json` | Explicit unqualified status, unavailable service rating and engineering blockers |
| `ASSEMBLY.txt` | Prototype assembly and inspection notes |
| `manifest.json` | File SHA-256 hashes, UTC timestamp, app version, candidate identity and production-rating status |

The Simulation workspace can also export sweep data with a completed sampled
mesh check. Unexpected static interference blocks CAD export. SVG references
are not production drawings with certified fits, surface finishes or GD&T.

## Command-line interface

All nine engineering workspaces also have batch commands. Each `calculate`
command writes a new assessment directory with retained inputs, results and a
file-integrity manifest. See the individual method guide before interpreting a
result.

| Command group | Guide |
| --- | --- |
| `gearforge study` | [Geometry and duty](OPEN_ENGINEERING.md) |
| `gearforge shaft` | [Shaft loads and motion](SHAFT_ANALYSIS.md) |
| `gearforge bearing` | [Bearing duty and capacity](BEARING_ANALYSIS.md) |
| `gearforge fatigue` | [Shaft material and fatigue](SHAFT_FATIGUE.md) |
| `gearforge contact` | [Tooth contact and surface fatigue](CONTACT_ANALYSIS.md) |
| `gearforge thermal` | [Thermal networks](THERMAL_ANALYSIS.md) |
| `gearforge tooth` | [Rack-generated tooth profiles](TOOTH_PROFILES.md) |
| `gearforge root` | [Elastic tooth-root stress](ROOT_STRESS.md) |
| `gearforge history` | [Signed stress histories](STRESS_HISTORY.md) |

For example, from the repository root:

```bash
gearforge history calculate examples/synthetic-history.gearforge-history --out history-review
gearforge verify history-review
```

This example uses invented history/material data. Its calculated damage is a
numerical demonstration, not a gearbox life rating. Use `gearforge <group> --help`
for creation, transfer and calculation options; `history import-csv` imports a
signed time/stress history. [Backup and restore](INTERNAL_DEPLOYMENT.md#data-recovery-and-backup)
cover the local catalog, profiles, settings and recovery file.

Use the installed `gearforge` executable, or `python -m gearforge` with the
appropriate environment interpreter:

```bash
gearforge --version
gearforge doctor
gearforge new example.gearforge
gearforge search example.gearforge --out candidates.json --limit 60
gearforge export example.gearforge --out design-export
gearforge export example.gearforge --out report-export --report-only
gearforge smoke --out desktop-diagnostics --cad
gearforge verify design-export
gearforge qualify example.gearforge --out qualification.json
gearforge export example.gearforge --out production-export --require-production-rating
```

`search` and `export` accept `--catalog custom.csv`. Export recalculates the
shortlist. Use `--candidate ID` to select an ID from a search using the same
project/catalog and a sufficient `--limit`; the default exports the highest-ranked
candidate. Existing project/search-output/export paths are preserved.

The smoke command writes screenshots and diagnostic JSON into a new folder.
To run it on a headless host, use `QT_QPA_PLATFORM=offscreen`. Normal desktop
launches require a display and should not use that variable.

## Projects, local data and privacy

Projects are versioned, size-limited `.gearforge` JSON documents, not executable
scripts. Catalogs and saved print profiles are stored in local SQLite. Settings,
rotating logs and autosave recovery are kept in the platform's Qt app-data location.
Set `GEARFORGE_DATA_DIR` to a writable directory to choose a different location.

Modified projects are autosaved every 30 seconds. Restore through
**File → Restore autosave**. Project/profile changes require regeneration before
CAD/export; stale background preview/check results are not applied to new inputs.

The app has no telemetry, automatic purchasing, license-server connection or
supplier scraping. Supplier pages open only through a user's catalog action.
Dependency installation and GitHub Actions builds require network access.

## Engineering methods and limitations

The engine screens reduction and envelope constraints, available continuous
output torque, accumulated backlash, pitch velocity, external contact ratio,
printable dimensions, Lewis tooth bending, combined shaft bending/torsion and
deflection, and generic bearing static/speed/L10 estimates. Requested safety and
peak factors enter structural screens; continuous torque does not establish
motor peak-load capability.

The prototype search/CAD pipeline uses sampled radial root relief. The separate
[tooth-profile study](TOOTH_PROFILES.md) generates a rack-cut spur root, and the
[root-stress study](ROOT_STRESS.md) assesses that generated profile. These do not
replace the prototype CAD tooth solids. Stage efficiencies, dynamic factors and material/bearing allowables are screening
assumptions. Housing, carrier, pins, retention, external shaft loads, manufactured
fits, polymer aging/creep and service wear/life remain unverified.

Establish a production design using reviewed supplier conditions, tolerances,
retention and lubrication, independent reference calculations and physical
gearbox tests. See [release status](RELEASE_STATUS.md) and
[architecture and load assumptions](ARCHITECTURE.md).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Installation cannot find compatible wheels | Use 64-bit Python 3.12 in a fresh environment; check the platform and core version constraints |
| GUI cannot start on Linux | Run from a graphical session; inspect Qt display-library errors. The recorded host lacked `libxcb-cursor.so.0`, commonly supplied by `libxcb-cursor0` |
| Tests report missing `libEGL.so.1` | Install the Ubuntu Qt runtime libraries listed under Install and launch; `QT_QPA_PLATFORM=offscreen` does not remove this shared-library requirement |
| GUI is invisible after tests | Remove `QT_QPA_PLATFORM=offscreen` from the normal launch environment |
| No feasible candidates | Review rejection explanations; check ratio, envelope, torque, module, backlash, mode and catalog constraints |
| CAD/export requests regeneration | Requirements, profile or catalog changed; generate a new shortlist |
| Detailed CAD unavailable | Bevel, worm and cycloidal entries are concept-only |
| CAD export reports interference | Export report-only, inspect geometry/fit assumptions and sample tooth poses; a static pass alone is insufficient |
| CSV import rejected | Start with the exported template, preserve exact column order and inspect the reported row |
| Job cannot start | Check the installed environment and writable app-data directory; inspect the local log or run CLI diagnostics |
| Export path already exists | Choose a new output directory; existing exports are not overwritten |
