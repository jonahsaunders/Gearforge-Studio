# Development and packaging

[Back to the overview](../README.md) · [Contributing](../CONTRIBUTING.md)

## Development and testing

Install the development dependencies using the tested constraints:

```bash
python -m pip install -c constraints-release.txt --upgrade pip
python -m pip install -c constraints-release.txt '.[dev]' pip-audit
python scripts/check_version.py
python -m pytest -q
```

For a headless Linux/macOS test run:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q --junitxml=build/test-results.xml
```

For PowerShell:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest -q --junitxml=build/test-results.xml
Remove-Item Env:QT_QPA_PLATFORM
```

Version-specific regression and native package evidence is indexed in
[VALIDATION.json](../VALIDATION.json). The rc12 implementation passed 351 tests on each of Windows, Linux and macOS,
plus native-package smoke checks and open-reference comparisons. Older release
records describe their own implementation and do not validate a newer build.
The index's `development_evidence` entry tracks unreleased numerical additions
separately from the recorded rc12 native-package baseline.
Coverage includes numerical constraints, catalogs/projects, CLI/worker flows,
real CAD solids/interference/STEP round-trips, export manifests, timed motion,
planetary relations, power balance, stale results and reduced-motion behavior.
A deliberately misaligned gear phase is a negative control for collision detection.
See [open engineering](OPEN_ENGINEERING.md) for the numerical reference scope.

The [regression workflow](https://github.com/jonahsaunders/Gearforge-Studio/actions/workflows/ci.yml)
checks all three target operating systems and uploads test results. Headless
desktop tests do not establish interactive platform usability or physical
gearbox load/life validation.

## Build packages and GitHub releases

Build on the target operating system with development dependencies installed:

```bash
python -m build
python scripts/collect_licenses.py
python -m pip_audit --no-deps --disable-pip -r release-licenses/requirements-runtime.txt --format json --output release-licenses/vulnerability-audit.json
python -m pip_audit --no-deps --disable-pip -r release-licenses/requirements-runtime.txt --format cyclonedx-json --output release-licenses/sbom.cdx.json
python scripts/build_native.py
python scripts/native_archive.py --smoke
python scripts/build_release.py
```

To produce the clean repository ZIP for uploading source code, run
`python scripts/package_github.py`. It places the archive under `release-assets/`
with `README.md` at its root and includes a per-file SHA-256 list.

The result includes wheel/source distributions, target-native archives,
checksums and a source release kit. Keep dependency notices with native bundles.
The macOS spec generates an `.app` with project document metadata; Windows uses a
windowed executable and a file-based worker protocol. Windows also includes
`GearForgeCLI.exe` for console commands, backup/restore and visible diagnostics.

| Workflow | Trigger | Result |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Pull requests, pushes to `main`, weekly and manual runs | Dependency audit and Python 3.12 tests on Linux, Windows and macOS |
| `.github/workflows/release.yml` | `v*` tags or manual run | Tests, native builds, frozen smoke checks, archives and checksums |
| Release draft job | Matching tag after all native builds succeed | Creates a draft prerelease with assets and release notes |

For the current release:

```bash
git tag -a v1.0.0rc12 -m "GearForge Studio 1.0.0rc12"
git push origin v1.0.0rc12
```

The tag must match package/runtime versions. Manual builds on `main` upload
workflow artifacts without creating a release draft. The separate numeric
macOS build in `pyproject.toml` must increase for each distributed Mac build.

Review platform results, manually launch on each target, and complete signing,
macOS notarization and the accessibility/platform checks before publication.
The workflow does not automatically publish its draft. Full instructions are in
[GitHub release preparation](GITHUB_RELEASE.md).

## Repository guide

| Path | Contents |
| --- | --- |
| `src/gearforge/` | Desktop UI, search engine, models, CAD, simulation, export and CLI code |
| `src/gearforge/data/` | Source-traceable seed catalog and application icon |
| `tests/` | Numerical, data, CAD, GUI, worker and release regression tests |
| `examples/` | Editable projects and separate examples for every engineering study |
| `screenshots/` | Nineteen actual app captures covering the desktop and all nine engineering workspaces |
| `docs/` | Architecture, simulation methods, GUI audit and release instructions |
| `packaging/` | Native build spec, launcher templates and supplemental license texts |
| `scripts/` | Version checks, license collection, package/archive creation and reproducible app captures |
| `.github/` | Test/release workflows and contribution templates |
| `VALIDATION.json` | Index of current software evidence and historical validation |

## Updating screenshots

From an installed development environment, run:

```bash
python scripts/capture_screenshots.py
```

The script runs the real app with the checked-in examples, calculates each study,
and captures 19 unmodified PNGs into `screenshots/`. It uses temporary application
data and light appearance; saved user projects, catalogs and preferences are
untouched. Windows offscreen captures use the installed Segoe UI font. Other
platforms use an available standard font and may render differently.

Use `--section desktop`, `--section studies` or `--section probes` to refresh a subset, and `--out`
to select another directory. `captures-all.json` (or the selected section name)
records the app version, platform, font, example paths, dimensions and hashes.
Review the images and the [gallery captions](GALLERY.md) before committing them.
Do not conceal prototype labels, synthetic-data notices or engineering limits.
