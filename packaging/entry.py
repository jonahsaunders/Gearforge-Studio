"""Frozen desktop launcher also dispatches local background workers and CLI commands."""
import sys
import os
from pathlib import Path

# PyInstaller's SWIG analysis places _casadi at the bundle root while its
# dependent DLLs remain in casadi/. Keep that trusted directory registered for
# the entire process, including background CAD workers.
_dll_handles = []
if sys.platform == "win32" and getattr(sys, "frozen", False):
    casadi_directory = Path(sys._MEIPASS) / "casadi"
    if casadi_directory.is_dir():
        _dll_handles.append(os.add_dll_directory(str(casadi_directory)))
for channel in ("stdout","stderr"):
    if getattr(sys,channel) is None:setattr(sys,channel,open(os.devnull,"w"))
from gearforge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
