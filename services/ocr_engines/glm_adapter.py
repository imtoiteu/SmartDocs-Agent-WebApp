from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from config import cfg

from .base import OCREngine

logger = logging.getLogger(__name__)

# Layout labels GLM-OCR emits whose `content` is HTML (kept verbatim in markdown /
# tables_html, but stripped to readable text for the flat `results`/plain-text path).
_HTML_LABELS = {"table"}
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _strip_html(s: str) -> str:
    """Turn an HTML fragment (e.g. a <table>) into readable plain text."""
    s = re.sub(r"</(tr|p|div|h\d|li)>", "\n", s, flags=re.I)
    s = re.sub(r"</t[dh]>", "\t", s, flags=re.I)
    s = _TAG_RE.sub("", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&lt;", "<").replace("&gt;", ">"))
    lines = [_WS_RE.sub(" ", ln).strip(" \t") for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _scale_box(region: dict, w: int, h: int):
    """Convert GLM 0–1000 normalised polygon/bbox to an image-pixel polygon
    ([[x,y],...]) so the existing canvas overlay (which scales by canvas/img) aligns.
    """
    sx, sy = w / 1000.0, h / 1000.0
    poly = region.get("polygon")
    if isinstance(poly, list) and len(poly) >= 3:
        try:
            return [[round(float(p[0]) * sx, 1), round(float(p[1]) * sy, 1)] for p in poly]
        except Exception:
            pass
    bbox = region.get("bbox_2d")
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox)
            return [[round(x1 * sx, 1), round(y1 * sy, 1)],
                    [round(x2 * sx, 1), round(y1 * sy, 1)],
                    [round(x2 * sx, 1), round(y2 * sy, 1)],
                    [round(x1 * sx, 1), round(y2 * sy, 1)]]
        except Exception:
            pass
    return None


def _page_of(name: str, default: int = 1) -> int:
    m = re.search(r"page(\d+)", name, re.I)
    return int(m.group(1)) + 1 if m else default


def _img_data_uri(path: Path) -> str | None:
    try:
        b = path.read_bytes()
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(b).decode()}"
    except Exception:
        return None


class GLMOCREngine(OCREngine):
    """GLM OCR — a local GLM-V vision OCR model (0.9B) run via its own SDK/venv.

    GLM-OCR is a *client*: it does layout detection (PP-DocLayoutV3, CPU) and then
    calls a local MLX model server (OpenAI-compatible, default :8080) per region.
    Because the SDK's deps (torch/transformers) cannot co-install with PaddlePaddle,
    SmartDocs invokes it as a **subprocess** in its own venv and reads the artifacts
    it writes (``X.json``/``X.md``/``layout_vis/``/``imgs/``), never importing it.

    Returns the standard SmartDocs shape (``results`` = ``{text, confidence, box}``
    per region, boxes scaled to pixels for the canvas overlay) plus the structured
    representations the viewer consumes: ``markdown``, ``tables_html``,
    ``layout_blocks``, ``images`` (base64 layout-vis + cropped regions) and
    ``raw_json``. ``layout_native=True`` skips the geometric reconstruction.
    """

    engine_name = "glmocr"

    def _server_up(self) -> bool:
        """Cheap TCP connect to the MLX model server. True if something is listening."""
        try:
            u = urlparse(cfg.GLM_OCR_API_URL)
            host = u.hostname or "localhost"
            port = u.port or (443 if u.scheme == "https" else 80)
            with socket.create_connection((host, port), timeout=3):
                return True
        except Exception:
            return False

    def _error(self, msg: str, w: int = 0, h: int = 0, ms: int = 0) -> dict:
        # Structured failure (NOT an exception) → the route returns it verbatim and
        # the SPA shows a clean error toast (it checks `data.success`).
        return {
            "success": False, "error": msg, "results": [],
            "img_width": w, "img_height": h, "elapsed_ms": ms,
            "ocr_engine": self.engine_name, "inference_status": "error",
            "layout_native": True,
        }

    def run(self, image_path: str) -> dict:
        from PIL import Image

        try:
            with Image.open(image_path) as im:
                w, h = im.size
        except Exception as e:
            return self._error(f"GLM OCR: cannot open image ({e})")

        if not Path(cfg.GLM_SDK_PYTHON).exists():
            return self._error(
                f"GLM OCR SDK not found at {cfg.GLM_SDK_PYTHON}. "
                f"Install the GLM-OCR venv (see GLM-OCR/GLM-OCR).", w, h)

        if not self._server_up():
            return self._error(
                "GLM-OCR model server is not running on "
                f"{cfg.GLM_OCR_API_URL}. Start it with tools/glm_serve.sh.", w, h)

        # GLM-OCR uses the DEFAULT HuggingFace cache (~/.cache/huggingface) where its
        # layout model lives — strip SmartDocs' HF_* redirects from the child env, and
        # force offline so it never reaches the network.
        env = dict(os.environ)
        for k in ("HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE", "HF_DATASETS_CACHE"):
            env.pop(k, None)
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"

        out_dir = tempfile.mkdtemp(prefix="glmocr_")
        t0 = time.time()
        try:
            cmd = [
                cfg.GLM_SDK_PYTHON, "-m", "glmocr.cli", "parse", str(image_path),
                "--config", cfg.GLM_CONFIG_YAML, "--mode", "selfhosted",
                "--output", out_dir, "--log-level", "WARNING",
            ]
            try:
                proc = subprocess.run(
                    cmd, cwd=cfg.GLM_ROOT, env=env, capture_output=True, text=True,
                    timeout=cfg.GLM_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return self._error(
                    f"GLM OCR timed out after {cfg.GLM_TIMEOUT}s.", w, h,
                    round((time.time() - t0) * 1000))
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                tail = " ".join(tail[-3:])[:300] if tail else "no output"
                return self._error(f"GLM OCR failed: {tail}", w, h,
                                   round((time.time() - t0) * 1000))

            res = self._collect(out_dir, w, h)
            res["elapsed_ms"] = round((time.time() - t0) * 1000)
            return res
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    # ── artifact parsing ────────────────────────────────────────────────────
    def _collect(self, out_dir: str, w: int, h: int) -> dict:
        import json

        base = Path(out_dir)
        subs = [d for d in base.iterdir() if d.is_dir()]
        stem_dir = subs[0] if subs else base

        # structured json (the one NOT ending _model.json) + raw model json
        struct_path = next(
            (p for p in sorted(stem_dir.glob("*.json")) if not p.name.endswith("_model.json")),
            None)
        if struct_path is None:
            return self._error("GLM OCR produced no JSON output.", w, h)
        try:
            pages = json.loads(struct_path.read_text(encoding="utf-8"))
        except Exception as e:
            return self._error(f"GLM OCR: bad JSON ({e})", w, h)

        items: list[dict] = []
        tables_html: list[str] = []
        layout_blocks: list[dict] = []
        order = 0
        for page in (pages or []):
            for region in (page or []):
                if not isinstance(region, dict):
                    continue
                label = (region.get("label") or "text").lower()
                content = str(region.get("content") or "")
                box = _scale_box(region, w, h)
                text = _strip_html(content) if label in _HTML_LABELS else content
                items.append({"text": text, "confidence": None, "box": box})
                if label in _HTML_LABELS and "<table" in content.lower():
                    tables_html.append(content)
                layout_blocks.append({
                    "label": region.get("label"),
                    "content": content,
                    "bbox": region.get("bbox_2d"),
                    "order": region.get("index", order),
                })
                order += 1

        # markdown
        md_path = next(iter(stem_dir.glob("*.md")), None)
        markdown = md_path.read_text(encoding="utf-8") if md_path else ""

        # extracted images: layout visualisation(s) + cropped region images
        images: list[dict] = []
        for p in sorted((stem_dir / "layout_vis").glob("*")):
            uri = _img_data_uri(p)
            if uri:
                images.append({"label": p.name, "kind": "layout", "page": _page_of(p.stem), "src": uri})
        for p in sorted((stem_dir / "imgs").glob("*")):
            uri = _img_data_uri(p)
            if uri:
                images.append({"label": p.name, "kind": "crop", "page": _page_of(p.stem), "src": uri})

        return {
            "success": True,
            "results": items,
            "img_width": w,
            "img_height": h,
            "ocr_engine": self.engine_name,
            "inference_status": "ok",
            "layout_native": True,
            "markdown": markdown,
            "tables_html": tables_html,
            "layout_blocks": layout_blocks,
            "images": images,
            "raw_json": pages,
        }
