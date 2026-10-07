#!/usr/bin/env bash
set -euo pipefail
gearforge_kit_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
gearforge_version="$(cat "$gearforge_kit_dir/VERSION.txt")"
gearforge_env_dir="${XDG_DATA_HOME:-$HOME/.local/share}/GearForgeStudio/venv-$gearforge_version"
gearforge_python="${GEARFORGE_PYTHON:-python3}"
if ! command -v "$gearforge_python" >/dev/null 2>&1; then
  echo "Install 64-bit Python 3.12 or 3.13, then run this launcher again."
  exit 1
fi
"$gearforge_python" -c 'import sys; assert (3,12) <= sys.version_info[:2] < (3,14), "Python 3.12–3.13 is required"'
if [ ! -x "$gearforge_env_dir/bin/python" ]; then
  "$gearforge_python" -m venv "$gearforge_env_dir"
fi
if ! "$gearforge_env_dir/bin/python" -m pip show gearforge-studio >/dev/null 2>&1; then
  "$gearforge_env_dir/bin/python" -m pip install -c "$gearforge_kit_dir/constraints-release.txt" --upgrade pip
  "$gearforge_env_dir/bin/python" -m pip install -c "$gearforge_kit_dir/constraints-release.txt" "$gearforge_kit_dir"/dist/gearforge_studio-"$gearforge_version"-py3-none-any.whl
fi
exec "$gearforge_env_dir/bin/python" -m gearforge gui
