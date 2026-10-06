"""Frozen desktop launcher also dispatches local background workers and CLI commands."""
import sys
import os
for channel in ("stdout","stderr"):
    if getattr(sys,channel) is None:setattr(sys,channel,open(os.devnull,"w"))
from gearforge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
