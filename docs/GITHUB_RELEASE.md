# Prepare and publish on GitHub

The repository has regression and release workflows. Runtime dependency versions
are pinned in constraints-release.txt; per-platform inventory and audit evidence
are retained with release artifacts. No production engineering approval is implied. Generated CAD, runtime databases,
build output, credentials and native dependencies are excluded by `.gitignore`.

From the extracted source kit, install development dependencies and verify:

```sh
python -m pip install -c constraints-release.txt --upgrade pip
python -m pip install -c constraints-release.txt '.[dev]' pip-audit
python scripts/check_version.py
python -m pytest -q
python -m build
```

Only for a new repository created from an extracted source kit, use your configured Git author identity:

```sh
git init -b main
git add .
git commit -m "Prepare GearForge Studio 1.0.0rc13"
git remote add origin https://github.com/jonahsaunders/Gearforge-Studio.git
git push -u origin main
```

CI tests Linux, Windows and macOS. Review every platform result and perform the
manual platform checks in GUI_AUDIT.md. The release workflow needs repository
Actions enabled and permission to create releases. Create the matching tag when
ready to build native assets:

```sh
git tag -a v1.0.0rc13 -m "GearForge Studio 1.0.0rc13"
git push origin v1.0.0rc13
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
python -m pip_audit --no-deps --disable-pip -r release-licenses/requirements-runtime.txt --format json --output release-licenses/vulnerability-audit.json
python -m pip_audit --no-deps --disable-pip -r release-licenses/requirements-runtime.txt --format cyclonedx-json --output release-licenses/sbom.cdx.json
python scripts/build_native.py
python scripts/native_archive.py --smoke
python scripts/build_release.py
```

See [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
and [PyInstaller bundle specification](https://pyinstaller.org/en/stable/spec-files.html).

The native build wrapper limits Windows DLL lookup to the active Python runtime
and Windows system paths, preventing unrelated applications on PATH from supplying
incompatible native libraries. The Windows package includes GearForgeCLI.exe for
visible diagnostics. The smoke gate exercises the GUI/CAD process and the windowed
worker entry point separately, retaining build/frozen-smoke.log on failure.

## Windows installer

After the frozen Windows smoke passes, run:

```sh
python scripts/build_windows_installer.py
python scripts/test_windows_installer.py
python scripts/native_archive.py
```

The compiler download is NSIS 3.13, pinned by SHA-256 and used from `build/`.
No installer compiler is installed system-wide. The complete `.exe`, portable ZIP
and their checksums are produced under `release-assets/`. The installer test must
run on a clean build account: it refuses to replace existing GearForge registration
or Start Menu entries, verifies every installed file, runs the installed GUI/CAD
without Python on PATH, then checks uninstall and user-file preservation.

The release workflow builds and tests this installer on its Windows runner.
All-target tag builds still require all platform jobs before creating a draft.
A maintainer may separately publish a verified Windows-only prerelease; the draft
job then retains its artifacts without replacing the already published files.
Never label that Windows-only download as a verified current Mac/Linux bundle.
