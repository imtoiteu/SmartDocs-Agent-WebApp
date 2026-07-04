#!/usr/bin/env bash
# ============================================================================
#  scripts/setup.sh — one-time (idempotent) local environment setup.
#
#    * finds or creates a Python virtualenv (never clobbers an existing one)
#    * installs requirements.txt into it
#    * seeds .env from .env.example if missing
#    * creates the runtime folders the app writes to (logs/ uploads/ artifacts/)
#
#  Safe to re-run. Does NOT touch the GLM-OCR MLX venv (that is Apple-Silicon
#  only and lives in the external GLM-OCR checkout).
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env
ensure_dirs

info "SmartDocs-Agent setup"
hr
info "Repo root: $REPO_ROOT"

# --- 1. Resolve or create the virtualenv -----------------------------------
VENV_PY=""
if VENV_PY="$(venv_python)"; then
  ok "Using existing virtualenv: $(cd "$(dirname "$VENV_PY")/.." && pwd)"
else
  info "No virtualenv found — creating one at $REPO_ROOT/.venv"
  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found on PATH. Install Python 3.10+ and re-run."
    exit 1
  fi
  python3 -m venv "$REPO_ROOT/.venv"
  VENV_PY="$REPO_ROOT/.venv/bin/python"
  ok "Created virtualenv: $REPO_ROOT/.venv"
fi

PYVER="$("$VENV_PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo '?')"
info "Python: $VENV_PY (v$PYVER)"

# --- 2. Install dependencies ------------------------------------------------
if [ -f "$REPO_ROOT/requirements.txt" ]; then
  info "Upgrading pip and installing requirements.txt (this can take a while)…"
  "$VENV_PY" -m pip install --upgrade pip >/dev/null
  "$VENV_PY" -m pip install -r "$REPO_ROOT/requirements.txt"
  ok "Dependencies installed"
else
  warn "requirements.txt not found — skipping dependency install"
fi

# --- 3. Seed .env -----------------------------------------------------------
if [ ! -f "$REPO_ROOT/.env" ] && [ -f "$REPO_ROOT/.env.example" ]; then
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  ok "Created .env from .env.example (edit it to set ports / API keys)"
elif [ -f "$REPO_ROOT/.env" ]; then
  ok ".env already present — left untouched"
fi

# --- 4. Runtime folders -----------------------------------------------------
mkdir -p "$REPO_ROOT/logs" "$REPO_ROOT/uploads" "$REPO_ROOT/artifacts"
ok "Runtime folders ready: logs/ uploads/ artifacts/"

hr
ok "Setup complete."
echo
echo "Next:"
echo "  scripts/check.sh       # verify environment, ports, health"
echo "  scripts/start.sh       # start the full local stack (GLM if enabled)"
echo "  scripts/start_web.sh   # start only the web app"
