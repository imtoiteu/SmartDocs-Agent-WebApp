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

**With GLM** (Apple Silicon only):

```bash
scripts/start_glm.sh -b      # start the model server (first run loads the model)
scripts/check.sh             # expect: "GLM health: 200"
scripts/start_web.sh         # or scripts/start.sh for both at once
```

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
