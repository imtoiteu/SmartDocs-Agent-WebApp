#!/usr/bin/env bash
# ============================================================================
#  scripts/setup_glm.sh — create the TWO repo-local GLM venvs (reproducible).
#
#  GLM-OCR is an OPTIONAL, third-party OCR engine vendored inside this repo at
#  <repo>/GLM-OCR. It needs TWO independent venvs (this is the original design;
#  keeping them separate avoids the VietOCR Pillow conflict):
#
#    A. GLM-OCR/.venv-mlx  — the MLX MODEL SERVER only (mlx_vlm/mlx_lm).
#         Reproduced from requirements/glm-mlx-lock.txt. NO torch, NO glmocr.
#
#    B. GLM-OCR/.venv-sdk  — the glmocr CLI / layout detector that the SmartDocs
#         UI drives as a SUBPROCESS (services/ocr_engines/glm_adapter.py runs
#         `GLM_SDK_PYTHON -m glmocr.cli parse ...`; config.py resolves
#         GLM_SDK_PYTHON to .venv-sdk first). Reproduced from
#         requirements/glm-sdk-lock.txt + an editable install of glmocr. Holds
#         torch/torchvision/transformers and Pillow 12.x — ISOLATED from the
#         main SmartDocs venv, which keeps Pillow 10.2.0 for VietOCR.
#
#  Neither venv touches the main SmartDocs venv. GLM_OCR_DIR defaults to
#  <repo>/GLM-OCR; override via GLM_OCR_DIR in .env.
#
#  The mlx* wheels are Apple-Silicon only. On other hosts the venvs are still
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

info "GLM-OCR venv setup (.venv-mlx server + .venv-sdk CLI)"
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
  warn "The venvs are still created so paths resolve, but the MLX install + verify"
  warn "will not succeed. Run this on an Apple-Silicon Mac to use GLM end-to-end."
fi

# --- 3. Select a supported Python interpreter (3.10 / 3.11 / 3.12) ----------
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
  err "No supported Python found. GLM venvs need Python 3.10, 3.11 or 3.12."
  err "Install one (e.g. 'brew install python@3.12'), or point GLM_SETUP_PYTHON at it."
  err "To use 3.13/3.14 anyway (unsupported): FORCE_GLM_PY=1 scripts/setup_glm.sh"
  exit 1
fi
ok "Using Python: $PY_BOOT ($("$PY_BOOT" -V 2>&1))"

# ============================================================================
#  A. GLM-OCR/.venv-mlx — MLX model server only
# ============================================================================
hr
info "[A] MLX server venv → $GLM_OCR_DIR/.venv-mlx"
MLX_VENV="$GLM_OCR_DIR/.venv-mlx"
if [ -x "$MLX_VENV/bin/python" ]; then
  ok "MLX venv already exists: $MLX_VENV"
else
  info "Creating MLX venv…"
  "$PY_BOOT" -m venv "$MLX_VENV"
  ok "Created $MLX_VENV"
fi
MLX_PY="$MLX_VENV/bin/python"
"$MLX_PY" -m pip install --upgrade pip >/dev/null

MLX_LOCK="$REPO_ROOT/requirements/glm-mlx-lock.txt"
if [ -f "$MLX_LOCK" ]; then
  info "Installing MLX server from lock: requirements/glm-mlx-lock.txt"
  if "$MLX_PY" -m pip install -r "$MLX_LOCK"; then
    ok "MLX lock installed"
  else
    err "MLX lock install failed."
    [ "$IS_APPLE_SILICON" -eq 1 ] || err "(expected off Apple Silicon — mlx* wheels are macOS/arm64 only)"
  fi
else
  warn "requirements/glm-mlx-lock.txt not found — installing mlx-vlm directly."
  [ "$IS_APPLE_SILICON" -eq 1 ] && "$MLX_PY" -m pip install mlx-vlm || true
fi

info "Verifying MLX imports…"
if "$MLX_PY" -c "import mlx_vlm, mlx_lm, transformers; print('GLM MLX imports OK')"; then
  ok "MLX imports verified"
elif [ "$IS_APPLE_SILICON" -eq 1 ]; then
  err "MLX imports failed on Apple Silicon — check the install output above."
else
  warn "MLX imports unavailable (expected off Apple Silicon)."
fi

# ============================================================================
#  B. GLM-OCR/.venv-sdk — glmocr CLI / layout detector (torch, Pillow 12.x)
# ============================================================================
hr
info "[B] SDK/CLI venv → $GLM_OCR_DIR/.venv-sdk"
SDK_VENV="$GLM_OCR_DIR/.venv-sdk"
if [ -x "$SDK_VENV/bin/python" ]; then
  ok "SDK venv already exists: $SDK_VENV"
else
  info "Creating SDK venv…"
  "$PY_BOOT" -m venv "$SDK_VENV"
  ok "Created $SDK_VENV"
fi
SDK_PY="$SDK_VENV/bin/python"
"$SDK_PY" -m pip install --upgrade pip >/dev/null

SDK_LOCK="$REPO_ROOT/requirements/glm-sdk-lock.txt"
if [ -f "$SDK_LOCK" ]; then
  info "Installing GLM SDK deps from lock: requirements/glm-sdk-lock.txt"
  if "$SDK_PY" -m pip install -r "$SDK_LOCK"; then
    ok "GLM SDK lock installed"
  else
    warn "SDK lock install failed — falling back to editable install with [layout] extra."
    "$SDK_PY" -m pip install -e "${GLM_OCR_DIR}[layout]"
  fi
else
  info "requirements/glm-sdk-lock.txt not found — installing glmocr[layout] (editable)…"
  if ! "$SDK_PY" -m pip install -e "${GLM_OCR_DIR}[layout]"; then
    err "glmocr[layout] install failed."
    exit 1
  fi
fi

# Install the glmocr package itself (editable) if not already importable. When
# the SDK lock was used, only the deps are present — this adds the package with
# no extra deps. Editable so the vendored GLM-OCR/glmocr is the live source.
if ! "$SDK_PY" -c "import glmocr" >/dev/null 2>&1; then
  info "Installing glmocr package (editable, --no-deps) into SDK venv…"
  "$SDK_PY" -m pip install -e "${GLM_OCR_DIR}" --no-deps
  ok "glmocr editable installed"
fi

info "Verifying SDK imports (torch + glmocr + layout_detector)…"
if "$SDK_PY" -c "
import torch
import glmocr
from glmocr.layout.layout_detector import PPDocLayoutDetector
print('GLM SDK imports OK')
"; then
  ok "GLM SDK imports verified"
else
  warn "GLM SDK import check failed — layout detection may not work. Details:"
  "$SDK_PY" -c "
import torch
import glmocr
from glmocr.layout.layout_detector import PPDocLayoutDetector
" 2>&1 | tail -5 | sed 's/^/         /' >&2
fi

# ============================================================================
#  Selfhosted config for the glmocr CLI (points at the local MLX server)
# ============================================================================
#  glmocr self-hosted mode REQUIRES pipeline.layout.model_dir — without it the
#  CLI aborts with "pipeline.layout.model_dir is required for self-hosted layout
#  detection". We therefore always ensure that key is present. A config that
#  predates this fix (has no model_dir) is regenerated; the old one is backed up.
# ============================================================================
hr
CFG="$GLM_OCR_DIR/mlx_config.yaml"
write_glm_config() {
  cat > "$CFG" <<YAML
# Generated by scripts/setup_glm.sh — selfhosted MLX mode.
# Points the glmocr SDK at the local MLX model server (scripts/start_glm.sh)
# and at the PP-DocLayout checkpoint used for self-hosted layout detection.
pipeline:
  maas:
    enabled: false
  ocr_api:
    api_host: ${GLM_HOST}
    api_port: ${GLM_PORT}
    model: ${GLM_MODEL}
    api_mode: openai
    verify_ssl: false
  layout:
    # Hugging Face id (default) or an absolute local checkpoint directory.
    # Override with GLM_LAYOUT_MODEL_DIR in .env. Pre-cache it while online with
    # 'scripts/setup_glm.sh --precache-layout' so runtime can stay offline.
    model_dir: ${GLM_LAYOUT_MODEL_DIR}
    device: cpu
YAML
}
if [ ! -f "$CFG" ]; then
  info "Writing selfhosted config: $CFG"
  write_glm_config
  ok "Wrote $CFG"
elif grep -q 'model_dir' "$CFG"; then
  ok "Config already present with layout.model_dir: $CFG (left untouched)"
else
  warn "Existing config lacks pipeline.layout.model_dir — regenerating (backup: $CFG.bak)"
  cp "$CFG" "$CFG.bak"
  write_glm_config
  ok "Rewrote $CFG (layout.model_dir=${GLM_LAYOUT_MODEL_DIR})"
fi

# ============================================================================
#  Optional: pre-cache the layout model into the DEFAULT HF cache.
#  glm_adapter.py strips HF_HOME before shelling out to glmocr, so the layout
#  model MUST live in ~/.cache/huggingface (NOT models/huggingface/). Run while
#  online; afterwards runtime works with HF_HUB_OFFLINE=1.
#  Triggered by: scripts/setup_glm.sh --precache-layout   (skipped by default).
# ============================================================================
PRECACHE_LAYOUT=0
for a in "$@"; do case "$a" in --precache-layout) PRECACHE_LAYOUT=1 ;; esac; done
if [ "$PRECACHE_LAYOUT" = "1" ]; then
  hr
  case "$GLM_LAYOUT_MODEL_DIR" in
    */*) ;;  # looks like an HF id (org/name) — proceed
    *)   warn "GLM_LAYOUT_MODEL_DIR ($GLM_LAYOUT_MODEL_DIR) is not an HF id — skipping pre-cache."
         PRECACHE_LAYOUT=0 ;;
  esac
fi
if [ "$PRECACHE_LAYOUT" = "1" ] && [ -d "$GLM_LAYOUT_MODEL_DIR" ]; then
  ok "Layout model_dir is a local directory — nothing to download."
elif [ "$PRECACHE_LAYOUT" = "1" ]; then
  info "Pre-caching layout model into the DEFAULT HF cache: $GLM_LAYOUT_MODEL_DIR"
  # Download with HF_* redirects stripped so it lands in ~/.cache/huggingface,
  # exactly where the adapter (offline) will look for it.
  env -u HF_HOME -u HF_HUB_CACHE -u TRANSFORMERS_CACHE -u HF_DATASETS_CACHE \
      HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 \
      "$SDK_PY" -c "
import sys
try:
    from huggingface_hub import snapshot_download
except Exception as e:
    print('huggingface_hub not available in .venv-sdk:', e); sys.exit(1)
p = snapshot_download('${GLM_LAYOUT_MODEL_DIR}')
print('Layout model cached at:', p)
" && ok "Layout model pre-cached" || warn "Layout pre-cache failed (need internet; retried at first online OCR run)."
fi

hr
ok "GLM setup complete."
echo
echo "  .venv-mlx : $MLX_PY   (MLX server)"
echo "  .venv-sdk : $SDK_PY   (glmocr CLI — what the UI uses)"
echo
echo "Next:"
echo "  scripts/check.sh          # verify both venvs' imports, paths, health"
echo "  scripts/start_glm.sh -b   # start the GLM model server (Apple Silicon)"
echo "  scripts/start.sh          # full stack (starts GLM if ENABLE_GLM=true)"
