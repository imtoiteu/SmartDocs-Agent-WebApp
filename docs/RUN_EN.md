# Running SmartDocs-Agent (English)

This is the practical guide to running SmartDocs-Agent locally with the
`scripts/` launchers. The scripts resolve the Python virtualenv and repository
paths automatically — **you never have to activate a venv or `cd` anywhere.**

> GLM OCR is **optional** and runs only on Apple Silicon (MLX). The web app and
> the Legacy / VietOCR / Modern OCR engines work fine without it.

---

## 1. One-time setup

```bash
scripts/setup.sh
```

This:

- finds an existing virtualenv (`./.venv`, or the parent `../.venv`), or creates
  `./.venv` if none exists — it never clobbers a working venv;
- installs `requirements.txt` into it;
- creates `.env` from `.env.example` if you don't have one yet;
- creates the runtime folders `logs/`, `uploads/`, `artifacts/`.

## 2. Check the environment

```bash
scripts/check.sh
```

Reports Python + venv, key dependencies, the state of the web and GLM ports, and
live health for both SmartDocs and (optionally) the GLM server. It changes
nothing and never fails just because GLM is down.

## 3. Start

### Full stack (recommended)

```bash
scripts/start.sh
```

- Starts the GLM server in the background **if** `ENABLE_GLM=true` and the MLX
  venv is present; otherwise prints a clear warning and continues without it.
- Starts the web app in the foreground. Press **Ctrl-C** to stop the web app
  (and the GLM server, if this command started it).

Open **http://localhost:5002** (or your `SMARTDOCS_PORT`) and log in.

### Individual services

```bash
scripts/start_web.sh        # only the web app (foreground)
scripts/start_web.sh -b     # only the web app (background -> logs/web.log)

scripts/start_glm.sh        # only the GLM server (foreground)
scripts/start_glm.sh -b     # only the GLM server (background -> logs/glm.log)
```

## 4. Stop

```bash
scripts/stop.sh             # stop background web + GLM (only what the scripts started)
scripts/stop.sh web         # stop only the web app
scripts/stop.sh glm         # stop only the GLM server
scripts/stop.sh --force     # ALSO kill whatever holds the port (use with care)
```

By default `stop.sh` only stops processes it started itself (tracked via PID
files in `logs/`). It will **not** kill an unrelated process that merely happens
to hold the port — important on shared machines. Pass `--force` to also stop a
stale/untracked process on the configured port. Foreground services (started
without `-b`) are stopped with **Ctrl-C**.

---

## Configuration (`.env`)

Copy `.env.example` to `.env` and edit. The runtime knobs the scripts use:

| Variable         | Default                          | Meaning                                            |
|------------------|----------------------------------|----------------------------------------------------|
| `SMARTDOCS_PORT` | `5002`                           | Web app port (scripts map it to the app's `PORT`). |
| `GLM_PORT`       | `8080`                           | GLM model server port.                             |
| `GLM_MODEL`      | `mlx-community/GLM-OCR-bf16`     | Model label used by the health probe.              |
| `ENABLE_GLM`     | `true`                           | Whether `start.sh` tries to launch GLM.            |

Everything else in `.env` (models, devices, API keys, offline mode) is read
directly by the app — see the comments in `.env.example`.

---

## Testing with and without GLM

**Without GLM** (any machine, including non-Mac):

```bash
ENABLE_GLM=false scripts/start.sh
```

The app starts normally. In the UI, Legacy PaddleOCR, PaddleOCR Modern, and
VietOCR all work. Selecting the **GLM OCR** engine shows a clear error toast
telling you to start the GLM server — nothing crashes.

**With GLM** (Apple Silicon only) — clean-clone setup, no external paths:

```bash
scripts/setup.sh             # main venv + requirements/glm-sdk.txt (SDK deps for the UI path)
scripts/setup_glm.sh         # GLM-OCR/.venv-mlx from requirements/glm-mlx-lock.txt (Py 3.10–3.12)
                             #   also writes GLM-OCR/mlx_config.yaml (selfhosted)
scripts/check.sh             # expect: "GLM SDK import (main): OK" + "GLM MLX import (glm): OK"
scripts/start_glm.sh -b      # start the model server (first run loads the model)
scripts/start.sh             # full stack; then expect "GLM health: 200"
```

Why two setup steps: the SmartDocs UI imports the vendored `GLM-OCR/glmocr` SDK
**in-process**, so its deps (`requirements/glm-sdk.txt`: PyMuPDF, wordfreq, …)
go into the **main** venv via `setup.sh`. The separate MLX **model server** runs
in `GLM-OCR/.venv-mlx`, pinned by `requirements/glm-mlx-lock.txt` via
`setup_glm.sh`. `setup_glm.sh` requires Python 3.10/3.11/3.12 (it rejects
3.13/3.14 unless you pass `--force`).

GLM path resolution is repo-local by default:

- `GLM_OCR_DIR` defaults to `<repo>/GLM-OCR` (the vendored copy).
- The GLM interpreter is the first that exists of
  `<repo>/GLM-OCR/.venv-mlx/bin/python` or `.../.venv-sdk/bin/python`.
- To use an **external** GLM-OCR checkout instead, set `GLM_OCR_DIR=/your/path`
  (and optionally `GLM_SDK_PYTHON` / `GLM_MLX_PYTHON`) in `.env`. Nothing is
  hardcoded to any machine.

Then in the UI: OCR tab → upload an image → pick **🧠 GLM OCR (Structured)** →
Run OCR.

---

## Troubleshooting

- **`Flask is not installed`** — run `scripts/setup.sh`.
- **`Port 5002 already in use`** — SmartDocs is already running; `scripts/stop.sh`,
  or set a different `SMARTDOCS_PORT`.
- **GLM health not 200** — make sure `scripts/start_glm.sh` is running and the
  model finished loading (watch `logs/glm.log`). GLM is Apple-Silicon only.
- **Logs** — background services write to `logs/web.log` and `logs/glm.log`.
