"""OCR engine routing tests (Phase 15).

Pure logic: natural-language request → OCR engine (default GLM, Vietnamese → VietOCR,
explicit always wins). Runs under pytest OR standalone.
"""

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import pytest  # noqa: F401
except ImportError:
    pytest = None

from agent.ocr_routing import (  # noqa: E402
    select_ocr_engine, normalize_engine, GLM, VIETOCR, PADDLE, PADDLE_MODERN,
)


def _eng(msg, explicit=None):
    return select_ocr_engine(msg, explicit)["engine"]


# ── the spec's worked examples ───────────────────────────────────────────────
def test_examples_from_spec():
    assert _eng("run OCR on this file") == GLM
    assert _eng("run OCR on this file using Vietnamese model") == VIETOCR
    assert _eng("extract Vietnamese text from this image") == VIETOCR
    assert _eng("run OCR using GLM") == GLM


# ── default ──────────────────────────────────────────────────────────────────
def test_default_is_glm():
    r = select_ocr_engine("please OCR this document")
    assert r["engine"] == GLM and r["reason"] == "default" and r["ocr_requested"] is True


def test_default_for_empty_message():
    assert _eng("") == GLM
    assert _eng(None) == GLM


# ── Vietnamese routing ───────────────────────────────────────────────────────
def test_vietnamese_variants_route_to_vietocr():
    for msg in [
        "use Vietnamese OCR",
        "run OCR using the Vietnamese model",
        "OCR Vietnamese text",
        "scan this with VietOCR",
        "đọc OCR tiếng việt",                 # Vietnamese-language phrasing + ocr
    ]:
        assert _eng(msg) == VIETOCR, msg
    assert select_ocr_engine("use Vietnamese OCR")["reason"] in (
        "vietnamese-request", "explicit-in-text")


def test_translate_to_vietnamese_is_not_ocr():
    # A translation request that merely mentions Vietnamese must NOT pick VietOCR,
    # and must not be flagged as an OCR request.
    r = select_ocr_engine("translate this document to Vietnamese")
    assert r["engine"] == GLM and r["ocr_requested"] is False


# ── explicit engine named in text ────────────────────────────────────────────
def test_explicit_engine_in_text():
    assert _eng("run OCR using GLM") == GLM
    assert _eng("ocr with PaddleOCR Modern") == PADDLE_MODERN
    assert _eng("use ppstructure to ocr this") == PADDLE_MODERN
    assert select_ocr_engine("run OCR using GLM")["reason"] == "explicit-in-text"


# ── explicit engine argument always overrides ────────────────────────────────
def test_explicit_arg_overrides_text():
    # Even though the text screams Vietnamese, an explicit arg wins.
    r = select_ocr_engine("extract Vietnamese text", explicit="glm")
    assert r["engine"] == GLM and r["reason"] == "explicit"
    assert _eng("run OCR using GLM", explicit="vietocr") == VIETOCR
    assert _eng("anything", explicit="paddleocr_modern") == PADDLE_MODERN


def test_unknown_explicit_arg_is_ignored():
    # An unrecognized engine arg falls through to text/default routing.
    assert _eng("run OCR on this file", explicit="nope") == GLM
    assert _eng("OCR Vietnamese text", explicit="") == VIETOCR


# ── normalize_engine ─────────────────────────────────────────────────────────
def test_normalize_engine_aliases():
    assert normalize_engine("glm") == GLM
    assert normalize_engine("GLM_OCR") == GLM
    assert normalize_engine("vietocr") == VIETOCR
    assert normalize_engine("paddle") == PADDLE
    assert normalize_engine("modern") == PADDLE_MODERN
    assert normalize_engine("auto") == GLM            # agent default
    assert normalize_engine("bogus") is None
    assert normalize_engine(None) is None


# ── result shape ─────────────────────────────────────────────────────────────
def test_result_shape_and_labels():
    r = select_ocr_engine("run OCR on this file")
    assert set(r.keys()) == {"engine", "label", "reason", "ocr_requested"}
    assert r["label"] == "GLM OCR"
    assert select_ocr_engine("use Vietnamese OCR")["label"] == "VietOCR"


if __name__ == "__main__":
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}")
        except Exception:
            failed += 1; print(f"FAIL  {name}"); traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
