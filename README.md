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

**Offline-first note:** with `OFFLINE=1` (the default) AI models load only from
local caches. The web app, login, upload, document management and basic correction
work immediately, but **chat, AI rewrite, VietOCR, offline translation and GLM OCR
need a one-time online priming**:

```bash
scripts/setup_offline.sh                  # cache local LLM (Qwen 2.5 1.5B — chat/rewrite/agent),
                                          # PhoBERT, embeddings, VietOCR weights+config.yml, Argos
                                          # (wrapper — always uses the main venv Python)
scripts/check_offline.sh                  # report: each feature usable / needs-setup / fallback
```

Full guide: **[docs/OFFLINE_SETUP_EN.md](docs/OFFLINE_SETUP_EN.md)** · **[docs/OFFLINE_SETUP_VI.md](docs/OFFLINE_SETUP_VI.md)**.

Individual services:

```bash
scripts/start_web.sh    # only the web app        (add -b to run in the background)
scripts/start_glm.sh    # only the GLM OCR server  (Apple-Silicon / MLX only, optional)
scripts/stop.sh         # stop background services (web + GLM)
```

**Optional GLM OCR (Apple Silicon)** — uses the GLM-OCR vendored inside this repo
(`GLM-OCR/`); no external path needed on a clean clone:

```bash
scripts/setup.sh                       # main SmartDocs venv (keeps Pillow 10.2.0 for VietOCR)
scripts/setup_glm.sh --precache-layout # BOTH GLM venvs + write layout.model_dir + cache PP-DocLayoutV3
scripts/check.sh                       # verify both venvs' imports, Pillow, ports, health
scripts/check_offline.sh               # verify GLM layout config + layout model cache
scripts/start_glm.sh -b                # start the GLM model server in the background
scripts/start.sh                       # full stack
```

> `--precache-layout` downloads the PP-DocLayoutV3 checkpoint into the **default**
> HF cache (`~/.cache/huggingface`) — where `glm_adapter.py` looks — so self-hosted
> layout detection works offline. Without a cached layout model + a
> `pipeline.layout.model_dir` in `mlx_config.yaml`, GLM OCR fails with
> *"pipeline.layout.model_dir is required for self-hosted layout detection"*.

**Three isolated Python environments** (this is the key to why GLM works without
breaking VietOCR):

| Env | Purpose | Pillow | Notes |
|---|---|---|---|
| main SmartDocs venv | Flask app + Legacy/VietOCR/Modern OCR | **10.2.0** (VietOCR pins it) | never imports glmocr |
| `GLM-OCR/.venv-mlx` | MLX **model server** (`mlx_vlm`) | 12.x | no torch, no glmocr; Apple Silicon |
| `GLM-OCR/.venv-sdk` | glmocr **CLI / layout** — what the UI drives | 12.x | torch + editable glmocr |

The SmartDocs UI never imports GLM-OCR in-process. `services/ocr_engines/glm_adapter.py`
runs `glmocr.cli` as a **subprocess** using `GLM-OCR/.venv-sdk/bin/python`, so
GLM's Pillow 12.x stays isolated and can't collide with the main venv's 10.2.0.

Reproducible dependency files:

- `requirements/glm-mlx-lock.txt` — pinned freeze for `.venv-mlx` (MLX server).
- `requirements/glm-sdk-lock.txt` — pinned freeze for `.venv-sdk` (torch + layout
  deps); `glmocr` itself is added by an editable install of the vendored `GLM-OCR/`.

`setup_glm.sh` requires Python 3.10/3.11/3.12 (rejects 3.13/3.14 unless `--force`).
To use an external GLM-OCR checkout, set `GLM_OCR_DIR=/path/to/GLM-OCR` in `.env`.
GLM stays optional: `ENABLE_GLM=false scripts/start.sh` runs SmartDocs without it,
and the other three OCR engines never depend on it.

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
| Legacy PaddleOCR, PaddleOCR Modern | ✅ (models fetched on first online OCR run) | pre-cache via `scripts/setup_offline.sh` for offline |
| VietOCR | — | `scripts/setup_offline.sh` — needs `vgg_transformer.pth` **and** `models/vietocr/config.yml` (both created by it) |
| GLM-OCR engine | — | `scripts/setup_glm.sh --precache-layout` (repo-local venvs + PP-DocLayoutV3) + MLX server, **Apple Silicon only** |
| Correction (rule-based), extractive summarization, text reading | ✅ | — |
| Translation (online) | ✅ (needs internet) | — |
| Translation (offline / Argos) | — | `scripts/setup_offline.sh` (Argos packages in `MODEL_DIR`) |
| RAG chat / AI rewrite / agent (local **Qwen 2.5 1.5B**, the default) | — with `OFFLINE=1` | `scripts/setup_offline.sh` caches the 1.5B model (larger models opt-in via `.env`) |
| Agent with cloud LLMs (Groq / Gemini) | — | API keys in `.env` (falls back to local Qwen) |

Verify readiness anytime with **`scripts/check_offline.sh`**.

### Platform support matrix

Development happens on macOS Apple Silicon and Linux; those columns are verified.
Windows columns are *expected* from the codebase (CPU torch/paddle wheels,
`run_windows.bat`, `platform_system` markers in `requirements.txt`) but not
regularly tested — prefer **WSL** on Windows for the scripted flow.

| Feature | macOS Apple Silicon | Linux | Windows | Notes |
|---|---|---|---|---|
| Web app (Flask + SPA) | ✅ | ✅ | ✅ expected | `scripts/*.sh` need Git Bash/WSL on Windows; native: `run_windows.bat` or manual venv |
| PaddleOCR (Legacy + Modern) | ✅ | ✅ | ✅ expected | models auto-cache to `~/.paddlex/official_models/` on first online OCR run |
| VietOCR | ✅ | ✅ | ✅ expected | needs `scripts/setup_offline.sh` (weights + `config.yml`) |
| GLM OCR — **local MLX server** | ✅ | ❌ | ❌ | `mlx`/`mlx-vlm` wheels are **macOS/arm64 only**; set `ENABLE_GLM=false` elsewhere (or leave it — `start.sh` just warns and continues) |
| GLM OCR — external server | ✅ | ⚠️ unverified | ⚠️ unverified | point `GLM_OCR_API_URL` at a running GLM server; the `glmocr` CLI venv (`GLM-OCR/.venv-sdk`, plain torch) is still needed locally |
| Argos offline translation | ✅ | ✅ | ✅ expected | packages in `models/argos/packages/` via `scripts/setup_offline.sh` |
| Qwen 2.5 1.5B chat / AI rewrite / agent | ✅ (CPU) | ✅ (CPU / CUDA) | ✅ expected (CPU / CUDA) | the default local LLM; larger models opt-in via `.env` |
| Embeddings / RAG | ✅ | ✅ | ✅ expected | char-hash retrieval fallback if the model is missing |
| Desktop packaging (Electron/Tauri) | 🔜 plan | 🔜 plan | 🔜 plan | [docs/DESKTOP_BUILD.md](docs/DESKTOP_BUILD.md) is a **plan**, not implemented |

Full instructions: **[docs/INSTALLATION.md](docs/INSTALLATION.md)** (per-OS setup).
Clean-clone walkthrough: **[docs/RUN_EN.md](docs/RUN_EN.md)** · **[docs/RUN_VI.md](docs/RUN_VI.md)**.
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
