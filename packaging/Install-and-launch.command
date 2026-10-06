#!/usr/bin/env bash
set -euo pipefail
gearforge_kit_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
exec bash "$gearforge_kit_dir/Install-and-launch.sh"
