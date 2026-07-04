#!/usr/bin/env python3
"""
SmartDocs Platform — Offline Setup Tool
========================================
Run this script ONCE on a machine with internet access.
It downloads all required models into web_app/models/
so the app can run completely offline afterwards.

Usage (preferred — resolves the main SmartDocs venv automatically):
    scripts/setup_offline.sh

Running it directly works ONLY with the main venv's interpreter
(a bare `python tools/setup_offline.py` often picks the SYSTEM python,
which has no vietocr/PIL/argostranslate — steps then silently skip):
    .venv/bin/python tools/setup_offline.py      # or ../.venv/bin/python …

After this completes, copy the entire project folder
(including models/) to any machine and run:
    bash run_mac.sh     # macOS / Linux
    run_windows.bat     # Windows
"""

import sys
import shutil
import subprocess
from pathlib import Path

# ── Bootstrap path ────────────────────────────────────────────────────────────
WEB_APP = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(WEB_APP))

print()
print("=" * 60)
print("  SmartDocs Platform — Offline Model Setup")
print("=" * 60)

# ── Interpreter diagnostics (BEFORE any app import) ───────────────────────────
# The single most common failure mode of this script is running it with the
# WRONG python (system interpreter instead of the main SmartDocs venv): the
# pure-download steps succeed but VietOCR config.yml / Argos / embeddings are
# silently skipped with "No module named …". Surface that immediately.
import platform


def _import_ok(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def _expected_venv_dirs():
    """The venv locations scripts/lib.sh::venv_python resolves, in order."""
    import os as _os
    dirs = []
    sp = _os.environ.get("SMARTDOCS_PYTHON", "").strip()
    if sp:
        # <venv>/bin/python → <venv>   (also handles <venv>/Scripts/python.exe)
        dirs.append(Path(sp).parent.parent)
    dirs.append(WEB_APP / ".venv")
    dirs.append(WEB_APP.parent / ".venv")
    return [d for d in dirs if d.is_dir()]


_IMPORT_CHECKS = {
    "PIL":                   _import_ok("PIL"),
    "vietocr":               _import_ok("vietocr"),
    "argostranslate":        _import_ok("argostranslate"),
    "sentence_transformers": _import_ok("sentence_transformers"),
}

print(f"\n  Python     : {sys.executable}")
print(f"  Version    : {platform.python_version()}")
for _mod, _okflag in _IMPORT_CHECKS.items():
    print(f"  import {_mod:<22}: {'OK' if _okflag else '❌ MISSING'}")

# In a venv, sys.prefix IS the venv directory (don't compare executables —
# venv pythons are symlinks, so realpath collapses to the base interpreter).
_expected = _expected_venv_dirs()
_in_expected_venv = any(
    Path(sys.prefix).resolve() == d.resolve() for d in _expected
)
if (_expected and not _in_expected_venv) or not (_IMPORT_CHECKS["PIL"] and _IMPORT_CHECKS["vietocr"]):
    print()
    print("  " + "!" * 56)
    print("  ⚠️  You may be using the wrong Python. Use scripts/setup_offline.sh.")
    print("     It resolves the main SmartDocs venv automatically (same one")
    print("     scripts/check.sh uses). All four imports above are provided by")
    print("     requirements.txt in that venv.")
    if _expected:
        print(f"     Expected venv: {_expected[0]}")
    print("  " + "!" * 56)

# ── Load config (sets HF env vars) ────────────────────────────────────────────
from config import cfg

MODELS_DIR = cfg.MODEL_DIR
HF_HUB     = cfg.HF_DIR / "hub"
ARGOS_DIR  = cfg.ARGOS_DIR

print(f"\n  MODEL_DIR : {MODELS_DIR}")
print(f"  HF cache  : {HF_HUB}")
print(f"  Argos dir : {ARGOS_DIR}")

# Allow downloads for this setup run
import os
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)

errors = []


# ══════════════════════════════════════════════════════════════════════════════
#  1. Qwen local LLM(s) — chat (CHAT_MODEL / FALLBACK_CHAT_MODEL) + AI rewrite
#     (QWEN_MODEL) + agent local provider.
#     DEFAULT LOCAL LLM POLICY: Qwen2.5-1.5B-Instruct is the single default for
#     ALL local LLM features. With the shipped defaults these three ids are the
#     SAME model, so only Qwen2.5-1.5B is downloaded. A larger model (e.g. 3B) is
#     downloaded ONLY if you explicitly set CHAT_MODEL/QWEN_MODEL in .env — it is
#     never fetched by default (unstable on Apple-Silicon MPS for this app).
# ══════════════════════════════════════════════════════════════════════════════
_qwen_models = []
for _m in (cfg.QWEN_MODEL, cfg.CHAT_MODEL, cfg.FALLBACK_CHAT_MODEL):
    if _m and _m not in _qwen_models:
        _qwen_models.append(_m)
if len(_qwen_models) == 1:
    print(f"\n[1/6] Local LLM (default) — {_qwen_models[0]}  [chat + rewrite + agent]")
else:
    print(f"\n[1/6] Local LLMs — {', '.join(_qwen_models)}  (extra model(s) from .env opt-in)")
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    for _m in _qwen_models:
        try:
            print(f"  ↓ {_m} — tokenizer…")
            AutoTokenizer.from_pretrained(_m)
            print(f"  ↓ {_m} — weights (1.5B≈3 GB / larger models bigger, please wait)…")
            AutoModelForCausalLM.from_pretrained(_m, torch_dtype=torch.float32)
            print(f"  ✅ {_m} ready")
        except Exception as e:
            print(f"  ❌ {_m} failed: {e}")
            errors.append(f"Qwen {_m}: {e}")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  2. PhoBERT (Vietnamese summarization)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[2/6] PhoBERT — {cfg.PHOBERT_MODEL}")
try:
    from transformers import AutoTokenizer, AutoModel

    print("  Downloading tokenizer…")
    AutoTokenizer.from_pretrained(cfg.PHOBERT_MODEL)

    print("  Downloading model weights (~400 MB)…")
    AutoModel.from_pretrained(cfg.PHOBERT_MODEL)

    print("  ✅ PhoBERT ready")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"PhoBERT: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  3. sentence-transformers (semantic embeddings for document chat / RAG)
# ══════════════════════════════════════════════════════════════════════════════
# Without this, AI Chat retrieval falls back to char-n-gram hashing (works, but
# can't match paraphrases). Caching it here enables real semantic retrieval offline.
# Keep in sync with EmbeddingEngine.SBERT_MODEL in services/chat_service.py.
_SBERT_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
print(f"\n[3/6] Embeddings (optional; hashing fallback if skipped) — {_SBERT_ID}")
try:
    from sentence_transformers import SentenceTransformer

    print("  Downloading sentence-transformers model (~470 MB)…")
    SentenceTransformer(_SBERT_ID)
    print("  ✅ sentence-transformers ready (semantic RAG enabled)")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")
    print("     sentence-transformers IS in requirements.txt — a missing import here")
    print("     usually means the wrong Python. Use scripts/setup_offline.sh.")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"sentence-transformers: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  4. VietOCR models  (pure download — no torch/paddle; run BEFORE PaddleOCR so a
#     Paddle segfault can never block config.yml/weights generation)
# ══════════════════════════════════════════════════════════════════════════════
print("\n[4/6] VietOCR models")
try:
    import urllib.request
    vietocr_dir = MODELS_DIR / "vietocr"
    vietocr_dir.mkdir(parents=True, exist_ok=True)
    
    # Official URL for vgg_transformer.pth
    url = "https://vocr.vn/data/vietocr/vgg_transformer.pth"
    weight_path = vietocr_dir / "vgg_transformer.pth"
    
    if weight_path.exists():
        print(f"  ✓ {weight_path.name} already downloaded")
    else:
        print(f"  Downloading {weight_path.name} (~160 MB)…")
        urllib.request.urlretrieve(url, str(weight_path))

    # ── Generate models/vietocr/config.yml (OFFLINE) ──────────────────────────
    # The adapter (services/ocr_engines/vietocr_adapter.py) loads a LOCAL
    # config.yml on purpose — vietocr's Cfg.load_config_from_name() may hit the
    # network. We build it here from the yaml files BUNDLED inside the installed
    # vietocr package (no internet), merging base.yml + the architecture yaml.
    config_yml = vietocr_dir / "config.yml"
    if config_yml.exists():
        print(f"  ✓ {config_yml.name} already present")
    else:
        try:
            import yaml, vietocr
            pkg_cfg = Path(vietocr.__file__).parent / "config"
            arch = cfg.VIETOCR_CONFIG                       # e.g. "vgg_transformer"
            base_f = pkg_cfg / "base.yml"
            # vietocr ships the arch file with a hyphen: vgg-transformer.yml
            arch_f = pkg_cfg / f"{arch.replace('_', '-')}.yml"
            if not arch_f.exists():
                arch_f = pkg_cfg / f"{arch}.yml"
            if base_f.exists() and arch_f.exists():
                merged = yaml.safe_load(base_f.read_text(encoding="utf-8")) or {}
                over = yaml.safe_load(arch_f.read_text(encoding="utf-8")) or {}
                # shallow-merge, then one level deep for nested dicts (cnn/transformer/…)
                for k, v in over.items():
                    if isinstance(v, dict) and isinstance(merged.get(k), dict):
                        merged[k].update(v)
                    else:
                        merged[k] = v
                # Offline, local-weights defaults (the adapter re-asserts these too)
                merged.setdefault("cnn", {})["pretrained"] = False
                merged["weights"] = str(weight_path)
                merged["device"] = cfg.VIETOCR_DEVICE
                merged.setdefault("predictor", {})["beamsearch"] = False
                config_yml.write_text(yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
                                      encoding="utf-8")
                print(f"  ✅ Wrote {config_yml} (from bundled {arch_f.name})")
            else:
                print(f"  ⚠️  Could not find bundled vietocr configs in {pkg_cfg} — "
                      f"config.yml NOT generated. VietOCR OCR will be unavailable.")
                errors.append("VietOCR: bundled package configs not found; config.yml missing")
        except Exception as e:
            print(f"  ⚠️  Could not generate config.yml: {e}")
            if isinstance(e, ImportError):
                print("     vietocr IS in requirements.txt — a missing import here usually")
                print("     means the wrong Python. Use scripts/setup_offline.sh.")
            errors.append(f"VietOCR config.yml: {e}")

    print("  ✅ VietOCR ready")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"VietOCR: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  5. Argos Translate packages  (pure download — also before PaddleOCR)
# ══════════════════════════════════════════════════════════════════════════════
_argos_packages_dir = ARGOS_DIR / "packages"
_argos_packages_dir.mkdir(parents=True, exist_ok=True)
print(f"\n[5/6] Argos Translate offline packages → {_argos_packages_dir}")

# Must set env var BEFORE importing argostranslate (it reads it at import time)
os.environ["ARGOS_PACKAGES_DIR"] = str(_argos_packages_dir)
os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(_argos_packages_dir)

# en↔vi is the CORE pair (listed first); the rest are best-effort extras. Each pair
# installs independently so one failed/absent package never blocks the others.
ARGOS_PAIRS = [
    ("en", "vi"), ("vi", "en"),
    ("en", "zh"), ("zh", "en"),
    ("en", "ja"), ("ja", "en"),
    ("en", "ko"), ("ko", "en"),
    ("en", "fr"), ("fr", "en"),
    ("en", "de"), ("de", "en"),
    ("en", "es"), ("es", "en"),
]
try:
    import argostranslate.settings as _as
    import argostranslate.package

    # Patch runtime state (safety net)
    _as.data_dir = ARGOS_DIR
    _as.package_data_dir = _argos_packages_dir
    if _argos_packages_dir not in _as.package_dirs:
        _as.package_dirs.insert(0, _argos_packages_dir)

    print("  Fetching package index…")
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    installed = {(p.from_code, p.to_code) for p in argostranslate.package.get_installed_packages()}

    downloaded = 0
    failed_pairs = []
    for from_code, to_code in ARGOS_PAIRS:
        if (from_code, to_code) in installed:
            print(f"  ✓ {from_code}→{to_code} already installed")
            continue
        pkg = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)
        if not pkg:
            print(f"  ⚠️  Package {from_code}→{to_code} not available in index")
            continue
        # Per-package guard: a single download/install failure must not abort the
        # remaining pairs (esp. the core en↔vi pair listed first).
        try:
            print(f"  ↓ Installing {from_code}→{to_code}…")
            argostranslate.package.install_from_path(pkg.download())
            downloaded += 1
        except Exception as e:
            print(f"  ❌ {from_code}→{to_code} failed: {e}")
            failed_pairs.append(f"{from_code}→{to_code}")

    print(f"  ✅ Argos: {downloaded} new package(s) installed to {_argos_packages_dir}")
    # Only surface a hard error if the CORE en↔vi pair could not be made available.
    core_ok = all(
        (fc, tc) in installed or f"{fc}→{tc}" not in failed_pairs
        for fc, tc in (("en", "vi"), ("vi", "en"))
    )
    if not core_ok:
        errors.append("Argos: core en↔vi pair failed to install "
                      "(manual: `argospm install translate-en_vi` / `translate-vi_en`, "
                      f"or drop the .argosmodel into {_argos_packages_dir})")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")
    print("     argostranslate IS in requirements.txt — a missing import here usually")
    print("     means the wrong Python. Use scripts/setup_offline.sh.")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    print(f"     Manual fallback: `argospm install translate-en_vi` and `translate-vi_en`, "
          f"or place .argosmodel files in {_argos_packages_dir}.")
    errors.append(f"Argos: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  6. PaddleOCR — LAST on purpose.
#     This script has already loaded torch/transformers (Qwen/PhoBERT steps), and
#     PaddlePaddle installs a Google-glog FailureSignalHandler that hijacks
#     SIGSEGV/SIGABRT. With torch + paddle sharing one process, that handler can
#     turn a benign worker-thread condition into a FATAL crash while symbolizing a
#     stack (observed in a macOS .ips: libpaddle FailureSignalHandler →
#     SymbolizeAndDemangle). Running Paddle LAST means even a hard crash here leaves
#     the Qwen/PhoBERT/embeddings/VietOCR/Argos assets already on disk. We also call
#     paddle.disable_signal_handler() first so Python handles signals normally.
#     Best-effort; never fatal if the API is unavailable.
# ══════════════════════════════════════════════════════════════════════════════
print("\n[6/6] PaddleOCR models  (downloads on first predict(); run last for stability)")
test_img = MODELS_DIR / "_paddle_setup_test.png"
try:
    from PIL import Image, ImageDraw

    # Create a small test image to force model download
    img = Image.new("RGB", (200, 60), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "SmartDocs test", fill=(0, 0, 0))
    img.save(str(test_img))

    print("  Initializing PaddleOCR (downloads models on first use)…")
    try:
        import paddle
        paddle.disable_signal_handler()
    except Exception:
        pass
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False)
    ocr.predict(str(test_img))
    test_img.unlink(missing_ok=True)
    print("  ✅ PaddleOCR ready")
except Exception as e:
    if test_img.exists():
        test_img.unlink(missing_ok=True)
    print(f"  ❌ Failed: {e}")
    errors.append(f"PaddleOCR: {e}")



# ══════════════════════════════════════════════════════════════════════════════
#  Summary
# ══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 60)
if errors:
    print("  ⚠️  Setup completed with errors:")
    for e in errors:
        print(f"     • {e}")
    print()
    print("  The app may still work for features whose models succeeded.")
else:
    print("  ✅ All models downloaded successfully!")
    print()
    print("  The project is now OFFLINE-READY.")
    print("  Copy the entire folder to another machine and run:")
    print("    bash run_mac.sh      (macOS / Linux)")
    print("    run_windows.bat      (Windows)")
print("=" * 60)
print()

# ── Post-setup readiness snapshot (same source of truth as check_offline.sh) ──
# Verifies what is ACTUALLY on disk now (completeness-checked, not just "downloaded
# without error"), and prints the exact re-run command if a required asset is short.
try:
    import importlib
    import config as _cfgmod
    importlib.reload(_cfgmod)          # pick up files written during this run
    _c = _cfgmod.cfg
    r = _c.check_offline_readiness()
    required = {
        "VietOCR config.yml":            r["vietocr_config"],
        "VietOCR weights":               r["vietocr_weights"],
        "Local LLM (chat/rewrite/agent)":r["ai_rewrite"],
    }
    optional = {
        "Embeddings (RAG, fallback OK)":  r["embeddings"],
        "Argos offline translate":        r["argos"],
        "PhoBERT summarize (fallback OK)":r["phobert"],
    }
    print("  ── Readiness after setup ────────────────────────")
    for label, (okflag, _detail) in required.items():
        print(f"   {'✅' if okflag else '❌'} {label}")
    for label, (okflag, _detail) in optional.items():
        print(f"   {'✅' if okflag else '⚠️ '} {label}")
    missing_required = [k for k, (okflag, _d) in required.items() if not okflag]
    if missing_required:
        print()
        print("  ❗ Required asset(s) still missing: " + ", ".join(missing_required))
        print("     Re-run online:  scripts/setup_offline.sh")
    print()
except Exception as e:
    print(f"  (readiness snapshot skipped: {e})")

# Show disk usage
try:
    total = sum(f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file())
    gb = total / (1024**3)
    print(f"  models/ total size: {gb:.1f} GB")
except Exception:
    pass
