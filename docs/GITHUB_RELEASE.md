# Prepare and publish on GitHub

The source kit is ready for a new repository. The tested core dependency versions
are pinned in constraints-release.txt; it is not a complete platform lockfile. No remote repository or published
release was created by this preparation. Generated CAD, runtime databases,
build output, credentials and native dependencies are excluded by `.gitignore`.

From the extracted source kit, install development dependencies and verify:

```sh
python -m pip install -c constraints-release.txt '.[dev]'
python scripts/check_version.py
python -m pytest -q
python -m build
```

Create an empty GitHub repository and use your configured Git author identity:

```sh
git init -b main
git add .
git commit -m "Prepare GearForge Studio 1.0.0rc2"
git remote add origin https://github.com/jonahsaunders/Gearforge-Studio.git
git push -u origin main
```

CI tests Linux, Windows and macOS. Review every platform result and perform the
manual platform checks in GUI_AUDIT.md. The release workflow needs repository
Actions enabled and permission to create releases. Create the matching tag when
ready to build native assets:

```sh
git tag -a v1.0.0rc2 -m "GearForge Studio 1.0.0rc2"
git push origin v1.0.0rc2
```

Tag/version mismatch stops the build. The separate numeric macOS build is `tool.gearforge.release.macos-build` in
pyproject.toml; increment it for each distributed Mac build. Each target runs
the regression suite, collects dependency licenses, freezes the app, runs the frozen desktop/CAD smoke
test and writes an archive/checksum. All three jobs must succeed. The final job
verifies checksums and creates a **draft prerelease**, attaching native assets,
the source kit, checksums and prepared release notes. It never publishes the
draft automatically. Manual workflow_dispatch on main builds artifacts only.

Before publication, verify asset architectures, extract each archive, launch on
the target system, check legal notices, and add signed/notarized replacements
when available. The current workflow intentionally emits unsigned artifacts;
it contains no placeholder signing keys or unverifiable signing claims.
`macos-14` produces the runner's architecture, not a universal binary. Linux
requires glibc 2.39+. Platform and signing evidence must be updated from actual
CI/manual results, rather than treating these workflow files as proof of success.

For a local native build:

```sh
python scripts/collect_licenses.py
python -m PyInstaller packaging/gearforge.spec --noconfirm
python scripts/native_archive.py --smoke
python scripts/build_release.py
```

See [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
and [PyInstaller bundle specification](https://pyinstaller.org/en/stable/spec-files.html).
