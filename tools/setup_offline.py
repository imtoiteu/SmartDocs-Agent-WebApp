#!/usr/bin/env python3
"""
SmartDocs Platform — Offline Setup Tool
========================================
Run this script ONCE on a machine with internet access.
It downloads all required models into web_app/models/
so the app can run completely offline afterwards.

Usage:
    cd /path/to/web_app
    python tools/setup_offline.py

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
#  1. Qwen (AI Rewrite model)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[1/5] Qwen — {cfg.QWEN_MODEL}")
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print("  Downloading tokenizer…")
    AutoTokenizer.from_pretrained(cfg.QWEN_MODEL)

    print("  Downloading model weights (~3 GB, please wait)…")
    AutoModelForCausalLM.from_pretrained(cfg.QWEN_MODEL, torch_dtype=torch.float32)

    print("  ✅ Qwen ready")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"Qwen: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  2. PhoBERT (Vietnamese summarization)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[2/5] PhoBERT — {cfg.PHOBERT_MODEL}")
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
#  2b. sentence-transformers (semantic embeddings for document chat / RAG)
# ══════════════════════════════════════════════════════════════════════════════
# Without this, AI Chat retrieval falls back to char-n-gram hashing (works, but
# can't match paraphrases). Caching it here enables real semantic retrieval offline.
# Keep in sync with EmbeddingEngine.SBERT_MODEL in services/chat_service.py.
_SBERT_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
print(f"\n[2b] Embeddings — {_SBERT_ID}")
try:
    from sentence_transformers import SentenceTransformer

    print("  Downloading sentence-transformers model (~470 MB)…")
    SentenceTransformer(_SBERT_ID)
    print("  ✅ sentence-transformers ready (semantic RAG enabled)")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"sentence-transformers: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  3. PaddleOCR (runs its own download on first predict() call)
# ══════════════════════════════════════════════════════════════════════════════
print("\n[3/5] PaddleOCR models")
try:
    import numpy as np
    from PIL import Image, ImageDraw

    # Create a small test image to force model download
    img = Image.new("RGB", (200, 60), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "SmartDocs test", fill=(0, 0, 0))
    test_img = MODELS_DIR / "_paddle_setup_test.png"
    img.save(str(test_img))

    print("  Initializing PaddleOCR (downloads models on first use)…")
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
#  4. VietOCR models
# ══════════════════════════════════════════════════════════════════════════════
print("\n[4/5] VietOCR models")
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
    
    print("  ✅ VietOCR ready")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"VietOCR: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  5. Argos Translate packages
# ══════════════════════════════════════════════════════════════════════════════
_argos_packages_dir = ARGOS_DIR / "packages"
_argos_packages_dir.mkdir(parents=True, exist_ok=True)
print(f"\n[5/5] Argos Translate offline packages → {_argos_packages_dir}")

# Must set env var BEFORE importing argostranslate (it reads it at import time)
os.environ["ARGOS_PACKAGES_DIR"] = str(_argos_packages_dir)
os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(_argos_packages_dir)

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
    for from_code, to_code in ARGOS_PAIRS:
        if (from_code, to_code) in installed:
            print(f"  ✓ {from_code}→{to_code} already installed")
            continue
        pkg = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)
        if pkg:
            print(f"  ↓ Installing {from_code}→{to_code}…")
            argostranslate.package.install_from_path(pkg.download())
            downloaded += 1
        else:
            print(f"  ⚠️  Package {from_code}→{to_code} not available in index")

    print(f"  ✅ Argos ready ({downloaded} new packages installed to {_argos_packages_dir})")
except ImportError as e:
    print(f"  ⚠️  Skipped (missing library): {e}")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    errors.append(f"Argos: {e}")



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

# Show disk usage
try:
    total = sum(f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file())
    gb = total / (1024**3)
    print(f"  models/ total size: {gb:.1f} GB")
except Exception:
    pass
