# Contributing

Use Python 3.12 and `python -m pip install '.[dev]'`. Run `python -m pytest -q`
with `QT_QPA_PLATFORM=offscreen` when no display is available. CAD tests build
real solids; preserve them when changing tooth geometry, layouts or exports.
Add meaningful regression coverage for changed numerical behavior. Review
simulation assumptions and commercial-component source conditions explicitly.

Keep generated CAD, databases, binary builds and credentials out of commits.
Describe the problem, resulting behavior, validation and material limitations
in pull requests. Update both package/runtime versions and release notes for a
release. See `docs/GITHUB_RELEASE.md` for tag/build/draft-release instructions.
