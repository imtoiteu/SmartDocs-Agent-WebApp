# Offline / Clean-Clone Setup (English)

SmartDocs-Agent is **offline-first**: with `OFFLINE=1` (the default) every AI
model is loaded **only** from local caches — nothing is downloaded at runtime.
That means a fresh clone must be **primed once while online** before those
features work. This guide lists exactly which models each feature needs, how to
cache them, and how to verify readiness.

> The web app, login, upload, document management and **basic text correction**
> work immediately with no model downloads. Everything below is about the AI
> features (OCR engines beyond Paddle, chat, rewrite, translation, GLM).

---

## TL;DR — one-time priming of a clean clone

```bash
scripts/setup.sh                        # main venv + deps + .env + folders
scripts/setup_offline.sh                # download ALL offline models (online, once)
scripts/setup_glm.sh --precache-layout  # (Apple Silicon only) GLM venvs + layout model
scripts/check_offline.sh                # verify: every feature usable / needs-setup / fallback
scripts/start.sh                        # run the stack
```

> **Always use `scripts/setup_offline.sh`, not `python tools/setup_offline.py`.**
> A bare `python` often resolves to the SYSTEM interpreter, which has none of the
> app's dependencies — the run then "succeeds" for pure downloads but silently
> skips VietOCR `config.yml`, Argos and embeddings with `No module named 'vietocr'
> / 'PIL' / …`. The wrapper resolves the main SmartDocs venv exactly the way
> `scripts/check.sh` does (`$SMARTDOCS_PYTHON` → `<repo>/.venv` → `<repo>/../.venv`)
> and refuses to run with anything else. `tools/setup_offline.py` itself also
> prints which Python it runs under and whether `PIL` / `vietocr` /
> `argostranslate` / `sentence_transformers` import — and warns loudly if the
> interpreter looks wrong. All four are provided by `requirements.txt` in the
> main venv.

---

## What each feature needs

| Feature | Needs (local) | Cached by | Missing → |
|---|---|---|---|
| Legacy / Modern Paddle OCR | PaddleX model cache | `setup_offline.py` (or first online OCR run) | downloads on first run (needs internet once) |
| **VietOCR** | `models/vietocr/config.yml` **+** `vgg_transformer.pth` | `setup_offline.py` | OCR returns a clear "run setup_offline" error |
| **GLM OCR** | `.venv-sdk` + `mlx_config.yaml` (`pipeline.layout.model_dir`) + PP-DocLayoutV3 in the default HF cache + MLX server | `setup_glm.sh --precache-layout` | "pipeline.layout.model_dir is required" / server-not-running toast |
| **AI Chat / AI Rewrite / Agent** | local **Qwen 2.5 1.5B** (the default, `CHAT_MODEL` = `QWEN_MODEL` = `FALLBACK_CHAT_MODEL`) | `setup_offline.py` | "No chat model could be loaded" |
| PhoBERT summarization | `vinai/phobert-base-v2` | `setup_offline.py` | **falls back** to extractive TF-IDF (still works) |
| RAG embeddings | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | `setup_offline.py` | **falls back** to char-hash retrieval (still works) |
| **Offline translation** | Argos packages in `models/argos/packages/` | `setup_offline.py` | online Google translate still works |

Notes:

- **Default local LLM = Qwen 2.5 1.5B-Instruct.** Chat, AI rewrite and the agent's
  local provider all use it, so `setup_offline.py` downloads it **once**. Larger
  models (e.g. 3B) are **not** the default and are **not** downloaded unless you set
  `CHAT_MODEL`/`QWEN_MODEL` in `.env` — the 3B model is optional and opt-in. A
  missing 3B never makes chat/rewrite report themselves as broken.
- **GLM layout model lives in the DEFAULT HF cache** (`~/.cache/huggingface`), not
  in `models/`. `glm_adapter.py` deliberately strips `HF_HOME` before shelling out
  to `glmocr`, so the layout checkpoint must be cached there. `setup_glm.sh
  --precache-layout` downloads it to the right place; afterwards runtime works with
  `HF_HUB_OFFLINE=1`.

---

## GLM self-hosted layout config

`glmocr` self-hosted mode **requires** `pipeline.layout.model_dir`. `setup_glm.sh`
writes it into `GLM-OCR/mlx_config.yaml`:

```yaml
pipeline:
  maas: { enabled: false }
  ocr_api: { api_host: localhost, api_port: 8080, model: mlx-community/GLM-OCR-bf16, api_mode: openai, verify_ssl: false }
  layout:
    model_dir: PaddlePaddle/PP-DocLayoutV3_safetensors   # HF id or local dir
    device: cpu
```

- Override the checkpoint with `GLM_LAYOUT_MODEL_DIR` in `.env` (HF id or absolute
  local directory).
- If an **older** `mlx_config.yaml` (generated before this fix) lacks
  `layout.model_dir`, `setup_glm.sh` regenerates it (backing up the old one to
  `mlx_config.yaml.bak`).

---

## Verifying readiness

```bash
scripts/check_offline.sh
```

Reports, per feature: **usable now**, **needs online setup**, or **running on a
fallback** — plus the main Python/Pillow, VietOCR config/weights, Paddle cache,
both GLM venvs, the `pipeline.layout.model_dir` value, and whether the GLM layout
model is cached. It changes nothing.

`scripts/check.sh` covers the runtime/venv side and points here for the model matrix.

The readiness check is **completeness-aware**: a model counts as ready only when a
full HF snapshot (config + weights) resolves in the app's cache
(`models/huggingface/`) — a half-finished or aborted download reports **missing**,
not ✅, so the check can't disagree with what the app can actually load. (The GLM
layout model is the one exception checked in the default `~/.cache/huggingface`.)

---

## Troubleshooting

- **Setup printed `No module named 'vietocr' / 'PIL' / 'argostranslate' / 'sentence_transformers'`** —
  you ran the tool with the wrong (system) Python. Use the wrapper:
  ```bash
  scripts/setup_offline.sh
  ```
- **`check_offline.sh` shows a required model missing right after setup** — the
  download was interrupted (or a hard crash aborted `setup_offline.py` mid-run).
  Just re-run it; completed assets are skipped:
  ```bash
  scripts/setup_offline.sh
  ```
  `setup_offline.py` runs the crash-prone PaddleOCR step **last**, so VietOCR,
  Argos and the Qwen/PhoBERT/embedding models are already on disk even if Paddle
  misbehaves on that machine.
- **"No chat model could be loaded" but the check said ✅ previously** — you were
  on the old check that only tested directory existence. Re-pull, re-run
  `check_offline.sh`; if it now shows the Local LLM missing, run `setup_offline.py`.
- **Argos offline translation missing / a pair won't install** — each pair installs
  independently, so others still succeed. Install the core pair manually:
  ```bash
  argospm install translate-en_vi
  argospm install translate-vi_en
  # …or drop the .argosmodel files into models/argos/packages/
  ```
  Online Google translate keeps working regardless.

---

## Fully offline afterwards

Once primed, set (or keep) `OFFLINE=1` in `.env`. The app loads HuggingFace,
Argos and Stanza models only from `MODEL_DIR` and never reaches the network. Copy
the whole project folder (including `models/`) plus the default HF cache to an
air-gapped machine to run without internet.
