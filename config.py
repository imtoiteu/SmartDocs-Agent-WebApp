"""
SmartDocs Platform — Central Configuration
==========================================
Reads from environment variables (or a .env file via python-dotenv).
All platform-specific paths and device settings are resolved here.
Every other module imports from this file instead of hardcoding values.

Usage:
    from config import cfg
    print(cfg.UPLOAD_DIR)
    print(cfg.DEVICE)
"""

import os
import sys
import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Try to load .env file ──────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        logger.info(f"[Config] Loaded .env from {_env_file}")
except ImportError:
    pass   # python-dotenv is optional; env vars can be set manually

# ── Base directory (always the folder containing this file) ───────────────
BASE_DIR = Path(__file__).parent.resolve()

# ── Model directory ───────────────────────────────────────────────────────
# Default: web_app/models/  (portable, offline-ready)
# Override: set MODEL_DIR=/absolute/path in .env
MODEL_DIR_RAW = os.environ.get("MODEL_DIR", "")
MODEL_DIR_DEFAULT = BASE_DIR / "models"


def _resolve_dir(env_key: str, default: Path) -> Path:
    """Read a Path from env; fall back to default. Always creates the dir."""
    raw = os.environ.get(env_key, "")
    p = Path(raw).resolve() if raw else default
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_file(env_key: str, default: Path) -> Path:
    """Read a file Path from env; fall back to default. Parent dir is created."""
    raw = os.environ.get(env_key, "")
    p = Path(raw).resolve() if raw else default
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_model_dir() -> Path:
    """Resolve MODEL_DIR: env override → ./models → HuggingFace default cache."""
    raw = os.environ.get("MODEL_DIR", "")
    if raw:
        p = Path(raw).resolve()
    else:
        p = BASE_DIR / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _configure_hf_env(model_dir: Path):
    """
    Set all required environment variables for offline model loading.
    Must be called BEFORE any import of transformers, huggingface_hub,
    or argostranslate.

    Directory layout inside MODEL_DIR:
        huggingface/
            models--Qwen--Qwen2.5-1.5B-Instruct/
            models--vinai--phobert-base-v2/
            models--PaddlePaddle--*/
        argos/
            packages/
    """
    hf_local = model_dir / "huggingface"
    hf_local.mkdir(parents=True, exist_ok=True)

    # HuggingFace: point to models/huggingface/ (models--* live directly here)
    os.environ.setdefault("HF_HOME",           str(hf_local))
    os.environ.setdefault("HF_HUB_CACHE",      str(hf_local))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_local))

    # Argos Translate: MUST be set before argostranslate is imported.
    # argostranslate reads ARGOS_PACKAGES_DIR at module import time to build
    # its package_dirs list — setting settings.data_dir after import does nothing.
    argos_packages = model_dir / "argos" / "packages"
    argos_packages.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ARGOS_PACKAGES_DIR",          str(argos_packages))
    os.environ.setdefault("ARGOS_TRANSLATE_PACKAGE_DIR", str(argos_packages))  # legacy

    # Offline mode: never attempt downloads if OFFLINE=1 in .env
    offline = os.environ.get("OFFLINE", "1")   # default ON (local-first)
    if offline == "1":
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        # Stanza Offline: Prevent check for updates and raw.githubusercontent.com calls
        os.environ["STANZA_RESOURCES_DIR"] = str(argos_packages)
    else:
        # Allow downloads (useful when online to fetch newer versions)
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        os.environ.pop("STANZA_RESOURCES_DIR", None)


    return hf_local


# ══════════════════════════════════════════════════════════════════════════════
#  DEVICE SELECTION
# ══════════════════════════════════════════════════════════════════════════════

def _select_device(requested: str = "auto") -> str:
    """
    Resolve the best available compute device.

    Priority (when requested == "auto"):
      1. CUDA  — if torch + CUDA GPU is available
      2. MPS   — if Apple Silicon (torch.backends.mps.is_available)
      3. CPU   — always available fallback

    The resolved device is logged once at startup.
    """
    req = requested.lower().strip()

    try:
        import torch
    except ImportError:
        logger.warning("[Config] PyTorch not installed — defaulting to cpu")
        return "cpu"

    if req == "cuda":
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            logger.info(f"[Config] Device: CUDA ({name})")
            return "cuda"
        logger.warning("[Config] CUDA requested but not available — falling back to cpu")
        return "cpu"

    if req == "mps":
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            logger.info("[Config] Device: MPS (Apple Silicon)")
            return "mps"
        logger.warning("[Config] MPS requested but not available — falling back to cpu")
        return "cpu"

    if req == "cpu":
        logger.info("[Config] Device: CPU (forced by config)")
        return "cpu"

    # "auto" — pick best available
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        logger.info(f"[Config] Device (auto): CUDA ({name})")
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        logger.info("[Config] Device (auto): MPS (Apple Silicon)")
        return "mps"
    logger.info("[Config] Device (auto): CPU")
    return "cpu"


def _select_dtype(device: str):
    """
    Choose the best floating-point dtype for the resolved device.

    - CUDA  → float16 (fast, VRAM-efficient)
    - MPS   → float16 (Apple driver supports it for most models)
    - CPU   → float32 (stable; float16 on CPU is slow and numerically fragile)

    Override with DTYPE env var: float16 | float32 | bfloat16
    """
    override = os.environ.get("DTYPE", "").lower()
    try:
        import torch
        _map = {
            "float16":  torch.float16,
            "fp16":     torch.float16,
            "float32":  torch.float32,
            "fp32":     torch.float32,
            "bfloat16": torch.bfloat16,
            "bf16":     torch.bfloat16,
        }
        if override in _map:
            logger.info(f"[Config] Dtype: {override} (from DTYPE env)")
            return _map[override]
        # Auto-select
        if device == "cuda":
            return torch.float16
        if device == "mps":
            return torch.float16
        return torch.float32      # CPU default
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  PLATFORM INFO
# ══════════════════════════════════════════════════════════════════════════════

def _platform_summary() -> str:
    bits = "64-bit" if sys.maxsize > 2**32 else "32-bit"
    return f"{platform.system()} {platform.release()} ({platform.machine()}, {bits})"


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG OBJECT
# ══════════════════════════════════════════════════════════════════════════════

class _Config:
    """
    Singleton configuration object populated at import time.
    All values are resolved once; changes to env vars after import are ignored.
    """

    def __init__(self):
        # ── Directories ──────────────────────────────────────────────────────
        self.BASE_DIR:    Path = BASE_DIR
        self.UPLOAD_DIR:  Path = _resolve_dir("UPLOAD_DIR",  BASE_DIR / "uploads")

        # MODEL_DIR: defaults to web_app/models/ (portable, offline-ready)
        self.MODEL_DIR:   Path = _resolve_model_dir()

        # ── Configure HuggingFace env vars BEFORE any HF/transformers imports ─
        # This redirects all HF downloads to models/huggingface/
        self.HF_DIR:      Path = _configure_hf_env(self.MODEL_DIR)

        # ── Argos Translate data directory ───────────────────────────────────
        self.ARGOS_DIR:   Path = self.MODEL_DIR / "argos"
        self.ARGOS_DIR.mkdir(parents=True, exist_ok=True)

        # ── Offline flag ──────────────────────────────────────────────────────
        self.OFFLINE:     bool = os.environ.get("OFFLINE", "1") == "1"

        # ── Database ─────────────────────────────────────────────────────────
        self.DB_PATH:     Path = _resolve_file("DB_PATH",    BASE_DIR / "paddleocr.db")

        # ── Server ───────────────────────────────────────────────────────────
        self.HOST:        str  = os.environ.get("HOST", "0.0.0.0")
        self.PORT:        int  = int(os.environ.get("PORT", "5001"))
        self.SECRET_KEY:  str  = os.environ.get("SECRET_KEY", "")  # filled later in app.py

        # ── Upload size limit (DoS protection) ───────────────────────────────
        # Caps the request body Flask will accept; applies to /api/upload and every
        # JSON endpoint. Without it a single huge request can exhaust disk/RAM.
        # Configurable via MAX_UPLOAD_MB (default 50 MB).
        self.MAX_UPLOAD_MB:      int = int(os.environ.get("MAX_UPLOAD_MB", "50"))
        self.MAX_CONTENT_LENGTH: int = self.MAX_UPLOAD_MB * 1024 * 1024

        # ── Session cookie hardening ─────────────────────────────────────────
        # HttpOnly + SameSite=Lax are always applied (safe over HTTP). The Secure
        # flag is gated here because the bundled dev server serves plain HTTP — set
        # SESSION_COOKIE_SECURE=1 when deployed behind HTTPS/TLS so cookies are
        # never sent in clear text.
        self.SESSION_COOKIE_SECURE: bool = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

        # ── Device ───────────────────────────────────────────────────────────
        _device_req      = os.environ.get("DEVICE", "auto")
        self.DEVICE:      str  = _select_device(_device_req)

        # ── Display timezone ────────────────────────────────────────────────
        # Timestamps are stored as UTC; this is the timezone used to render them
        # (admin templates via the vn_time Jinja filter; the SPA via Intl).
        self.DISPLAY_TZ: str = os.environ.get("DISPLAY_TZ", "Asia/Ho_Chi_Minh").strip()

        # ── OCR Engine Selection ────────────────────────────────────────────
        self.OCR_ENGINE: str = os.environ.get("OCR_ENGINE", "paddle").strip().lower()
        self.VIETOCR_DEVICE: str = os.environ.get("VIETOCR_DEVICE", self.DEVICE).strip().lower()
        self.VIETOCR_CONFIG: str = os.environ.get("VIETOCR_CONFIG", "vgg_transformer")
        _vietocr_default = self.MODEL_DIR / "vietocr" / f"{self.VIETOCR_CONFIG}.pth"
        self.VIETOCR_WEIGHTS: str = os.environ.get(
            "VIETOCR_WEIGHTS",
            str(_vietocr_default) if _vietocr_default.exists() else "",
        ).strip()

        # ── GLM-OCR engine (subprocess; OWN venv + local MLX model server) ───
        # GLM-OCR is a third-party SDK vendored INSIDE this repo at
        # <repo>/GLM-OCR. SmartDocs never imports it — the adapter shells out to
        # the `glmocr` CLI (running in the GLM venv) and reads the artifacts it
        # writes. GLM-OCR runs in its own venv because its torch/transformers
        # deps cannot co-install with paddle.
        #
        # Path resolution is CLEAN-CLONE friendly: with nothing configured, the
        # vendored copy at <repo>/GLM-OCR is used. Only an explicit env var points
        # elsewhere:
        #   GLM_OCR_DIR   – GLM-OCR directory (legacy alias: GLM_ROOT)
        #   GLM_SDK_PYTHON – interpreter that runs the `glmocr` CLI
        #   GLM_MLX_PYTHON – interpreter that runs the MLX model server
        # When the interpreters are not pinned, we pick the first that exists of
        # the repo-local .venv-mlx / .venv-sdk (setup_glm.sh creates .venv-mlx).
        _glm_dir_default = BASE_DIR / "GLM-OCR"
        _glm_dir = (os.environ.get("GLM_OCR_DIR")
                    or os.environ.get("GLM_ROOT")
                    or str(_glm_dir_default))
        self.GLM_ROOT:        Path = Path(_glm_dir)

        def _first_existing(candidates: list, fallback) -> str:
            for c in candidates:
                if Path(c).exists():
                    return str(c)
            return str(fallback)

        _glm_mlx_py = self.GLM_ROOT / ".venv-mlx" / "bin" / "python"
        _glm_sdk_py = self.GLM_ROOT / ".venv-sdk" / "bin" / "python"
        # SDK CLI: prefer a dedicated .venv-sdk, else the unified .venv-mlx.
        self.GLM_SDK_PYTHON:  str  = os.environ.get(
            "GLM_SDK_PYTHON", _first_existing([_glm_sdk_py, _glm_mlx_py], _glm_sdk_py))
        # MLX server: prefer .venv-mlx, else fall back to .venv-sdk.
        self.GLM_MLX_PYTHON:  str  = os.environ.get(
            "GLM_MLX_PYTHON", _first_existing([_glm_mlx_py, _glm_sdk_py], _glm_mlx_py))
        # Selfhosted config: prefer a repo-local mlx_config.yaml (setup_glm.sh
        # generates one), else the SDK's bundled glmocr/config.yaml.
        self.GLM_CONFIG_YAML: str  = os.environ.get(
            "GLM_CONFIG_YAML",
            _first_existing([self.GLM_ROOT / "mlx_config.yaml",
                             self.GLM_ROOT / "glmocr" / "config.yaml"],
                            self.GLM_ROOT / "mlx_config.yaml"))
        # Local MLX model server (OpenAI-compatible). Started manually via
        # tools/glm_serve.sh; the adapter health-checks it before each run.
        self.GLM_OCR_API_URL: str  = os.environ.get("GLM_OCR_API_URL", "http://localhost:8080")
        self.GLM_TIMEOUT:     int  = int(os.environ.get("GLM_TIMEOUT", "300"))

        # ── Qwen / AI Rewrite ────────────────────────────────────────────────
        # For Qwen on MPS: Apple's MPS driver crashes with tensors > 4GB.
        # When MPS is selected as the global device, Qwen still runs on CPU
        # unless the user explicitly sets QWEN_DEVICE=mps.
        _qwen_req         = os.environ.get("QWEN_DEVICE", "cpu" if self.DEVICE in ("mps", "cpu") else "auto")
        self.QWEN_DEVICE: str  = _select_device(_qwen_req)
        self.QWEN_MODEL:  str  = os.environ.get("QWEN_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        self.QWEN_DTYPE         = _select_dtype(self.QWEN_DEVICE)

        # ── AI Chat (separate model from AI Rewrite) ─────────────────────────
        # Primary  : Qwen2.5-3B-Instruct (better Vietnamese QA / document understanding)
        # Fallback : Qwen2.5-1.5B-Instruct (if 3B unavailable or OOM)
        # Device   : same CPU-safe default as AI Rewrite
        _chat_req              = os.environ.get("CHAT_DEVICE", "cpu" if self.DEVICE in ("mps", "cpu") else "auto")
        self.CHAT_DEVICE: str  = _select_device(_chat_req)
        self.CHAT_MODEL:  str  = os.environ.get("CHAT_MODEL",  "Qwen/Qwen2.5-3B-Instruct")
        self.FALLBACK_CHAT_MODEL: str = os.environ.get("FALLBACK_CHAT_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        self.CHAT_DTYPE        = _select_dtype(self.CHAT_DEVICE)

        # ── PhoBERT / Summarization ──────────────────────────────────────────
        # PhoBERT is small enough to run on MPS safely.
        self.PHOBERT_DEVICE: str = self.DEVICE  # uses the global best device
        self.PHOBERT_MODEL: str  = os.environ.get("PHOBERT_MODEL", "vinai/phobert-base-v2")
        self.PHOBERT_DTYPE       = _select_dtype(self.PHOBERT_DEVICE)

        # ── SQLAlchemy URI (computed from DB_PATH) ───────────────────────────
        # On Windows, sqlite:/// + absolute path needs 4 slashes:
        #   sqlite:////C:/Users/... or sqlite:///C:/Users/...
        # Path.as_posix() gives forward-slash paths on all platforms.
        self.SQLALCHEMY_URI: str = f"sqlite:///{self.DB_PATH.as_posix()}"

        # ── Platform info ─────────────────────────────────────────────────────
        self.PLATFORM: str = _platform_summary()

        # Log key config at startup
        mode = "OFFLINE (local models)" if self.OFFLINE else "ONLINE (downloads allowed)"
        logger.info(f"[Config] Mode: {mode}")
        logger.info(f"[Config] MODEL_DIR: {self.MODEL_DIR}")
        logger.info(f"[Config] HF cache : {self.HF_DIR / 'hub'}")
        logger.info(f"[Config] Argos dir: {self.ARGOS_DIR}")

    def check_models(self) -> dict:
        """
        Check which local models are available.
        Returns a dict of {model_name: bool (exists)}.
        """
        hf = self.HF_DIR   # models/huggingface/ — models--* live directly here
        results = {
            "qwen":       any(hf.glob("models--Qwen--*"))                   if hf.exists() else False,
            "phobert":    any(hf.glob("models--vinai--*"))                   if hf.exists() else False,
            "paddle_det": any(hf.glob("models--PaddlePaddle--*det*"))        if hf.exists() else False,
            "paddle_rec": any(hf.glob("models--PaddlePaddle--*rec*"))        if hf.exists() else False,
            "vietocr":    Path(self.VIETOCR_WEIGHTS).exists()                if self.VIETOCR_WEIGHTS else False,
            "argos":      any(self.ARGOS_DIR.glob("packages/*/"))            if self.ARGOS_DIR.exists() else False,
        }
        return results


    def summary(self) -> str:
        models = self.check_models()
        mode = "🔒 OFFLINE" if self.OFFLINE else "🌐 ONLINE"
        lines = [
            "=" * 56,
            "  SmartDocs Platform — Configuration",
            "=" * 56,
            f"  Platform   : {self.PLATFORM}",
            f"  Mode       : {mode}",
            f"  BASE_DIR   : {self.BASE_DIR}",
            f"  UPLOAD_DIR : {self.UPLOAD_DIR}",
            f"  DB_PATH    : {self.DB_PATH}",
            f"  MODEL_DIR  : {self.MODEL_DIR}",
            f"  HF cache   : {self.HF_DIR / 'hub'}",
            f"  Argos dir  : {self.ARGOS_DIR}",
            f"  DEVICE     : {self.DEVICE}  (global)",
            f"  OCR_ENGINE : {self.OCR_ENGINE}",
            f"  VIETOCR_CFG: {self.VIETOCR_CONFIG}",
            f"  VIETOCR_WTS: {self.VIETOCR_WEIGHTS or '(library default)'}",
            f"  QWEN_DEVICE: {self.QWEN_DEVICE}  (AI Rewrite)",
            f"  QWEN_MODEL : {self.QWEN_MODEL}",
            f"  CHAT_DEVICE: {self.CHAT_DEVICE}  (AI Chat)",
            f"  CHAT_MODEL : {self.CHAT_MODEL}",
            f"  CHAT_FALLBK: {self.FALLBACK_CHAT_MODEL}",
            "  ── Local Models ─────────────────────────────────",
            f"  Qwen      : {'✅' if models['qwen']     else '❌ MISSING — run tools/setup_offline.py'}",
            f"  PhoBERT   : {'✅' if models['phobert']  else '❌ MISSING — run tools/setup_offline.py'}",
            f"  Paddle det: {'✅' if models['paddle_det'] else '⚠️  will download on first OCR run'}",
            f"  Paddle rec: {'✅' if models['paddle_rec'] else '⚠️  will download on first OCR run'}",
            f"  VietOCR   : {'✅' if models['vietocr'] else '⚠️  using library default / configure VIETOCR_WEIGHTS'}",
            f"  Argos pkg : {'✅' if models['argos']    else '❌ MISSING — run tools/setup_offline.py'}",
            "=" * 56,
        ]
        return "\n".join(lines)


cfg = _Config()

def print_startup_diagnostics():
    """
    Requirement #8: Print detailed system and AI stability diagnostics at startup.
    """
    import torch
    try:
        import psutil
    except ImportError:
        psutil = None
    import os
    
    print("=" * 60)
    print("  SmartDocs Platform — AI Stability Diagnostics")
    print("=" * 60)
    
    # 1. Device Info
    mps_avail = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    cuda_avail = torch.cuda.is_available()
    
    print(f"  MPS Available   : {'✅ Yes' if mps_avail else '❌ No'}")
    print(f"  CUDA Available  : {'✅ Yes' if cuda_avail else '❌ No'}")
    print(f"  Resolved Global Device : {cfg.DEVICE}")
    
    # 2. RAM Usage
    if psutil:
        vm = psutil.virtual_memory()
        proc = psutil.Process(os.getpid())
        print(f"  System RAM      : {vm.total/1e9:.1f} GB total, {vm.available/1e9:.1f} GB free")
        print(f"  Process RSS     : {proc.memory_info().rss/1e6:.1f} MB")
    
    # 3. Model Configs
    print("\n  ── AI Chat Config ──")
    print(f"  Model           : {cfg.CHAT_MODEL}")
    print(f"  Device          : {cfg.CHAT_DEVICE}")
    print(f"  DType           : {cfg.CHAT_DTYPE}")
    
    # Estimate VRAM (rough)
    p_chat = 1.5 if "1.5B" in cfg.CHAT_MODEL else (3.0 if "3B" in cfg.CHAT_MODEL else 1.5)
    bytes_per_p = 2 if cfg.CHAT_DTYPE == torch.float16 or cfg.CHAT_DTYPE == torch.bfloat16 else 4
    est_chat = p_chat * bytes_per_p
    print(f"  Est. VRAM/RAM   : ~{est_chat:.1f} GB")
    
    print("\n  ── AI Rewrite Config ──")
    print(f"  Model           : {cfg.QWEN_MODEL}")
    print(f"  Device          : {cfg.QWEN_DEVICE}")
    print(f"  DType           : {cfg.QWEN_DTYPE}")
    
    p_rew = 1.5 if "1.5B" in cfg.QWEN_MODEL else 3.0
    bytes_per_rew = 2 if cfg.QWEN_DTYPE == torch.float16 or cfg.QWEN_DTYPE == torch.bfloat16 else 4
    est_rew = p_rew * bytes_per_rew
    print(f"  Est. VRAM/RAM   : ~{est_rew:.1f} GB")
    
    if mps_avail and (cfg.CHAT_DEVICE == "mps" or cfg.QWEN_DEVICE == "mps"):
        print("\n  ⚠️  STABILITY NOTICE (MPS):")
        print("  - Generation length is clamped to 128 tokens to avoid NDArray > 2**32 crashes.")
        print("  - KV cache may be disabled for long prompts.")
        print("  - Automatic CPU fallback is active.")
    
    print("=" * 60)
    print()
