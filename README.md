<p align="center">
  <img src="src/gearforge/data/icon.svg" alt="GearForge Studio gear icon" width="80">
</p>

<h1 align="center">GearForge Studio</h1>

<p align="center"><strong>Explore gearbox designs. Understand the loads. Keep the evidence.</strong></p>

<p align="center">
  <a href="https://github.com/jonahsaunders/Gearforge-Studio/actions/workflows/ci.yml"><img src="https://github.com/jonahsaunders/Gearforge-Studio/actions/workflows/ci.yml/badge.svg" alt="Desktop regression tests"></a>
</p>

<p align="center">Offline desktop app · Windows / macOS / Linux · Apache-2.0 application code</p>

GearForge Studio brings gearbox search, 3D CAD, motion playback and nine engineering study workspaces into one local desktop application. Compare printed, catalog and hybrid designs; investigate geometry, loads, heat and fatigue; export the inputs and calculations behind each result.

**[Get started](#install-and-launch)** · **[Features](#features)** · **[Engineering workspaces](#engineering-workspaces)** · **[Screenshot gallery](docs/GALLERY.md)** · **[Documentation](#documentation)**

![GearForge Studio rc12: a 12:1 hybrid gearbox, generated 3D assembly, ranked candidates and engineering checks](screenshots/desktop.png)

> **Current version: 1.0.0rc12 — engineering release candidate.** Supports prototype design and engineering studies. Final production gearbox load/life ratings remain unqualified. Synthetic examples illustrate the methods; they are not material allowables. [Scope and remaining work →](docs/PRODUCTION_QUALIFICATION.md)

## Features

| Workflow | What you can do |
| --- | --- |
| **Find a design** | Enter speeds, torque, envelope, manufacturing mode and priorities. Search one- or two-stage templates; compare ranked candidates, Pareto flags and rejection reasons. |
| **Inspect real CAD** | Load spur, helical and planetary prototype solids. Orbit, zoom, show the housing and explode the assembly. Review geometry, shafts, bearings and hardware. |
| **Explore motion and operating points** | Play, pause, reverse, seek and step one input tooth. Sweep a motor curve or assumed torque envelope; inspect output torque, load margin and power loss. Run optional sampled tooth-intersection checks. |
| **Review modeled checks** | Inspect ratio error, available motor torque, backlash, tooth dimensions, contact ratio, preliminary bending, shaft and bearing screens, with assumptions visible. |
| **Work with catalog components** | Browse six source-traceable seed gears; import/export validated CSV catalogs. Preserve supplier URLs, rating conditions, retrieval dates and unknown prices. |
| **Calibrate printed parts** | Save material profiles, set backlash and fit clearances, export a dimensional coupon and apply measured shrink compensation. |
| **Save and recover work** | Use validated project files, autosave/recovery, local profiles, a data-directory lock and verified backup/restore. Background jobs can be cancelled; changed inputs invalidate stale results. |
| **Review and share** | Export CAD, print files, BOMs, reports, layouts and calculation evidence. New export directories are published atomically with file hashes and explicit qualification status. |
| **Make the workspace yours** | Use system/light/dark appearance, text sizing, a resizable sidebar, keyboard controls, accessible field labels and reduced-motion playback. |
| **Run batches offline** | Search, calculate, export, verify and diagnose from the command line. Normal design work stays on the workstation; there are no accounts or telemetry. |

<table>
  <tr>
    <td width="50%"><strong>Helical prototype</strong><br><img src="screenshots/helical.png" alt="Generated helical gearbox with opposite helix hands"></td>
    <td width="50%"><strong>Planetary prototype</strong><br><img src="screenshots/planetary.png" alt="Fixed-ring planetary gearbox with sun input and carrier output"></td>
  </tr>
</table>

[Explore CAD, simulation, catalog, calibration and report screenshots →](docs/GALLERY.md)

## Engineering workspaces

Open these workspaces from the **Design** menu. Each has editable inputs, explicit assumptions, saved study files and calculation exports. Transfers retain the source study where supported; missing material, supplier and operating evidence stays visible.

| Workspace and method guide | Included capabilities | Try an example |
| --- | --- | --- |
| **[Geometry and operating duty](docs/OPEN_ENGINEERING.md)** | External spur/helical geometry, profile shifts, operating center distance, contact ratios, duty cases, mesh forces, energy and revolution exposure. | [250 W steel spur study](examples/steel-spur-250w.gearforge-study) |
| **[Shaft loads and motion](docs/SHAFT_ANALYSIS.md)** | Stepped solid/hollow sections, two bearing supports, 3-axis forces and couples, reactions, deflection, slope, twist and nominal stress diagrams. | [Input shaft](examples/steel-spur-input.gearforge-shaft) |
| **[Bearing duty and capacity](docs/BEARING_ANALYSIS.md)** | Explicit ratings and duty factors; per-bearing basic L10 exposure, stationary peak loads, static safety, speed, temperature and misalignment checks. | [Synthetic bearing study](examples/steel-spur-synthetic.gearforge-bearing) |
| **[Shaft material and fatigue](docs/SHAFT_FATIGUE.md)** | Material evidence and bounded stress-life curves, selected critical sections, application factors, rotating bending and steady-torque fatigue blocks. | [NASA worked example](examples/nasa-shaft-fatigue.gearforge-fatigue) |
| **[Tooth contact and surface fatigue](docs/CONTACT_ANALYSIS.md)** | Spur Hertz pressure and sliding diagrams, declared load sharing, opposite-flank exposure, each gear's tooth cycles and bounded pressure-life curves. | [Synthetic contact study](examples/synthetic-contact.gearforge-contact) |
| **[Thermal network](docs/THERMAL_ANALYSIS.md)** | Thermal bodies and heat-transfer paths, ordered heating/cooling phases, continuous temperature extrema, energy balance, settled repeated duty and warm-up bounds. | [Synthetic thermal study](examples/synthetic-thermal.gearforge-thermal) |
| **[Rack-generated tooth profiles](docs/TOOTH_PROFILES.md)** | Explicit spur cutter geometry, generated root/involute joins, undercut/fold rejection, active-path checks, whole-gear/tooth views and sampled DXF/SVG/CSV profiles. | [Synthetic cutter study](examples/synthetic-tooth.gearforge-tooth) |
| **[Elastic tooth-root stress](docs/ROOT_STRESS.md)** | 2D finite-element stress on the generated spur profile, explicit supports and pressure patches, three mesh levels, a wider-sector comparison, signed stress at fixed material points, stress maps and CSV/VTK fields. | [Root study](examples/synthetic-root.gearforge-root) · [Fixed points](examples/synthetic-root-probes.gearforge-root) |
| **[Cyclic stress histories](docs/STRESS_HISTORY.md)** | Signed local stress samples, finite rainflow counts across repeated blocks, bounded uniaxial fatigue damage, duration/start coverage, CSV fingerprints and history/cycle/S–N plots. | [Synthetic history](examples/synthetic-history.gearforge-history) |

<table>
  <tr>
    <td width="50%"><strong>Generated tooth and root</strong><br><img src="screenshots/tooth.png" alt="Rack-generated tooth profile showing the involute and generated root"></td>
    <td width="50%"><strong>Elastic root stress</strong><br><img src="screenshots/root.png" alt="Finite-element stress map at one sampled tooth-load position"></td>
  </tr>
  <tr>
    <td><strong>Shaft deflection</strong><br><img src="screenshots/shaft.png" alt="Shaft support and deflection diagram from an explicit gear-load study"></td>
    <td><strong>Tooth contact pressure</strong><br><img src="screenshots/contact.png" alt="Spur Hertz pressure along the nominal contact path using synthetic inputs"></td>
  </tr>
  <tr>
    <td><strong>Heating and cooling</strong><br><img src="screenshots/thermal.png" alt="Synthetic thermal-network temperature history for the gear train"></td>
    <td><strong>Signed stress history</strong><br><img src="screenshots/history.png" alt="One template block of signed local stress used for finite rainflow counting"></td>
  </tr>
</table>

These are **actual app captures** using repository examples. [View all 19 images, example files and captions →](docs/GALLERY.md)

The prototype CAD pipeline and the rack-generated profile study are separate. Root stress evaluates sampled pressure-patch positions; it does not automatically produce a complete rolling-load fatigue history. See each method guide for its supported conditions and evidence requirements.

## Install and launch

Use **64-bit Python 3.12** for the tested setup. The package supports Python 3.12–3.13. A graphical desktop is required for normal GUI use; installation downloads dependencies, then design and calculation run locally.

```bash
git clone https://github.com/jonahsaunders/Gearforge-Studio.git
cd Gearforge-Studio
```

<details open>
<summary><strong>Windows · PowerShell</strong></summary>

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-release.txt .
.\.venv\Scripts\python.exe -m gearforge doctor
.\.venv\Scripts\python.exe -m gearforge gui
```

</details>

<details>
<summary><strong>macOS / Linux</strong></summary>

On Ubuntu 24.04, first install the Qt runtime libraries:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libgl1 libopengl0 libxkbcommon0 libxcb-cursor0
```

Then create the environment with Python 3.12 (on macOS, start here):

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -c constraints-release.txt .
.venv/bin/python -m gearforge doctor
.venv/bin/python -m gearforge gui
```

</details>

No environment activation is needed for these commands. After installation, `gearforge-studio` is the desktop entry point and `gearforge` is the CLI, in the environment's `Scripts` or `bin` folder.

**First design:** Open [`examples/12-to-1-hybrid.gearforge`](examples/12-to-1-hybrid.gearforge), choose **Generate designs**, select a candidate and choose **Load 3D CAD**. Inspect the checks, explore **Simulation workspace**, then export to a new folder. [Full walkthrough →](docs/USER_GUIDE.md#design-your-first-gearbox)

**First engineering study:** Choose **Design → Engineering study**, review the geometry and duty, then calculate. Open the other study examples in their matching workspaces using **Open study…** or **Open…**.

For company installation, native archives and backup/restore, use the [deployment guide](docs/INTERNAL_DEPLOYMENT.md). The rc12 native builds were checked on Windows x86_64, Linux x86_64 and macOS ARM64. Packages are unsigned; Linux bundles target glibc 2.39 or newer. [Exact build evidence →](VALIDATION.json)

## Supported designs

| Gear family | Search and arrangement | CAD scope |
| --- | --- | --- |
| **Spur** | One or two stages; printed, catalog or mixed gears | Prototype solids with sampled involute teeth |
| **Helical** | One or two stages; opposite helix hands | Prototype solids with twisted sampled involutes |
| **Planetary** | Fixed ring, sun input, three planets, carrier output | Prototype external/internal gears and carrier |
| **Bevel** | Single-stage ratio and packaging concepts | Reference layouts only |
| **Worm** | Starts/wheel ratios and assumed efficiency | Reference layouts only |
| **Cycloidal** | Integer reduction and packaging concepts | Reference layouts only |

**Manufacturing modes:** Printed gears and housing; catalog gears in a machined housing; or hybrid gear combinations in a printed housing. Shafts, bearings and fasteners are purchased or machined. Catalog mode builds a custom assembly from recorded gear dimensions.

The current prototype search covers reductions greater than 1:1 through 100:1, modules from 0.8 to 3.0 mm and at most two external-gear stages. It searches bounded templates and returns a ranked shortlist; it does not establish a global optimum. The separate engineering studies have their own input ranges.

## Exports and traceability

| Output | Included formats and records |
| --- | --- |
| **Prototype CAD and printing** | STEP assemblies/parts; STL and 3MF for printed components; optional print shrink compensation |
| **Design review** | PDF/HTML reports, BOM CSV, SVG layout and shaft references, assembly notes |
| **Engineering studies** | Retained study inputs, readable HTML assessment, calculation JSON and study-specific CSV data |
| **Profile and field data** | Sampled tooth DXF/SVG/CSV; root-stress CSV and VTK; cycle and raw-sample CSV |
| **Simulation** | Motor/load sweep JSON/CSV, static interference results and optional sampled tooth-check evidence |
| **Reproducibility** | Source project, catalog snapshot where applicable, calculation inputs, runtime provenance, qualification status and SHA-256 manifest |

Exports preserve existing directories. Changed inputs require recalculation. Unexpected static interference blocks CAD export; a report-only path remains available. `gearforge verify <directory>` checks a completed bundle against its manifest. Hashes establish file integrity, not engineering approval.

[Complete design export inventory →](docs/USER_GUIDE.md#exported-files) · [Batch commands →](docs/USER_GUIDE.md#command-line-interface)

## Verification and engineering scope

The rc12 implementation passed **351 regression tests on each of Windows, Linux and macOS**, plus native-package checks on all three platforms. [Recorded tests and exact commits](docs/HISTORY_VALIDATION.json) are separate from the live CI badge above.

Numerical comparisons cover geometry, shaft statics, bearing arithmetic, shaft fatigue, contact, heat balance, generated profiles, elastic fields and rainflow cycles. Reference checks use openly licensed tools or documented public worked examples; original synthetic fixtures are included in the repository. The history study alone has 25,788 independent numerical comparisons. [Methods and reference scope →](docs/OPEN_ENGINEERING.md)

Software verification does not qualify a physical gearbox. Actual material/process data, supplier conditions, lubrication, fits, retention, complete load histories and physical validation remain part of the [production qualification work](docs/PRODUCTION_QUALIFICATION.md). Reports retain this boundary, and production-required exports refuse to issue an unverified rating.

## Documentation

| I want to… | Start here |
| --- | --- |
| Use the app, understand controls or troubleshoot | [User guide](docs/USER_GUIDE.md) |
| See every workspace before installing | [19-image gallery](docs/GALLERY.md) |
| Understand a calculation and its limits | [Engineering workspaces](#engineering-workspaces) · [Simulation methods](docs/SIMULATION.md) |
| Install for employees, manage data or restore a backup | [Internal deployment](docs/INTERNAL_DEPLOYMENT.md) |
| Review current readiness and remaining work | [Release status](docs/RELEASE_STATUS.md) · [Qualification](docs/PRODUCTION_QUALIFICATION.md) · [Changelog](CHANGELOG.md) |
| Develop, test, build or refresh screenshots | [Development guide](docs/DEVELOPMENT.md) · [Architecture](docs/ARCHITECTURE.md) |
| Prepare a GitHub release | [Release workflow](docs/GITHUB_RELEASE.md) |

Contributions are welcome; read [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities using [SECURITY.md](SECURITY.md).

Application code is licensed under [Apache-2.0](LICENSE). Dependencies retain their own licenses; keep the [third-party notices](THIRD_PARTY_NOTICES.md) and the exact native build's notices with redistributed packages.
