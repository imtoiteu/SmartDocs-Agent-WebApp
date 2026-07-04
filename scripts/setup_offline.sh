#!/usr/bin/env bash
# ============================================================================
#  scripts/setup_offline.sh — run tools/setup_offline.py with the CORRECT Python.
#
#  Why this exists: typing `python tools/setup_offline.py` uses whatever python
#  is on PATH — often the SYSTEM interpreter, which has none of the app's
#  dependencies. The run then "succeeds" for pure-download steps but silently
#  skips VietOCR config.yml, Argos, embeddings ("No module named 'vietocr'/
#  'PIL'/…"), while scripts/check.sh — which resolves the venv — says everything
#  imports fine. This wrapper resolves the MAIN SmartDocs venv the same way
#  scripts/check.sh does ($SMARTDOCS_PYTHON → <repo>/.venv → <repo>/../.venv)
#  and refuses to fall back to a bare system python.
#
#  Usage:  scripts/setup_offline.sh          (online, once per clean clone)
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env

# STRICT venv resolution — deliberately NOT resolve_python(), whose system-python
# fallback is exactly the wrong-interpreter bug this wrapper prevents.
if ! PY="$(venv_python)"; then
  err "Main SmartDocs venv Python not found."
  err "Looked for: \$SMARTDOCS_PYTHON, $REPO_ROOT/.venv/bin/python, $(cd "$REPO_ROOT/.." && pwd)/.venv/bin/python"
  err "Run scripts/setup.sh first (or set SMARTDOCS_PYTHON in .env)."
  exit 1
fi

ok "Using main venv Python: $PY"
cd "$REPO_ROOT"
exec "$PY" "$REPO_ROOT/tools/setup_offline.py" "$@"
