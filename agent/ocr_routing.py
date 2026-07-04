"""OCR engine selection for the agent (Phase 15).

Pure, model-free routing of a natural-language request to an OCR engine, so the
agent (the orchestration layer) picks the right engine without the user ever
touching internal engine ids. Rules:

  * an explicit engine (UI arg, or one NAMED in the request text) always wins;
  * a Vietnamese-OCR request (e.g. "use Vietnamese OCR", "extract Vietnamese
    text", "run OCR using the Vietnamese model") → VietOCR;
  * everything else → GLM OCR (the agent's default).

Engine ids match ``services/ocr_engines/router.py`` so a result can be passed
straight to ``/api/ocr/all``. This module imports nothing heavy, so ``import
agent`` stays model-free; it does NOT touch the global OCR default or the SPA
OCR viewer — it only decides which engine the agent asks for.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

# Canonical engine ids (must match the OCR router's registry keys).
GLM = "glmocr"
VIETOCR = "vietocr"
PADDLE = "paddleocr"
PADDLE_MODERN = "paddleocr_modern"

# The agent's default OCR engine (product rule: GLM for all OCR requests).
DEFAULT_ENGINE = GLM

_LABELS = {
    GLM: "GLM OCR",
    VIETOCR: "VietOCR",
    PADDLE: "Legacy PaddleOCR",
    PADDLE_MODERN: "PaddleOCR Modern",
}

# Lightweight alias map for an explicit engine argument. Kept local on purpose so
# this module imports nothing heavy. Note 'auto' resolves to the agent default
# (GLM), which differs from the global config default — by design.
_ALIASES = {
    "glm": GLM, "glmocr": GLM, "glm_ocr": GLM, "glm-ocr": GLM,
    "viet": VIETOCR, "vietocr": VIETOCR,
    "paddle": PADDLE, "paddleocr": PADDLE, "legacy": PADDLE,
    "modern": PADDLE_MODERN, "paddleocr_modern": PADDLE_MODERN, "ppstructure": PADDLE_MODERN,
    "auto": DEFAULT_ENGINE,
}

# Signals an OCR operation (vs translate / summarize / chat).
_OCR_INTENT = re.compile(
    r"\bocr\b|\bscan\b|recogni[sz]e|"
    r"extract(?:ing|ed)?\s+(?:the\s+)?(?:vietnamese\s+)?text|"
    r"read\s+text|text\s+from",
    re.I,
)
# Explicit engine named in free text.
_GLM_RE = re.compile(r"\bglm(?:[\s\-_]?ocr)?\b", re.I)
_VIET_RE = re.compile(r"viet\s*ocr", re.I)                 # "VietOCR" / "viet ocr"
_MODERN_RE = re.compile(r"pp[\s\-]?structure|paddle\s*(?:ocr)?\s*modern", re.I)
# A Vietnamese-OCR request.
_VIET_WORD = re.compile(r"vietnamese|tiếng\s*việt|tieng\s*viet", re.I)
_VIET_MODEL = re.compile(r"vietnamese\s+(?:ocr|model|engine|text)", re.I)


def label_for(engine: str) -> str:
    """Human label for an engine id (falls back to the id)."""
    return _LABELS.get(engine, engine)


def normalize_engine(name: Optional[str]) -> Optional[str]:
    """Map an engine name/alias to a canonical id, or None if unrecognized."""
    if not name:
        return None
    return _ALIASES.get(str(name).strip().lower())


def select_ocr_engine(message: Optional[str], explicit: Optional[str] = None) -> Dict[str, object]:
    """Resolve the OCR engine for a request.

    Returns ``{engine, label, reason, ocr_requested}`` where ``engine`` is a
    canonical id, ``reason`` is one of ``explicit`` | ``explicit-in-text`` |
    ``vietnamese-request`` | ``default``, and ``ocr_requested`` is True when the
    message actually asks for OCR (used to decide whether to surface the engine).
    """
    m = message or ""

    # 1) Explicit engine argument (e.g. a UI override) always wins.
    norm = normalize_engine(explicit)
    if norm:
        return {"engine": norm, "label": label_for(norm),
                "reason": "explicit", "ocr_requested": True}

    ocr_requested = bool(_OCR_INTENT.search(m))

    # 2) Engine named explicitly in the request text.
    if _VIET_RE.search(m):
        return {"engine": VIETOCR, "label": label_for(VIETOCR),
                "reason": "explicit-in-text", "ocr_requested": True}
    if _GLM_RE.search(m):
        return {"engine": GLM, "label": label_for(GLM),
                "reason": "explicit-in-text", "ocr_requested": True}
    if _MODERN_RE.search(m):
        return {"engine": PADDLE_MODERN, "label": label_for(PADDLE_MODERN),
                "reason": "explicit-in-text", "ocr_requested": True}

    # 3) Vietnamese-OCR request: an explicit "Vietnamese model/ocr/text", or
    #    "Vietnamese" together with an OCR verb (so "translate to Vietnamese" — a
    #    translation, not OCR — does NOT route to VietOCR).
    if _VIET_MODEL.search(m) or (_VIET_WORD.search(m) and ocr_requested):
        return {"engine": VIETOCR, "label": label_for(VIETOCR),
                "reason": "vietnamese-request", "ocr_requested": True}

    # 4) Default → GLM OCR.
    return {"engine": DEFAULT_ENGINE, "label": label_for(DEFAULT_ENGINE),
            "reason": "default", "ocr_requested": ocr_requested}
