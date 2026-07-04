# macOS crash notes — Paddle + Torch signal-handler SIGSEGV

Analysis of the crash report `Python-2026-07-04-145305.ips` (kept out of the repo).
Recorded here so future MacBook validation has a reference. **No user data is in
this file.**

## What crashed

| Field | Value |
|---|---|
| Process | Homebrew **Python 3.10.17** (`/opt/homebrew/.../Python.framework/Versions/3.10`) |
| Launched by | **Electron** (the desktop wrapper) → `responsibleProc: Electron` |
| Signal | **SIGSEGV** (segmentation fault 11), `EXC_CRASH` |
| Faulting thread | a **PaddlePaddle worker thread** parked in `EventCount::Park` / `ThreadPoolTempl::WaitForWork` (`libpaddle.so`) |
| Main thread (T0) | inside `libpaddle.so google::FailureSignalHandler → SymbolizeAndDemangle → DumpStackFrameInfo` |
| Native libs loaded in the same process | `libpaddle.so`, `libtorch*.dylib`, `onnxruntime`, `cv2` — all from the **main SmartDocs venv** |

## Root cause (not the diagnostics)

PaddlePaddle installs a **Google-glog `FailureSignalHandler`** that hijacks
`SIGSEGV`/`SIGABRT`. In this process **PaddlePaddle and PyTorch are loaded
together** (the main venv runs Flask + Paddle OCR + the Torch-based Qwen/chat
models in one process). When a fault occurs on a Paddle threadpool worker, Paddle's
own handler runs and tries to symbolize a stack — turning a condition that Python
would otherwise handle into a fatal crash dump.

This is **not** caused by `scripts/check_offline.sh` or
`config.check_offline_readiness()` — those only inspect the filesystem and never
import Paddle/Torch or load a model. The crash is the **running app** (Paddle+Torch
coexistence under Electron).

The GLM three-venv split is unaffected and correct:
- main venv → Flask + VietOCR + Paddle + Torch chat/rewrite
- `GLM-OCR/.venv-mlx` → MLX server
- `GLM-OCR/.venv-sdk` → glmocr CLI / layout

The Paddle+Torch coexistence is inside the **main venv**, independent of GLM.

## Mitigation applied in this change

`tools/setup_offline.py` loads Torch (Qwen download) and then PaddleOCR in one
process — the exact fragile combination. It now calls
`paddle.disable_signal_handler()` before initialising PaddleOCR (best-effort), so
Paddle no longer hijacks signals during setup. The default-LLM change to
**Qwen 2.5 1.5B on CPU** also lowers MPS memory pressure, which is aligned with the
policy that this MacBook should not run larger Qwen models on MPS.

## Recommended follow-up (NOT applied here — needs approval)

The same `paddle.disable_signal_handler()` guard should be applied in the **app
runtime** right after PaddleOCR is first imported (e.g. in
`services/ocr_engines/paddle_adapter.py`, `paddle_modern_adapter.py`, and the
Paddle detector inside `vietocr_adapter.py`), OR PaddleOCR should be run in a
separate process from Torch. This is an OCR-engine-layer change, kept out of this
LLM-focused commit deliberately (surgical-change policy) — please confirm and it
can land as its own change.

## MacBook validation still needed

1. Reproduce: run the desktop (Electron) app, then trigger **Paddle/Modern OCR**
   on a document while a Torch chat/rewrite model is loaded. Confirm whether the
   segfault recurs.
2. Apply the follow-up guard (above) and re-test the same flow.
3. Confirm the default local LLM is now **Qwen 2.5 1.5B** end-to-end:
   `scripts/check_offline.sh` shows a single `Local LLM (chat/rewrite/agent)` row,
   chat + AI rewrite + agent all respond, and **no 3B download** happens.
4. Capture any new `.ips` if it still crashes and attach the faulting-thread
   backtrace.
