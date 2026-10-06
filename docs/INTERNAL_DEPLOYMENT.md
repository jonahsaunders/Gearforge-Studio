# Internal company deployment

GearForge Studio 1.0.0rc9 is an offline desktop tool for **prototype exploration
and engineering review**. This deployment guide does not approve a gearbox for
production, certify a load rating, or replace the company's engineering process.
The application retains visible prototype/concept labels in reports and exports.
The requested final-production scope remains blocked by the work in
[production qualification](PRODUCTION_QUALIFICATION.md); this guide covers the
software deployment portion only.

## Intended use and ownership

Use one installation per employee workstation and one local data directory per
OS user. IT owns the approved version, endpoint access, backups and updates. An
engineering owner approves permitted use, material profiles and supplier data.
Keep exported design packages in the company's existing controlled document
store, alongside review tickets and physical test evidence.

The application has no accounts, server, telemetry, automatic update service or
license server. Windows/macOS/Linux account permissions control local access.
There is no application-level encryption, SSO, team synchronization, immutable
audit log or company support SLA. Supplier links open a browser only on request.
Do not put the SQLite data directory on a shared network drive or a live cloud
sync folder. Use approved storage for saved projects and completed exports.

## Approve a deployment artifact

1. Record the reviewed Git commit, version, platform and package SHA-256. Retain
   the source, package, test evidence, dependency inventory and notices together.
2. Check the platform's CI tests and frozen-app smoke evidence. A source test
   pass is not proof that a packaged executable works. Review
   root `VALIDATION.json` for version-specific evidence. `docs/INTERNAL_VALIDATION.json`
   records the historical rc3 build only.
3. Review the exact `licenses/DEPENDENCIES.json`, `requirements-runtime.txt`,
   `vulnerability-audit.json` and `sbom.cdx.json`. Inventory covers the declared
   runtime closure, including libraries excluded from the frozen application.
   Scans cover known Python package advisories, not every native-library issue.
4. Verify the archive checksum using `Get-FileHash -Algorithm SHA256` on Windows
   or `sha256sum` on Linux. Get the expected checksum through a trusted company
   channel: a checksum beside an untrusted download is not proof of authorship.
5. The provided native archives are **unsigned**. IT must approve the unsigned
   pilot artifact or sign it through its own approved distribution process.
   Signing certificates and notarization credentials are not part of this repo.
6. Run the acceptance procedure below as a standard, non-administrator user on
   the actual workstation image before broad deployment.

The pipeline refuses a release build on test, dependency-audit or native smoke
failure. Releases created by the tag workflow remain drafts and prereleases.
There is no automatic production rollout.

## Install and launch

For an approved native archive, extract the **entire** directory to a
version-specific location such as `C:\CompanyApps\GearForge\1.0.0rc9`. Keep
`GearForgeStudio.exe` and `_internal` together. Launch the executable. Runtime
operation does not require an internet connection or Python installation.

For source installs, use 64-bit Python 3.12 (the tested runtime; package support
also allows 3.13). Python 3.11 is no longer supported by the pinned SciPy release.
In a clean environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints-release.txt --upgrade pip
.\.venv\Scripts\python.exe -m pip install -c constraints-release.txt .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m gearforge doctor
.\.venv\Scripts\python.exe -m gearforge gui
```

IT can prepare an offline Python wheelhouse on an approved connected machine of
the same OS, architecture and Python version: download the built application
wheel and the exact runtime requirements with `pip download --only-binary=:all:`.
Retain hashes of all wheels and install with `--no-index --find-links` from the
approved wheelhouse. The native archive is the already bundled offline option.
The source-kit launchers download dependencies on first run.

## Data, recovery and backup

By default Qt chooses the per-user application-data directory. Set
`GEARFORGE_DATA_DIR` to an absolute, local, writable directory for managed use.
For example, in PowerShell before launching:

```powershell
$env:GEARFORGE_DATA_DIR = "$env:LOCALAPPDATA\Company\GearForge"
.\.venv\Scripts\python.exe -m gearforge gui
```

The directory holds `catalog.sqlite` (gears and saved print profiles),
`settings.ini`, `recovery.gearforge` and rotating local logs. A session lock
prevents two application instances from modifying the same directory. If an
instance is active, close it normally; do not remove its lock file.

Autosave retains the most recent valid unsaved project every 30 seconds. It is
not version history or a backup of all projects. Restore it with **File → Restore
autosave**, then save to a normal project location. Logs may contain paths and
error details; share them under the company's data-handling rules.

Close the application, then run the maintenance commands from the approved
Python environment, or use `GearForgeCLI.exe` from the Windows native package
in place of `python -m gearforge` for visible diagnostics and scripted reports:

```powershell
python -m gearforge backup --data-dir "$env:LOCALAPPDATA\Company\GearForge" --out "D:\Backups\GearForge-2026-10-06"
python -m gearforge verify "D:\Backups\GearForge-2026-10-06"
python -m gearforge restore "D:\Backups\GearForge-2026-10-06" --data-dir "$env:LOCALAPPDATA\Company\GearForge-restored"
```

Backup uses SQLite's backup API, checks database integrity and records hashes.
It contains the catalog/profiles, settings and recovery file, **not project files
saved elsewhere, completed exports or logs**. Back those up separately using the
company's document system. Restore verifies hashes and database integrity and
only writes to a new directory; existing data is never intentionally replaced.
Point `GEARFORGE_DATA_DIR` at the restored directory to perform a recovery drill.
Keep backup access as restricted as the original data; backups are not encrypted.

## Repeatable design review

An export preserves `design.gearforge`, `catalog.csv`, and `provenance.json`,
including project name/notes, requirements, print profile, runtime versions and
the selected design. The manifest records a UTC creation time and file hashes.
Catalog edits invalidate previous desktop results. Generate designs again before
exporting. Saved design snapshots are informational; they are not trusted CAD.

```text
python -m gearforge verify design-export
python -m gearforge search design-export/design.gearforge --catalog design-export/catalog.csv --out replay.json
```

Use the same application version, requirements, catalog and search limit when
comparing candidate IDs. Exact output bytes can differ with timestamps and
platform-dependent CAD/PDF serialization. Hash verification detects missing,
changed and extra files, but is not a digital signature or an engineering
approval. Keep approvals in the company's existing review system.

## Workstation acceptance and rollback

- Launch all five workspaces; confirm text, controls, keyboard navigation and
  window sizing on the intended monitor configuration.
- Open the included hybrid example, search, select a design, load CAD, seek and
  step the simulation, cancel a CAD job, and confirm another search still works.
- Save and reopen a project with company terminology and non-ASCII text. Change
  requirements and confirm export is blocked until regeneration.
- Open **Design → Engineering study**, calculate the target, edit its duty,
  confirm old results disappear, then save/reopen and verify its exported bundle.
  Back up `.gearforge-study` files separately; they are not part of catalog backup.
- Transfer a gear study into its shaft load editor, change the support positions,
  recalculate, and verify the shaft report. Back up `.gearforge-shaft` files with
  the project records; they are also separate from catalog backup.
- Import the approved supplier catalog. Test that an invalid import preserves
  existing records and that a successful import clears previous results.
- Export a report-only and a full prototype package into new directories; verify
  the manifest and inspect CAD in the company's downstream tool.
- Back up and restore into a separate data directory. Check profiles, catalog
  records and recovery before declaring the backup process operational.
- Confirm the software's preliminary assumptions and concept-only families are
  acceptable to the engineering owner. Production parts require independent
  engineering validation, supplier ratings and physical verification.

For an upgrade, retain the old application and a verified pre-upgrade backup,
test the new version against a copy of the data, and then update the managed
shortcut. To roll back, close the application, restore the pre-upgrade backup to
a new directory and use it with the retained old version. Do not open a future
database schema with an older version. Saved project schema remains version 1.

## License and support handoff

Keep the application license, all collected notices and the full source revision
with the internal deployment record. Qt/PySide6 and Open CASCADE have separate
license obligations. The company should review the exact bundle and its method
of distribution, including access to corresponding library sources and library
replacement rights where applicable; collecting notices alone does not discharge
all obligations. See [Qt's licensing guidance](https://www.qt.io/development/open-source-lgpl-obligations)
and the [Apache 2.0 license](https://www.apache.org/licenses/LICENSE-2.0.html).

Assign an internal support owner, update-review cadence and incident channel.
For a defect record version, OS, steps, a sanitized example project, and relevant
logs; do not publish company designs in public issues. Use `SECURITY.md` for
private vulnerability reporting. No vendor response-time commitment is implied.

## Bearing-study acceptance

- Open **Design → Bearing duty and capacity…** and a supplied synthetic example.
- Verify both bearings, all duty conditions and the retained shaft source; change
  a capacity to an unknown value and confirm the life result becomes unassessed.
- Save/reopen `.gearforge-bearing`, export its assessment and verify the manifest.
- Keep these files with project backups. Synthetic inputs and basic per-bearing
  L10 never establish production gearbox life. See [method scope](BEARING_ANALYSIS.md).

## Shaft-fatigue study acceptance

- Open **Design → Shaft fatigue and material evidence…** and **Worked example**.
  Confirm the historical NASA fixture is visibly labeled as example data.
- Inspect material evidence, critical-section cuts and every retained duty case.
  Clear a strength input and confirm the damage becomes unassessed. Change a
  load model to unsupported and confirm it cannot retain a fatigue result.
- Save/reopen `.gearforge-fatigue`, export the assessment and verify its manifest.
  Preserve these files in project backups, separately from the catalog database.
- Review the finite-life range and omitted transient/critical-section coverage.
  The example is not material allowables or production approval. See
  [shaft fatigue methods](SHAFT_FATIGUE.md).

## Tooth-contact study acceptance

- Open **Design → Tooth contact and surface fatigue…**, load **Synthetic example**,
  calculate and inspect both material tabs, duty, contact path, provenance and assessment.
- Switch all four contact-path diagrams. Confirm the example reports about
  342.500436 MPa peak pressure and remains an unqualified synthetic study.
- Change material data or a load factor and confirm prior results and diagrams clear.
- Remove required factors, use an unsupported helical pair or move pressure beyond
  the entered life curve and confirm missing results stay explicitly unavailable.
- Save/reopen `.gearforge-contact`, export its assessment and verify the manifest.
  Confirm opposite flanks and pinion/wheel cycle counts remain separate.
- Review [the contact method and reference scope](CONTACT_ANALYSIS.md). The example
  curve, elastic limit and unity factors are invented arithmetic inputs.

## Thermal study acceptance

- Open **Design → Thermal network and cooling duty…**, load **Synthetic example**
  and calculate. Inspect all six tabs and the entered/settled histories for each body.
- Confirm the synthetic gear-body peak is about 60.79234545°C and the overall
  assessment remains incomplete. The example has invented losses and cooling data.
- Rename/add/remove bodies and heat-transfer paths and confirm phase inputs follow
  those edits. Reorder phases and confirm the entered trajectory changes.
- Clear a required loss/capacity value and confirm dependent trajectories are
  unavailable. Remove cooling and inspect the lack of a unique settled cycle.
- Save/reopen `.gearforge-thermal`, export and verify the assessment manifest.
  Review [thermal method/domain](THERMAL_ANALYSIS.md), including the distinction
  between calculated maxima and conservative bounds for every repeated cycle.
