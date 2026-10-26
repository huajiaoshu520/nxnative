#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.dotnet:$PATH"
PY="${NX_PYTHON:-python3}"
if [ "$#" -eq 0 ]; then set -- --select; fi
rc=0
"$PY" scripts/nx_one_click.py --platform mac-app "$@" || rc=$?
if [ -t 0 ]; then read -r -p 'Press Return to close...' _ || true; fi
exit "$rc"
