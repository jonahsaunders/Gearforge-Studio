# Security and reporting

The app operates locally, with no telemetry or update/license server. Projects
are size-limited JSON; workers use local JSON files and do not execute project
code. Treat imported catalogs and supplier links as untrusted input. Filesystem
exports never overwrite an existing design directory.

For a vulnerability, use the repository's private security advisory reporting
if enabled. If unavailable, contact the repository owner privately; do not post
exploit details in public issues. This source kit does not designate a fictional
security contact or claim a response SLA. Only the current release candidate is
maintained; no commercial support agreement is implied.
