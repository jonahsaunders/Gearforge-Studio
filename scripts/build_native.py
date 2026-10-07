"""Build with a controlled Windows DLL search path, avoiding unrelated app DLLs."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def build_environment():
    environment=os.environ.copy()
    if sys.platform=="win32":
        windows=Path(os.environ["SystemRoot"])
        environment["PATH"]=os.pathsep.join(map(str,(
            Path(sys.executable).parent,Path(sys.base_prefix),windows/"System32",windows)))
    return environment


if __name__=="__main__":
    subprocess.run([sys.executable,"-m","PyInstaller",str(ROOT/"packaging/gearforge.spec"),
                    "--noconfirm","--clean"],cwd=ROOT,env=build_environment(),check=True)
