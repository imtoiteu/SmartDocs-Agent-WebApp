#!/usr/bin/env bash
#
# glm_serve.sh — start the local GLM-OCR model server (MLX, Apple Silicon).
#
# GLM-OCR is a vision OCR model served as a long-lived, OpenAI-compatible HTTP
# server. SmartDocs' "GLM OCR" engine is a CLIENT of this server — it does NOT
# spawn it. Start this once (it holds the model resident between requests); the
# SmartDocs adapter health-checks the port and errors clearly if it is down.
#
# Usage:
#   tools/glm_serve.sh            # serve on :8080 (matches mlx_config.yaml)
#   GLM_PORT=9090 tools/glm_serve.sh
#
# Override paths with GLM_ROOT / GLM_MLX_PYTHON if your checkout differs.
set -euo pipefail

# SmartDocs-Agent root = one level up from tools/
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Load .env so GLM_ROOT / GLM_MLX_PYTHON set there are picked up automatically
if [[ -f "$AGENT_DIR/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$AGENT_DIR/.env"
  set +a
fi

# GLM_ROOT: prefer .env value → sibling GLM-OCR/GLM-OCR next to SmartDocs-Agent
GLM_ROOT="${GLM_ROOT:-$(cd "$AGENT_DIR/../GLM-OCR/GLM-OCR" 2>/dev/null && pwd || echo '')}"
GLM_MLX_PYTHON="${GLM_MLX_PYTHON:-$GLM_ROOT/.venv-mlx/bin/python}"
GLM_PORT="${GLM_PORT:-8080}"

if [[ -z "$GLM_ROOT" ]] || [[ ! -x "$GLM_MLX_PYTHON" ]]; then
  echo "ERROR: MLX python not found at ${GLM_MLX_PYTHON:-<unresolved>}" >&2
  echo "       Set GLM_ROOT or GLM_MLX_PYTHON in .env (or as env vars)." >&2
  echo "       Expected layout: <parent>/<SmartDocs-Agent>/../GLM-OCR/GLM-OCR/.venv-mlx/" >&2
  exit 1
fi

echo "Starting GLM-OCR MLX server (mlx-community/GLM-OCR-bf16) on :$GLM_PORT …"
echo "  GLM_ROOT : $GLM_ROOT"
echo "  python   : $GLM_MLX_PYTHON"
echo "  (Ctrl-C to stop. The model is held resident between requests.)"
exec "$GLM_MLX_PYTHON" -m mlx_vlm.server --trust-remote-code --port "$GLM_PORT"
