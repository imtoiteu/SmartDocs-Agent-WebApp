# SmartDocs-Agent

An offline-first, document-centric AI platform built on Flask. It combines four OCR
engines, classical + neural AI services (correction, translation, summarization,
RAG chat), and an LLM **agent** that orchestrates those capabilities as tools — all
behind one web UI and HTTP API.

- **OCR**: Legacy PaddleOCR (PP-OCRv5), PaddleOCR Modern (PP-StructureV3 + PP-OCRv6), VietOCR, GLM-OCR
- **AI services**: text correction, translation (Google / Argos), summarization (TF-IDF / PhoBERT / Qwen rewrite), RAG chat
- **Agent**: plans and chains the tools above, with document scoping and durable sessions
- **Storage**: SQLite + an in-memory RAG index, files under `uploads/`

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full technical architecture and
[docs/diagrams/](docs/diagrams/) for editable diagrams.

---

## Quick Start

**Prerequisites:** Python **3.10** (verified) and `git`. **Node/npm are *not* required** —
the frontend is plain vendored JavaScript with no build step. macOS, Ubuntu/Linux, and
Windows are supported (see [docs/INSTALLATION.md](docs/INSTALLATION.md) for per-OS details).

### Fastest start — the `scripts/` launchers (recommended)

The scripts resolve the virtualenv and repo paths for you — **you never have to
activate a venv or know where it lives.** Run them from anywhere.

```bash
cd SmartDocs-Agent
scripts/setup.sh        # create/find .venv, install deps, seed .env, make folders
scripts/check.sh        # verify Python, deps, ports, GLM + SmartDocs health
scripts/start.sh        # start the full local stack (GLM too, if enabled/available)
```

Then open **http://localhost:5002** (or the `SMARTDOCS_PORT` you set in `.env`) and log in.

Individual services:

```bash
scripts/start_web.sh    # only the web app        (add -b to run in the background)
scripts/start_glm.sh    # only the GLM OCR server  (Apple-Silicon / MLX only, optional)
scripts/stop.sh         # stop background services (web + GLM)
```

**Optional GLM OCR (Apple Silicon)** — uses the GLM-OCR vendored inside this repo
(`GLM-OCR/`); no external path needed on a clean clone:

```bash
scripts/setup.sh        # also installs requirements/glm-sdk.txt into the main venv,
                        #   so the Flask/UI path can import the GLM-OCR SDK in-process
scripts/setup_glm.sh    # create GLM-OCR/.venv-mlx from requirements/glm-mlx-lock.txt
scripts/check.sh        # verifies GLM SDK import (main Python) + MLX import (GLM Python)
scripts/start_glm.sh -b # start the GLM model server in the background
scripts/start.sh        # full stack
```

Two dependency sets make the GLM path reproducible on a clean clone:

- `requirements/glm-sdk.txt` — light SDK deps (PyMuPDF, wordfreq, …) that the
  **main** SmartDocs venv needs because the UI imports `GLM-OCR/glmocr` in-process.
- `requirements/glm-mlx-lock.txt` — pinned, known-good freeze for the **GLM
  MLX server** venv (`GLM-OCR/.venv-mlx`, Python 3.10–3.12, Apple Silicon).

To use an external GLM-OCR checkout instead, set `GLM_OCR_DIR=/path/to/GLM-OCR`
in `.env`. GLM stays optional: `ENABLE_GLM=false scripts/start.sh` runs SmartDocs
without it, and the other three OCR engines never depend on it.

Full guides: **[docs/RUN_EN.md](docs/RUN_EN.md)** · **[docs/RUN_VI.md](docs/RUN_VI.md)**.
Desktop-app packaging plan: **[docs/DESKTOP_BUILD.md](docs/DESKTOP_BUILD.md)**.

### Manual start (equivalent, no scripts)

```bash
# 1. Get the code and enter the project
cd SmartDocs-Agent

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies (~several GB incl. torch + paddle)
pip install -r requirements.txt

# 4. Create your env file (safe defaults; edit later for API keys / models)
cp .env.example .env

# 5. Run — first launch creates and seeds the SQLite database
python app.py
```

Then open **http://localhost:5002** (or the `SMARTDOCS_PORT` / `PORT` you set in `.env`) and log in.

> **First-run accounts (CHANGE IMMEDIATELY):** `admin / admin123` and `user / user123`.
> These are seeded on first launch ([models.py](models.py)). Reset passwords in the Admin
> console (`/admin`) before exposing the app to anyone.

**Convenience launchers** (create `.venv`, copy `.env`, install deps, then start):

```bash
bash run_mac.sh         # macOS / Linux
run_windows.bat         # Windows
```

> Note: the launch scripts look for a virtualenv at `../.venv` (the repo's parent) first,
> then a local `.venv`. Either works.

### What works out of the box vs. needs setup

| Capability | Works immediately | Needs extra setup |
|---|---|---|
| Legacy PaddleOCR, PaddleOCR Modern, VietOCR | ✅ (models fetched on first use / via helper) | — |
| GLM-OCR engine | — | `scripts/setup_glm.sh` (repo-local venv) + MLX server, **Apple Silicon only** |
| Correction, extractive summarization, text reading | ✅ | — |
| Translation (online) | ✅ (needs internet) | — |
| Translation (offline / Argos) | — | Argos packages in `MODEL_DIR` |
| RAG chat / AI rewrite (local Qwen) | ✅ (downloads model unless `OFFLINE=1`) | Pre-download for offline use |
| Agent with cloud LLMs (Groq / Gemini) | — | API keys in `.env` (falls back to local Qwen) |

Full instructions: **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.
Production deployment: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

---

## Running tests

```bash
pytest                 # full suite (root test_*.py + agent/tests)
pytest agent/tests     # agent layer only
```

## Repository layout

```text
app.py                  Flask app + OCR/upload/document routes (entrypoint)
auth.py  admin_bp.py    Auth + admin blueprints
chat_bp.py agent_bp.py  Chat (RAG) + Agent blueprints
config.py               Central configuration (reads .env)
models.py               SQLAlchemy models + DB helpers (SQLite)
services/               OCR engines + AI services (correction/translate/summary/chat)
agent/                  Agent core, LLM providers, tools, skills, knowledge, memory
static/  templates/     Frontend SPA + Jinja admin pages
tools/                  Offline-setup / model-download / GLM-serve / benchmark helpers
docs/                   Architecture, diagrams, installation, deployment
uploads/                User-uploaded files (UUID-named)
requirements.txt        Python dependencies
run_mac.sh run_windows.bat  Convenience launchers
```
