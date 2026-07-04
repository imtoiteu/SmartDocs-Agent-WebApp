#!/usr/bin/env bash
# ============================================================================
#  scripts/start_glm.sh — start ONLY the GLM-OCR MLX model server.
#
#  Thin, robust wrapper around the existing tools/glm_serve.sh (which is the
#  verified-working launch command on the MacBook). This script just resolves
#  paths, loads .env, and passes GLM_PORT through — it does NOT change how the
#  server is invoked.
#
#  GLM-OCR is OPTIONAL and Apple-Silicon / MLX only. If the MLX venv is not
#  present (e.g. on the VPS or a non-Mac host) this exits with a clear message;
#  the SmartDocs web app still runs fine without it — only the GLM OCR engine
#  is unavailable.
#
#  Usage:
#    scripts/start_glm.sh          # run in the foreground (Ctrl-C to stop)
#    scripts/start_glm.sh -b       # run in the background (logs/glm.log, PID file)
# ============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

load_env
normalize_env
ensure_dirs

BACKGROUND=0
case "${1:-}" in -b|--background) BACKGROUND=1 ;; esac

GLM_SERVE="$REPO_ROOT/tools/glm_serve.sh"
if [ ! -x "$GLM_SERVE" ]; then
  err "tools/glm_serve.sh not found or not executable at $GLM_SERVE"
  exit 1
fi

if port_in_use "$GLM_PORT"; then
  warn "Port $GLM_PORT already in use — the GLM server may already be running."
  if glm_health; then
    ok "GLM server is already up and healthy on $GLM_OCR_API_URL"
    exit 0
  fi
  err "Something is on port $GLM_PORT but not answering as GLM. Free it or set GLM_PORT."
  exit 1
fi

info "Starting GLM-OCR MLX server"
info "  port  : $GLM_PORT"
info "  model : $GLM_MODEL"
info "  serve : $GLM_SERVE"

# GLM_PORT is exported (normalize_env); tools/glm_serve.sh reads it from the env.
if [ "$BACKGROUND" -eq 1 ]; then
  nohup "$GLM_SERVE" >>"$LOG_DIR/glm.log" 2>&1 &
  echo $! > "$GLM_PID_FILE"
  ok "GLM server starting in background (PID $(cat "$GLM_PID_FILE")) — logs: logs/glm.log"
  info "It may take a while to load the model. Check with: scripts/check.sh"
else
  exec "$GLM_SERVE"
fi
