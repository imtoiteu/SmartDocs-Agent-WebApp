#!/usr/bin/env bash
# ============================================================================
#  scripts/check_offline.sh — comprehensive OFFLINE / clean-clone readiness.
#
#  Read-only. Reports, for a fresh clone, whether every AI feature is usable
#  now, needs a one-time online setup, or is running on a built-in fallback:
#
#    * main SmartDocs Python path/version + Pillow version + VietOCR import
#    * VietOCR config.yml + weights           (models/vietocr/)
#    * Paddle det/rec cache                    (first-run download otherwise)
#    * Local LLM (chat/rewrite/agent)          (Qwen2.5-1.5B-Instruct REQUIRED;
#                                               a complete HF snapshot, not a
#                                               half-download — 3B is NOT required)
#    * PhoBERT + embeddings                    (fallbacks exist if missing)
#    * Argos offline translation packages      (installed language pairs listed)
#    * GLM .venv-mlx / .venv-sdk               (imports)
#    * GLM self-hosted config: pipeline.layout.model_dir present?
#    * GLM layout model cached in the DEFAULT HF cache?
#
#  The model matrix comes from config.cfg.offline_readiness_report() so the
#  script and the running app agree on exactly what "ready" means.
#
#  Exit code: 0 always for optional/fallback-capable features; non-zero only if
#  the interpreter or Flask itself is missing (a genuinely broken environment).
# ============================================================================
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env

FAIL=0

info "SmartDocs-Agent — OFFLINE readiness check"
hr
info "Repo root : $REPO_ROOT"

# --- Main Python + Pillow + VietOCR import ----------------------------------
if PY="$(resolve_python)"; then
  PYVER="$("$PY" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])' 2>/dev/null || echo '?')"
  ok "Main SmartDocs Python: $PY (v$PYVER)"
else
  err "No Python interpreter found. Run scripts/setup.sh."
  exit 1
fi
if ! "$PY" -c 'import flask' >/dev/null 2>&1; then
  err "Flask not importable — run scripts/setup.sh to install requirements.txt"
  exit 1
fi
MAIN_PIL="$("$PY" -c 'import PIL; print(PIL.__version__)' 2>/dev/null || echo 'not installed')"
ok "Main Pillow version  : $MAIN_PIL"
if "$PY" -c 'import vietocr' >/dev/null 2>&1; then
  ok "VietOCR import       : OK"
else
  warn "VietOCR import       : not available (run scripts/setup.sh)"
fi

# --- Model readiness matrix (single source of truth: config.py) -------------
hr
if ! ( cd "$REPO_ROOT" && "$PY" -c 'from config import cfg; print(cfg.offline_readiness_report())' 2>/dev/null ); then
  warn "Could not import the app config to compute model readiness."
  warn "(Needs the main venv deps installed — run scripts/setup.sh.)"
fi

# --- GLM venvs (optional, Apple Silicon) ------------------------------------
hr
info "GLM OCR (optional):"
echo "    GLM_OCR_DIR      : $GLM_OCR_DIR"
MLX_PY="$GLM_OCR_DIR/.venv-mlx/bin/python"
SDK_PY="$GLM_OCR_DIR/.venv-sdk/bin/python"
if [ -x "$MLX_PY" ]; then
  if "$MLX_PY" -c "import mlx_vlm, mlx_lm, transformers" >/dev/null 2>&1; then
    ok  ".venv-mlx imports    : OK (mlx_vlm, mlx_lm, transformers)"
  else
    info ".venv-mlx imports    : not available (Apple-Silicon only / re-run scripts/setup_glm.sh)"
  fi
else
  info ".venv-mlx python     : missing — create with scripts/setup_glm.sh"
fi
if [ -x "$SDK_PY" ]; then
  if "$SDK_PY" -c "import torch, glmocr; from glmocr.layout.layout_detector import PPDocLayoutDetector" >/dev/null 2>&1; then
    ok  ".venv-sdk imports    : OK (torch, glmocr, PPDocLayoutDetector)"
  else
    warn ".venv-sdk imports    : FAILED — run scripts/setup_glm.sh"
  fi
else
  info ".venv-sdk python     : missing — GLM OCR needs it; run scripts/setup_glm.sh"
fi

# --- GLM self-hosted config: the pipeline.layout.model_dir that broke OCR ----
GLM_CFG="${GLM_CONFIG_YAML:-$GLM_OCR_DIR/mlx_config.yaml}"
echo "    GLM config       : $GLM_CFG"
if [ -f "$GLM_CFG" ]; then
  if grep -Eq '^[[:space:]]*model_dir:[[:space:]]*[^[:space:]]' "$GLM_CFG"; then
    MDL_LINE="$(grep -E '^[[:space:]]*model_dir:' "$GLM_CFG" | head -1 | sed 's/^[[:space:]]*//')"
    ok  "GLM layout config    : OK ($MDL_LINE)"
  else
    warn "GLM layout config    : pipeline.layout.model_dir MISSING — re-run scripts/setup_glm.sh"
    warn "  (this is the 'pipeline.layout.model_dir is required' UI error)"
  fi
else
  info "GLM layout config    : $GLM_CFG not present (run scripts/setup_glm.sh)"
fi

# --- GLM layout model cache (DEFAULT HF cache, where the adapter looks) ------
DEF_HUB="${HOME}/.cache/huggingface/hub"
if compgen -G "$DEF_HUB/models--PaddlePaddle--PP-DocLayout*" >/dev/null 2>&1; then
  ok  "GLM layout model     : cached in $DEF_HUB"
else
  info "GLM layout model     : not cached — 'scripts/setup_glm.sh --precache-layout' (online), or first online OCR run"
fi

# --- GLM port + health ------------------------------------------------------
if port_in_use "$GLM_PORT"; then
  ok  "GLM port $GLM_PORT       : in use"
else
  info "GLM port $GLM_PORT       : free (server not running — optional)"
fi

hr
ok "Offline readiness report complete."
echo
echo "To make a clean clone fully offline-ready:"
echo "  python tools/setup_offline.py          # Qwen(chat+rewrite), PhoBERT, embeddings, Paddle, VietOCR(+config.yml), Argos"
echo "  scripts/setup_glm.sh --precache-layout  # (Apple Silicon) GLM venvs + layout model cache"
exit "$FAIL"
