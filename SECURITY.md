# Security and reporting

The app operates locally, with no telemetry or update/license server. Projects
are size-limited JSON; workers use local JSON files and do not execute project
code. Treat imported catalogs and supplier links as untrusted input. Filesystem
exports never overwrite an existing design directory.

Use rc3 or later: rc2 pinned VTK 9.3.1, which has published GLTF-loader
vulnerabilities. GearForge has no GLTF import feature, but rc3 updates the CAD
dependency set to VTK 9.6.2 rather than excluding those advisories from scans.
CI and release builds audit all resolved runtime dependencies and fail on
reported vulnerabilities. A clean scan is not a penetration test or a guarantee
against unknown vulnerabilities or native-library issues.

rc3 also upgrades PySide6/Qt from 6.8.3 to 6.11.2 after reviewing
https://wiki.qt.io/List_of_known_vulnerabilities_in_Qt_products . This addresses
the older QtCore, SVG and related fixes present in that release. Native Qt
advisories are not comprehensively represented by pip-audit. Review upstream
advisories as well as the package scan before each deployment. The app uses
Qt Widgets, not Qt's VNC Server or QDom XML serialization; do not interpret this
as a blanket waiver for every Qt module or future application feature.

Data directories are per-user and locked during application use. Backups and
exports are unencrypted local data; protect them with OS permissions and company
storage controls. Hash verification checks integrity, not authenticity. Worker
files are a local trusted application protocol, not a remote API or sandbox.
Production engineering qualification is a separate process documented in
`docs/PRODUCTION_QUALIFICATION.md`.

For a vulnerability, use the repository's private security advisory reporting
if enabled. If unavailable, contact the repository owner privately; do not post
exploit details in public issues. This source kit does not designate a fictional
security contact or claim a response SLA. Only the current release candidate is
maintained; no commercial support agreement is implied.
