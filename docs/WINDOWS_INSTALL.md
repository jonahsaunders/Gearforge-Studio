# Install GearForge Studio on Windows

Download [GearForge Studio 1.0.0rc13 for Windows x64](https://github.com/jonahsaunders/Gearforge-Studio/releases/download/v1.0.0rc13/GearForge-Studio-1.0.0rc13-Windows-x64-Setup.exe) from the repository’s [Releases page](https://github.com/jonahsaunders/Gearforge-Studio/releases/tag/v1.0.0rc13).

Run the installer and follow the prompts. It installs the full application for
your Windows account, normally under `%LOCALAPPDATA%\Programs\GearForge Studio`,
and adds **GearForge Studio** to the Start Menu. Administrator access, a Python
installation and an internet connection are not required to run the app.

The release is unsigned. Windows can show an unknown-publisher or reputation
prompt; follow your company’s workstation policy. Checksums are available next
to the release assets. The installer targets 64-bit Windows; its verification was
performed on Windows x64, not on ARM hardware.

Use the portable ZIP if you prefer an extracted application folder. Extract the
entire archive and run `GearForgeStudio.exe`; keep `_internal` alongside it.
`GearForgeCLI.exe` provides command-line tools and diagnostics. Downloading just
`GearForgeStudio.exe` from an extracted folder is insufficient; the installer
executable is the complete one-file download.

## Updates and removal

Close GearForge Studio before uninstalling. Use **Settings → Apps → Installed
apps → GearForge Studio → Uninstall**, or its Start Menu uninstaller. Installation
requires an empty destination; uninstall an older version before installing a
replacement. User settings, catalog data and projects are kept. Uninstall removes
only files shipped by the package; it does not recursively erase the destination.

Projects can be saved wherever you choose. Store work outside the program folder.
See [backup and restore](INTERNAL_DEPLOYMENT.md) before transferring workstations.

## Company deployment

The installer supports NSIS’s `/S` silent option. An optional `/D=...` destination
must be last on the command line and unquoted, even when it contains spaces:

```text
GearForge-Studio-1.0.0rc13-Windows-x64-Setup.exe /S /D=C:\CompanyApps\GearForge
```

The destination must be empty and writable by the current user. This is a per-user
installation; it does not register machine-wide associations or modify PATH.

This is an engineering release candidate. Making it easy to install does not
establish production gearbox load/life ratings. See [release scope](RELEASE_STATUS.md).
