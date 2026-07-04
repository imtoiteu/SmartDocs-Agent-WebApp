#!/usr/bin/env bash
# ============================================================================
#  scripts/setup_glm.sh — create the REPO-LOCAL GLM MLX server venv (reproducible).
#
#  GLM-OCR is an OPTIONAL, third-party OCR engine vendored inside this repo at
#  <repo>/GLM-OCR. This script prepares the MLX MODEL-SERVER venv without
#  hardcoding any machine-specific path:
#
#    * selects a Python 3.10 / 3.11 / 3.12 interpreter (rejects 3.13/3.14 unless
#      forced) — the known-good MLX stack is built for 3.12
#    * creates the venv  <GLM_OCR_DIR>/.venv-mlx  (GLM_OCR_DIR defaults to
#      <repo>/GLM-OCR; override via GLM_OCR_DIR in .env)
#    * installs a reproducible env from requirements/glm-mlx-lock.txt (known-good
#      freeze). If the lock is absent, falls back to the GLM-OCR requirements.
#    * also installs requirements/glm-sdk.txt (light pure-python SDK deps)
#    * verifies:  import mlx_vlm, mlx_lm, transformers
#    * generates a selfhosted <GLM_OCR_DIR>/mlx_config.yaml if none exists
#
#  The mlx* wheels are Apple-Silicon only. On other hosts the venv is still
#  created (so paths resolve), but the MLX install/verify cannot succeed — that
#  is fine: GLM stays optional and the rest of SmartDocs is unaffected.
#
#  Env:
#    GLM_SETUP_PYTHON=/path/to/python3.12   # pin the interpreter explicitly
#    FORCE_GLM_PY=1                         # allow Python 3.13/3.14 anyway
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env
ensure_dirs

FORCE_GLM_PY="${FORCE_GLM_PY:-0}"
case "${1:-}" in -f|--force) FORCE_GLM_PY=1 ;; esac

info "GLM-OCR MLX server setup"
hr
info "Repo root   : $REPO_ROOT"
info "GLM_OCR_DIR : $GLM_OCR_DIR"

# --- 1. Sanity: the vendored GLM-OCR code must be present -------------------
if [ ! -f "$GLM_OCR_DIR/pyproject.toml" ] && [ ! -d "$GLM_OCR_DIR/glmocr" ]; then
  err "No GLM-OCR project found at $GLM_OCR_DIR"
  err "Expected the vendored copy at <repo>/GLM-OCR, or set GLM_OCR_DIR in .env."
  exit 1
fi

# --- 2. Platform note (Apple Silicon required for the MLX server) -----------
IS_APPLE_SILICON=0
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
  IS_APPLE_SILICON=1
else
  warn "Host is not Apple Silicon — the MLX server (mlx-vlm/mlx-lm) cannot run here."
  warn "The venv is still created so paths resolve, but the MLX install + verify"
  warn "will not succeed. Run this on an Apple-Silicon Mac to use GLM end-to-end."
fi

# --- 3. Select a supported Python interpreter (3.10 / 3.11 / 3.12) ----------
# Returns the interpreter path via stdout; enforces the version policy.
pick_python() {
  local cands=()
  [ -n "${GLM_SETUP_PYTHON:-}" ] && cands+=("$GLM_SETUP_PYTHON")
  cands+=(python3.12 python3.11 python3.10 python3)
  local c ver major minor
  for c in "${cands[@]}"; do
    command -v "$c" >/dev/null 2>&1 || continue
    ver="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)" || continue
    major="${ver%%.*}"; minor="${ver##*.}"
    [ "$major" = "3" ] || continue
    if [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
      printf '%s\n' "$c"; return 0
    fi
  done
  # Nothing in the 3.10–3.12 window. Honour an explicit force.
  if [ "$FORCE_GLM_PY" = "1" ]; then
    for c in "${cands[@]}"; do
      command -v "$c" >/dev/null 2>&1 || continue
      warn "Forcing unsupported Python: $("$c" -V 2>&1) (FORCE_GLM_PY=1)"
      printf '%s\n' "$c"; return 0
    done
  fi
  return 1
}

if ! PY_BOOT="$(pick_python)"; then
  err "No supported Python found. GLM MLX needs Python 3.10, 3.11 or 3.12."
  err "Install one (e.g. 'brew install python@3.12'), or point GLM_SETUP_PYTHON at it."
  err "To use 3.13/3.14 anyway (unsupported): FORCE_GLM_PY=1 scripts/setup_glm.sh"
  exit 1
fi
ok "Using Python: $PY_BOOT ($("$PY_BOOT" -V 2>&1))"

# --- 4. Create the venv -----------------------------------------------------
VENV="$GLM_OCR_DIR/.venv-mlx"
if [ -x "$VENV/bin/python" ]; then
  ok "GLM venv already exists: $VENV"
else
  info "Creating GLM venv: $VENV"
  "$PY_BOOT" -m venv "$VENV"
  ok "Created $VENV"
fi
GLM_PY="$VENV/bin/python"

info "Upgrading pip…"
"$GLM_PY" -m pip install --upgrade pip >/dev/null

# --- 5. Install the MLX server env (reproducible) ---------------------------
MLX_LOCK="$REPO_ROOT/requirements/glm-mlx-lock.txt"
if [ -f "$MLX_LOCK" ]; then
  info "Installing MLX server from lock: requirements/glm-mlx-lock.txt"
  if "$GLM_PY" -m pip install -r "$MLX_LOCK"; then
    ok "MLX lock installed"
  else
    err "MLX lock install failed."
    [ "$IS_APPLE_SILICON" -eq 1 ] || err "(expected off Apple Silicon — mlx* wheels are macOS/arm64 only)"
    exit 1
  fi
else
  warn "requirements/glm-mlx-lock.txt not found — falling back to GLM-OCR requirements."
  info "Installing glmocr[selfhosted] + mlx-vlm…"
  "$GLM_PY" -m pip install "${GLM_OCR_DIR}[selfhosted]"
  if [ "$IS_APPLE_SILICON" -eq 1 ]; then
    "$GLM_PY" -m pip install mlx-vlm || warn "mlx-vlm install failed — retry manually."
  fi
fi

# --- 6. Also install the light SDK deps (harmless in this venv) -------------
GLM_SDK_REQ="$REPO_ROOT/requirements/glm-sdk.txt"
if [ -f "$GLM_SDK_REQ" ]; then
  info "Installing GLM SDK deps (requirements/glm-sdk.txt)…"
  "$GLM_PY" -m pip install -r "$GLM_SDK_REQ" && ok "GLM SDK deps installed"
fi

# --- 7. Verify the MLX imports ---------------------------------------------
info "Verifying MLX imports…"
if "$GLM_PY" -c "import mlx_vlm, mlx_lm, transformers; print('GLM MLX imports OK')"; then
  ok "MLX imports verified"
elif [ "$IS_APPLE_SILICON" -eq 1 ]; then
  err "MLX imports failed on Apple Silicon — check the install output above."
  exit 1
else
  warn "MLX imports unavailable (expected off Apple Silicon)."
fi

# --- 8. Generate a selfhosted config if none exists ------------------------
CFG="$GLM_OCR_DIR/mlx_config.yaml"
if [ -f "$CFG" ]; then
  ok "Config already present: $CFG (left untouched)"
else
  info "Writing selfhosted config: $CFG"
  cat > "$CFG" <<YAML
# Generated by scripts/setup_glm.sh — selfhosted MLX mode.
# Points the glmocr SDK at the local MLX model server (scripts/start_glm.sh).
pipeline:
  maas:
    enabled: false
  ocr_api:
    api_host: ${GLM_HOST}
    api_port: ${GLM_PORT}
    model: ${GLM_MODEL}
    api_mode: openai
    verify_ssl: false
YAML
  ok "Wrote $CFG"
fi

hr
ok "GLM setup complete."
echo
echo "Detected GLM python : $(glm_python 2>/dev/null || echo "$GLM_PY")"
echo
echo "Next:"
echo "  scripts/check.sh          # verify GLM SDK + MLX imports, paths, health"
echo "  scripts/start_glm.sh -b   # start the GLM model server (Apple Silicon)"
echo "  scripts/start.sh          # full stack (starts GLM if ENABLE_GLM=true)"
