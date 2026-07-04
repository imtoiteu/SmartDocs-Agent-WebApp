#!/usr/bin/env bash
# ============================================================================
#  scripts/lib.sh — shared helpers for the SmartDocs-Agent local runtime.
#
#  This file is SOURCED by the other scripts (setup / start_* / stop / check).
#  It never runs anything on its own; it only defines variables + functions.
#
#  Responsibilities:
#    * resolve the repository root robustly (independent of the caller's CWD)
#    * load .env and normalise the friendly runtime variables into the exact
#      names the app + GLM server already read:
#          SMARTDOCS_PORT  ->  PORT              (read by config.py / app.py)
#          GLM_HOST/GLM_PORT ->  GLM_OCR_API_URL (read by config.py / adapter)
#          GLM_PORT         ->  exported for tools/glm_serve.sh
#      => no Python/business-logic changes are required.
#    * locate a usable Python interpreter (repo .venv, parent .venv, or system)
#    * small port / HTTP health helpers used by start.sh / check.sh
#
#  Compatible with the stock macOS Bash 3.2 (no bash-4-only features).
# ============================================================================

# --- Repo layout ------------------------------------------------------------
# lib.sh lives in <repo>/scripts, so the repo root is one level up. Resolve via
# the classic cd/pwd trick (portable; no `readlink -f`, which macOS lacks).
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$LIB_DIR/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs"

# --- Pretty output ----------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET='\033[0m'; C_DIM='\033[2m'; C_RED='\033[31m'
  C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_BLUE='\033[34m'; C_BOLD='\033[1m'
else
  C_RESET=''; C_DIM=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_BOLD=''
fi

info()  { printf "${C_BLUE}==>${C_RESET} %s\n" "$*"; }
ok()    { printf "${C_GREEN}[ok]${C_RESET}  %s\n" "$*"; }
warn()  { printf "${C_YELLOW}[warn]${C_RESET} %s\n" "$*" >&2; }
err()   { printf "${C_RED}[err]${C_RESET}  %s\n" "$*" >&2; }
hr()    { printf "${C_DIM}%s${C_RESET}\n" "------------------------------------------------------------"; }

# --- .env loading -----------------------------------------------------------
# Same mechanism the existing tools/glm_serve.sh already uses: export every
# assignment found in .env. Safe because .env is a private, trusted file.
load_env() {
  if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$REPO_ROOT/.env"
    set +a
  fi
}

# --- Normalise the friendly runtime variables -------------------------------
# Fills in defaults and maps the operator-facing names onto the exact env vars
# the Python app and the GLM server already consume. Call AFTER load_env.
normalize_env() {
  # Web port: SMARTDOCS_PORT is the operator-facing name; the app reads PORT.
  # Precedence: an explicit PORT wins (back-compat with existing .env files),
  # otherwise SMARTDOCS_PORT, otherwise the project default 5002.
  if [ -n "${PORT:-}" ]; then
    SMARTDOCS_PORT="${SMARTDOCS_PORT:-$PORT}"
  else
    SMARTDOCS_PORT="${SMARTDOCS_PORT:-5002}"
    PORT="$SMARTDOCS_PORT"
  fi
  export PORT SMARTDOCS_PORT

  HOST="${HOST:-0.0.0.0}"
  export HOST
  # Host used for *local* health probes / browser URL (0.0.0.0 isn't dialable).
  SMARTDOCS_LOCAL_HOST="127.0.0.1"
  case "$HOST" in
    0.0.0.0|"") SMARTDOCS_LOCAL_HOST="127.0.0.1" ;;
    *)          SMARTDOCS_LOCAL_HOST="$HOST" ;;
  esac

  # GLM server: derive GLM_OCR_API_URL (what the adapter reads) from GLM_HOST /
  # GLM_PORT unless the operator pinned a full URL explicitly.
  GLM_HOST="${GLM_HOST:-localhost}"
  GLM_PORT="${GLM_PORT:-8080}"
  GLM_OCR_API_URL="${GLM_OCR_API_URL:-http://${GLM_HOST}:${GLM_PORT}}"
  GLM_MODEL="${GLM_MODEL:-mlx-community/GLM-OCR-bf16}"
  # Layout model for GLM self-hosted mode (glmocr requires pipeline.layout.model_dir).
  # Default is a Hugging Face id (cached in the DEFAULT HF cache); may be an
  # absolute local checkpoint dir. setup_glm.sh writes this into mlx_config.yaml.
  GLM_LAYOUT_MODEL_DIR="${GLM_LAYOUT_MODEL_DIR:-PaddlePaddle/PP-DocLayoutV3_safetensors}"
  export GLM_HOST GLM_PORT GLM_OCR_API_URL GLM_MODEL GLM_LAYOUT_MODEL_DIR

  # GLM directory (clean-clone friendly): explicit GLM_OCR_DIR / legacy GLM_ROOT
  # wins; otherwise the vendored copy INSIDE this repo (<repo>/GLM-OCR).
  GLM_OCR_DIR="${GLM_OCR_DIR:-${GLM_ROOT:-$REPO_ROOT/GLM-OCR}}"
  GLM_ROOT="$GLM_OCR_DIR"
  export GLM_OCR_DIR GLM_ROOT

  # ENABLE_GLM: whether start.sh should try to launch the GLM server. Optional;
  # the app itself always runs without it. Normalise to lowercase true/false.
  ENABLE_GLM="${ENABLE_GLM:-true}"
  case "$(printf '%s' "$ENABLE_GLM" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)  ENABLE_GLM="true" ;;
    *)              ENABLE_GLM="false" ;;
  esac
  export ENABLE_GLM
}

# --- Python / venv resolution ----------------------------------------------
# Print the venv python if one exists, in priority order. Returns non-zero when
# no virtualenv is found (callers may then fall back to system python3).
#   1. $SMARTDOCS_PYTHON override
#   2. <repo>/.venv                 (a venv created inside this project)
#   3. <repo>/../.venv              (OCRSoftware/.venv — the MacBook layout)
venv_python() {
  if [ -n "${SMARTDOCS_PYTHON:-}" ] && [ -x "${SMARTDOCS_PYTHON}" ]; then
    printf '%s\n' "$SMARTDOCS_PYTHON"; return 0
  fi
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    printf '%s\n' "$REPO_ROOT/.venv/bin/python"; return 0
  fi
  local parent_py; parent_py="$(cd "$REPO_ROOT/.." && pwd)/.venv/bin/python"
  if [ -x "$parent_py" ]; then
    printf '%s\n' "$parent_py"; return 0
  fi
  return 1
}

# Print a python to RUN the app with: the venv python if available, else a
# system python3/python. Returns non-zero if nothing is found.
resolve_python() {
  local p
  if p="$(venv_python)"; then printf '%s\n' "$p"; return 0; fi
  if command -v python3 >/dev/null 2>&1; then command -v python3; return 0; fi
  if command -v python  >/dev/null 2>&1; then command -v python;  return 0; fi
  return 1
}

# --- GLM interpreter resolution ---------------------------------------------
# Resolve the GLM python the SAME way config.py / tools/glm_serve.sh do, so the
# scripts' "is GLM available?" checks match what actually launches. Repo-local
# by default; an explicit env var points elsewhere. Requires normalize_env to
# have set GLM_OCR_DIR. Prints the interpreter path (exists+executable) or
# returns non-zero. Candidate order prefers .venv-mlx (server), then .venv-sdk.
glm_python() {
  local candidates=()
  [ -n "${GLM_MLX_PYTHON:-}" ] && candidates+=("$GLM_MLX_PYTHON")
  [ -n "${GLM_SDK_PYTHON:-}" ] && candidates+=("$GLM_SDK_PYTHON")
  candidates+=("${GLM_OCR_DIR:-$REPO_ROOT/GLM-OCR}/.venv-mlx/bin/python")
  candidates+=("${GLM_OCR_DIR:-$REPO_ROOT/GLM-OCR}/.venv-sdk/bin/python")
  local c
  for c in "${candidates[@]}"; do
    if [ -n "$c" ] && [ -x "$c" ]; then printf '%s\n' "$c"; return 0; fi
  done
  return 1
}

# Back-compat alias used by start.sh.
glm_mlx_python() { glm_python; }

# Print the path where the repo-local GLM venv is expected (whether or not it
# exists) — used by diagnostics / setup messaging.
glm_venv_dir() { printf '%s\n' "${GLM_OCR_DIR:-$REPO_ROOT/GLM-OCR}/.venv-mlx"; }

# --- Port + HTTP helpers ----------------------------------------------------
# True (0) when something is listening on 127.0.0.1:$1. Uses bash /dev/tcp so it
# needs no lsof/nc (both of which may be absent).
port_in_use() {
  local port="$1"
  ( exec 3<>"/dev/tcp/127.0.0.1/${port}" ) >/dev/null 2>&1
}

# Echo the HTTP status code for a GET (or "000" if unreachable). Needs curl.
http_status() {
  local url="$1"; shift || true
  curl -s -o /dev/null -m "${HEALTH_TIMEOUT:-5}" -w "%{http_code}" "$@" "$url" 2>/dev/null || echo "000"
}

# GLM health probe — mirrors RUN_CONTEXT_FOR_CLAUDE.md. Returns 0 iff HTTP 200.
glm_health() {
  local code
  code="$(curl -s -o /dev/null -m "${HEALTH_TIMEOUT:-8}" -w "%{http_code}" \
    "${GLM_OCR_API_URL}/chat/completions" -X POST \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${GLM_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"hi\"}]}],\"max_tokens\":3}" \
    2>/dev/null)"
  [ "$code" = "200" ]
}

# SmartDocs health — any HTTP response (200/302/401/403…) means the server is up.
smartdocs_health() {
  local code
  code="$(http_status "http://${SMARTDOCS_LOCAL_HOST}:${SMARTDOCS_PORT}/")"
  case "$code" in 000|"") return 1 ;; *) return 0 ;; esac
}

# --- PID file helpers -------------------------------------------------------
WEB_PID_FILE="$LOG_DIR/web.pid"
GLM_PID_FILE="$LOG_DIR/glm.pid"

pid_alive()  { [ -n "${1:-}" ] && kill -0 "$1" >/dev/null 2>&1; }

read_pid() { [ -f "$1" ] && cat "$1" 2>/dev/null || true; }

ensure_dirs() { mkdir -p "$LOG_DIR"; }
