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
  ok "Main SmartDocs Python: $PY (v$PYVER)"
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

# --- Dependencies (main SmartDocs venv) -------------------------------------
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
  # Pillow version — MUST stay 10.2.0 in the main venv for VietOCR. GLM's
  # Pillow 12.x lives ONLY in GLM-OCR/.venv-sdk (isolated), so no conflict.
  MAIN_PIL="$("$PY" -c 'import PIL; print(PIL.__version__)' 2>/dev/null || echo 'not installed')"
  ok "Main Pillow version  : $MAIN_PIL"
  # VietOCR import — the engine that pins Pillow==10.2.0.
  if "$PY" -c 'import vietocr' >/dev/null 2>&1; then
    ok "VietOCR import       : OK"
  else
    info "VietOCR import       : not available (run scripts/setup.sh)"
  fi
fi

# --- Web port + health ------------------------------------------------------
hr
if port_in_use "$SMARTDOCS_PORT"; then
  ok "Web port $SMARTDOCS_PORT: in use (SmartDocs likely running)"
else
  info "Web port $SMARTDOCS_PORT: free (SmartDocs not running)"
fi
if command -v curl >/dev/null 2>&1; then
  if smartdocs_health; then
    ok "SmartDocs health: responding on http://${SMARTDOCS_LOCAL_HOST}:${SMARTDOCS_PORT}/"
  else
    info "SmartDocs health: not responding (start it with scripts/start_web.sh)"
  fi
else
  warn "curl not found — skipping HTTP health checks."
fi

# --- GLM (optional) ---------------------------------------------------------
# Two independent venvs (see scripts/setup_glm.sh):
#   .venv-mlx = MLX model server (mlx_vlm/mlx_lm)   — NO torch, NO glmocr
#   .venv-sdk = glmocr CLI / layout detector        — torch + glmocr (UI uses this)
hr
info "GLM OCR (optional):"
echo "    GLM_OCR_DIR      : $GLM_OCR_DIR"
if [ -d "$GLM_OCR_DIR" ]; then
  ok  "GLM-OCR dir exists   : yes ($( [ -f "$GLM_OCR_DIR/pyproject.toml" ] && echo 'vendored SDK present' || echo 'dir present'))"
else
  warn "GLM-OCR dir exists   : NO — run scripts/setup_glm.sh or set GLM_OCR_DIR"
fi

# ── .venv-mlx (MLX model server) ──
MLX_PY="$GLM_OCR_DIR/.venv-mlx/bin/python"
if [ -x "$MLX_PY" ]; then
  MLX_VER="$("$MLX_PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo '?')"
  ok  ".venv-mlx python     : $MLX_PY (v$MLX_VER)"
  if "$MLX_PY" -c "import mlx_vlm, mlx_lm, transformers" >/dev/null 2>&1; then
    ok  ".venv-mlx imports    : OK (mlx_vlm, mlx_lm, transformers)"
  else
    info ".venv-mlx imports    : not available (Apple-Silicon only, or re-run scripts/setup_glm.sh)"
  fi
else
  info ".venv-mlx python     : missing ($MLX_PY) — create with scripts/setup_glm.sh"
fi

# ── .venv-sdk (glmocr CLI / layout — the venv the UI actually uses) ──
SDK_PY="$GLM_OCR_DIR/.venv-sdk/bin/python"
if [ -x "$SDK_PY" ]; then
  SDK_VER="$("$SDK_PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo '?')"
  ok  ".venv-sdk python     : $SDK_PY (v$SDK_VER)"
  if "$SDK_PY" -c "import torch; import glmocr; from glmocr.layout.layout_detector import PPDocLayoutDetector" >/dev/null 2>&1; then
    ok  ".venv-sdk imports    : OK (torch, glmocr, PPDocLayoutDetector)"
  else
    warn ".venv-sdk imports    : FAILED — run scripts/setup_glm.sh"
    "$SDK_PY" -c "import torch; import glmocr; from glmocr.layout.layout_detector import PPDocLayoutDetector" 2>&1 | tail -3 | sed 's/^/         ↳ /' >&2
    FAIL=1
  fi
else
  warn ".venv-sdk python     : MISSING ($SDK_PY) — GLM OCR from the UI will fail; run scripts/setup_glm.sh"
fi

if port_in_use "$GLM_PORT"; then
  ok  "GLM port $GLM_PORT       : in use"
else
  info "GLM port $GLM_PORT       : free (server not running — optional)"
fi

if command -v curl >/dev/null 2>&1; then
  if [ "$ENABLE_GLM" = "true" ]; then
    if glm_health; then
      ok  "GLM health           : 200 on ${GLM_OCR_API_URL} (model: ${GLM_MODEL})"
    else
      info "GLM health           : not responding on ${GLM_OCR_API_URL} (start: scripts/start_glm.sh -b)"
    fi
  else
    info "GLM health           : skipped (ENABLE_GLM=false) — Legacy/VietOCR/Modern OCR still work."
  fi
fi

hr
if [ "$FAIL" -eq 0 ]; then
  ok "Core environment looks good."
else
  err "One or more core checks failed (see above)."
fi
exit "$FAIL"
