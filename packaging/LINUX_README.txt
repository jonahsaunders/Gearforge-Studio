GEARFORGE STUDIO 1.0.0rc2 — Linux native release candidate

Extract the entire directory, retain _internal, then run ./GearForgeStudio.
The executable includes its Python, Qt and CAD dependencies.

Target: Linux x86_64 with glibc 2.39 or newer (Ubuntu 24.04 class systems).
The bundle was tested in a headless Linux environment using Qt offscreen. An
interactive X11/Wayland desktop and its system display libraries are required.
On Ubuntu 24.04, install the Qt runtime libraries with:
  sudo apt-get install libegl1 libgl1 libopengl0 libxkbcommon0 libxcb-cursor0
EGL/OpenGL libraries are required even for Qt's offscreen desktop tests.
Qt's X11 plugin requires libxcb-cursor.so.0; distributions commonly provide it
as libxcb-cursor0. This host does not have that system library, so interactive
desktop startup could not be tested here. Qt offscreen desktop/search/CAD worker
checks are recorded in desktop-smoke.json.

CLI examples:
  ./GearForgeStudio doctor
  ./GearForgeStudio new design.gearforge
  ./GearForgeStudio search design.gearforge --out candidates.json
  ./GearForgeStudio export design.gearforge --out design-export

No telemetry or automatic purchasing. Data is stored in the local Qt application
data directory; set GEARFORGE_DATA_DIR to choose another directory.

This is a prototype engineering release candidate, not a validated commercial
gearbox load rating system. Read _internal/documentation/RELEASE_STATUS.md and bundled
license notices before distribution or production engineering use.
