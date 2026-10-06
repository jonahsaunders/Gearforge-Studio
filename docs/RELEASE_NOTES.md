# GearForge Studio 1.0.0rc2

This release candidate improves the desktop interface and simulation workflow.

- Native platform controls/system font, appearance and text-size preferences,
  resizable sidebar, standard shortcuts and macOS application-menu roles.
- Named accessible inputs, keyboard viewer controls, document state/path support
  and a Finder file-open handler.
- Timed rigid-body CAD animation with pause, reverse, seek, slow motion and tooth
  stepping; CAD survives playback. Reduced-motion controls prevent automatic play.
- A simulation workspace with motor/load curves, power-loss and overload tables,
  JSON/CSV export and optional exact tooth intersections at sampled input poses.
- File-based background workers compatible with windowed executable builds.
- Cross-platform test/build workflows, version/tag checks, native archives and
  checksums; successful tag builds create a draft GitHub prerelease.
- macOS .app target with icon/project document metadata and Windows windowed UI.

Detailed tooth CAD is available for spur, helical and fixed-ring planetary
prototypes. Bevel, worm and cycloidal searches remain concept-only. Numerical
screens and simulations are not certified commercial gearbox load ratings.
Thermal, fatigue, continuous contact, manufactured fits and retention require
independent validation. See `docs/SIMULATION.md` and `docs/RELEASE_STATUS.md`.

Linux x86_64 is the locally built/tested native target (Ubuntu 24.04 class,
glibc 2.39+). Windows/macOS targets are configured in CI but have not run in this
workspace. Assets are unsigned. macOS VoiceOver/Finder/system appearance and
signed/notarized distribution need a real platform validation pass. This is a
prerelease and must not be labeled a fully validated commercial engineering app.
