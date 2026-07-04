#!/usr/bin/env bash
# ============================================================================
#  scripts/check.sh — diagnose the local runtime. Read-only; changes nothing.
#
#  Reports:
#    * repo root + resolved Python interpreter / venv + version
#    * presence of key dependencies (flask + the app's own config import)
#    * web port + GLM port state (free / in use)
#    * SmartDocs health   (HTTP response on the web port)
#    * GLM health         (POST /chat/completions -> 200) — optional
#
#  Exit code: 0 if the core web stack looks healthy or simply not running;
#  non-zero only when something is clearly broken (e.g. no Python / no Flask).
#  GLM being down is NEVER an error here (it is optional).
# ============================================================================
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env

FAIL=0

info "SmartDocs-Agent — environment check"
hr
info "Repo root : $REPO_ROOT"

# --- Python -----------------------------------------------------------------
if PY="$(resolve_python)"; then
  PYVER="$("$PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo '?')"
  ok "Python: $PY (v$PYVER)"
  case "$PYVER" in
    3.10.*|3.11.*|3.12.*) : ;;
    3.1[3-9].*|4.*)  warn "Python $PYVER is newer than the verified 3.10 — deps may not resolve." ;;
    3.[0-9].*)       warn "Python $PYVER is older than the recommended 3.10." ;;
    *)               warn "Could not parse Python version." ;;
  esac
else
  err "No Python interpreter found. Run scripts/setup.sh."
  FAIL=1
  PY=""
fi

# --- Dependencies -----------------------------------------------------------
if [ -n "$PY" ]; then
  if "$PY" -c 'import flask' >/dev/null 2>&1; then
    ok "Flask import OK"
  else
    err "Flask not importable — run scripts/setup.sh to install requirements.txt"
    FAIL=1
  fi
  # Import the app's own config (validates the project is on sys.path + parseable).
  if ( cd "$REPO_ROOT" && "$PY" -c 'import config' >/dev/null 2>&1 ); then
    ok "App config import OK"
  else
    warn "Could not import the app 'config' module (may need full deps / env)."
  fi
fi

# --- Ports ------------------------------------------------------------------
hr
if port_in_use "$SMARTDOCS_PORT"; then
  ok "Web port $SMARTDOCS_PORT: in use (SmartDocs likely running)"
else
  info "Web port $SMARTDOCS_PORT: free (SmartDocs not running)"
fi
if port_in_use "$GLM_PORT"; then
  ok "GLM port $GLM_PORT: in use"
else
  info "GLM port $GLM_PORT: free (GLM server not running — optional)"
fi

# --- Health -----------------------------------------------------------------
hr
if command -v curl >/dev/null 2>&1; then
  if smartdocs_health; then
    ok "SmartDocs health: responding on http://${SMARTDOCS_LOCAL_HOST}:${SMARTDOCS_PORT}/"
  else
    info "SmartDocs health: not responding (start it with scripts/start_web.sh)"
  fi

  if [ "$ENABLE_GLM" = "true" ]; then
    if glm_health; then
      ok "GLM health: 200 on ${GLM_OCR_API_URL} (model: ${GLM_MODEL})"
    else
      info "GLM health: not responding on ${GLM_OCR_API_URL} (optional — start with scripts/start_glm.sh)"
    fi
  else
    info "GLM: disabled (ENABLE_GLM=false) — Legacy/VietOCR/Modern OCR still work."
  fi
else
  warn "curl not found — skipping HTTP health checks."
fi

hr
if [ "$FAIL" -eq 0 ]; then
  ok "Core environment looks good."
else
  err "One or more core checks failed (see above)."
fi
exit "$FAIL"
