#!/usr/bin/env bash
# ============================================================================
#  scripts/start.sh — start the full local stack.
#
#  Behaviour:
#    * If ENABLE_GLM=true AND the GLM MLX venv is available, start the GLM
#      server in the BACKGROUND first (logs/glm.log). If it can't start
#      (not Apple Silicon, MLX venv missing, port busy), print a clear warning
#      and CONTINUE — the app runs fine without GLM; only the GLM OCR engine
#      is affected.
#    * Then start the web app in the FOREGROUND. Ctrl-C stops the web app and
#      (if we started it) the GLM server too.
#
#  Usage:
#    scripts/start.sh              # GLM (if enabled) + web app
#    ENABLE_GLM=false scripts/start.sh   # web app only, no GLM attempt
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env
ensure_dirs

STARTED_GLM=0

cleanup() {
  if [ "$STARTED_GLM" -eq 1 ]; then
    local gpid; gpid="$(read_pid "$GLM_PID_FILE")"
    if pid_alive "$gpid"; then
      info "Stopping GLM server (PID $gpid)…"
      kill "$gpid" >/dev/null 2>&1 || true
    fi
    rm -f "$GLM_PID_FILE"
  fi
}
trap cleanup EXIT INT TERM

info "SmartDocs-Agent — full local stack"
hr

# --- GLM (optional) ---------------------------------------------------------
if [ "$ENABLE_GLM" = "true" ]; then
  GLM_STATE="$(glm_ready_state)"
  case "$GLM_STATE" in
    ready:*)
      ok "GLM server already running (model loaded) on $GLM_OCR_API_URL — reusing it" ;;
    loading|no-model)
      ok "GLM server already up on $GLM_OCR_API_URL — model still loading; reusing it (watch logs/glm.log)" ;;
    unknown)
      warn "Port $GLM_PORT busy but not answering like the GLM server — skipping GLM startup" ;;
    down)
      if glm_mlx_python >/dev/null 2>&1; then
        info "Starting GLM server in background…"
        # Short readiness wait: the web app does not need GLM, so don't hold the
        # whole stack for a long model load — start_glm.sh reports "still
        # loading" and scripts/check.sh shows the live state afterwards.
        if GLM_START_WAIT="${GLM_START_WAIT:-15}" "$DIR/start_glm.sh" -b; then
          STARTED_GLM=1
        else
          warn "GLM server failed to start — continuing without it (GLM OCR engine will be unavailable)."
        fi
      else
        warn "GLM MLX venv not found — skipping GLM (Apple-Silicon/MLX only)."
        warn "The web app and Legacy/VietOCR/Modern OCR engines will work normally."
      fi ;;
  esac
else
  info "ENABLE_GLM=false — not starting the GLM server."
fi

# --- Web app (foreground) ---------------------------------------------------
hr
# Runs in the foreground; when it exits, the EXIT trap tears down GLM.
"$DIR/start_web.sh"
