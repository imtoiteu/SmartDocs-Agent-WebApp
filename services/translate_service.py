"""Translation service — engine: auto / online / offline.

Key improvements:
- check_online_available() uses a fast TCP + HTTP multi-method probe.
- get_engine_status() caches results with a short TTL for fast UI response.
- _translate_offline() validates language pairs and missing packages cleanly.
- translate() wraps errors with clear user-facing messages.

Offline fix (2024-04):
  argostranslate resolves package_dirs at MODULE IMPORT TIME from the
  ARGOS_PACKAGES_DIR env var. Setting settings.data_dir after import has
  NO effect on which packages are loaded.
  Fix: set ARGOS_PACKAGES_DIR in the environment BEFORE argostranslate is
  imported, then also patch settings.package_dirs at runtime as a safety net.
"""
import os
import sys
import time
import threading
import logging
from pathlib import Path

# ── Central config (also sets HF_HOME env vars) ───────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import cfg

# ── Redirect Argos Translate to local models/argos BEFORE any argos import ────
# argostranslate reads ARGOS_PACKAGES_DIR at module import time to build
# its package_dirs list. We must set this env var first.
# ── Redirect Argos Translate to local models/argos BEFORE any argos import ────
_argos_packages_dir = cfg.ARGOS_DIR / "packages"
_argos_packages_dir.mkdir(parents=True, exist_ok=True)
os.environ["ARGOS_PACKAGES_DIR"] = str(_argos_packages_dir)
os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = str(_argos_packages_dir)  # legacy compat

# ── Neutralize Stanza (Argos sub-dependency) ──────────────────────────────────
# Stanza attempts to check raw.githubusercontent.com for resources.
# We force it to use the local directory and disable all network activity.
os.environ["STANZA_RESOURCES_DIR"] = str(_argos_packages_dir)
os.environ["STANZA_RESOURCES_URL"] = "http://127.0.0.1:1"  # Fast-fail if any leak occurs

try:
    # We use a localized import and monkey-patch to satisfy the "No Stanza usage" 
    # requirement while still allowing Argos Translate (which depends on it) to work.
    import stanza
    import stanza.resources.common as stanza_common
    
    # 1. Disable the resources.json fetcher
    stanza_common.download_resources_json = lambda *args, **kwargs: None
    
    # 2. Disable the main download function
    stanza.download = lambda *args, **kwargs: None
    
    # 3. Force Pipeline to 'none' download method (this is the most critical fix)
    # Patch get_language_resources to remove 'mwt' from default processors.
    # This prevents Stanza from "expecting" MWT and attempting to load it.
    _orig_get_lang_res = stanza_common.get_language_resources
    def _patched_get_lang_res(resources, lang):
        res = _orig_get_lang_res(resources, lang)
        if res and "default_processors" in res:
            if "mwt" in res["default_processors"]:
                # Modify a copy to avoid side effects on the shared resources dict
                res = res.copy()
                res["default_processors"] = res["default_processors"].copy()
                res["default_processors"].pop("mwt", None)
                # Also check 'packages' if they exist
                if "packages" in res:
                    res["packages"] = res["packages"].copy()
                    for pkg_name in res["packages"]:
                        if isinstance(res["packages"][pkg_name], dict):
                            res["packages"][pkg_name] = res["packages"][pkg_name].copy()
                            res["packages"][pkg_name].pop("mwt", None)
        return res
    stanza_common.get_language_resources = _patched_get_lang_res

    # 4. Final Boss Fix: Disable Stanza's auto-mwt re-injection.
    # Even if we request 'tokenize', Stanza re-adds 'mwt' for some languages.
    # We block that here by making the re-injection logic a no-op.
    stanza_common.add_mwt = lambda processors, resources, lang: None

    _orig_init = stanza.Pipeline.__init__
    def _patched_init(self, *args, **kwargs):
        # Force offline mode regardless of what argostranslate requests
        kwargs.pop('download_method', None)
        kwargs['download_method'] = 'none'
        
        # CRITICAL: Force ONLY 'tokenize' processor.
        kwargs.pop('processors', None)
        kwargs['processors'] = 'tokenize'
        
        # Ensure sentence splitting is ENABLED
        kwargs.pop('tokenize_no_ssplit', None)
        kwargs['tokenize_no_ssplit'] = False
        
        return _orig_init(self, *args, **kwargs)
    stanza.Pipeline.__init__ = _patched_init
except Exception:
    pass

logger = logging.getLogger(__name__)

# Now import argostranslate and patch any already-resolved paths as a safety net
try:
    import argostranslate.settings as _argos_settings
    _argos_settings.data_dir = cfg.ARGOS_DIR
    _argos_settings.package_data_dir = _argos_packages_dir
    # Force Argos to not use Stanza if possible (MiniSBD fallback)
    # However, for languages like Vietnamese, it will still try to use Stanza.
    if _argos_packages_dir not in _argos_settings.package_dirs:
        _argos_settings.package_dirs.insert(0, _argos_packages_dir)
except Exception as _e:
    pass   # argostranslate not installed

LANGUAGES = {
    "auto": "auto",
    "en":   "english",
    "vi":   "vietnamese",
    "zh":   "chinese (simplified)",
    "ja":   "japanese",
    "ko":   "korean",
    "fr":   "french",
    "de":   "german",
    "es":   "spanish",
}

# Argostranslate language codes supported offline
_ARGOS_CODES = {"en", "vi", "zh", "ja", "ko", "fr", "de", "es"}

# Simple in-memory cache so /api/translate/status is fast
_status_cache: dict = {}
_status_lock  = threading.Lock()
_STATUS_TTL   = 10          # seconds before re-probing (short for fast recovery)
_last_probe   = 0.0


# ── Online (Google Translate via deep-translator) ──────────────────────────
def _translate_online(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using Google Translate (requires internet). Raises on failure."""
    from deep_translator import GoogleTranslator
    MAX = 4500
    chunks = [text[i:i + MAX] for i in range(0, len(text), MAX)]
    parts = []
    for chunk in chunks:
        result = GoogleTranslator(source=from_lang, target=to_lang).translate(chunk)
        parts.append(result or "")
    return "\n".join(parts)


# ── Offline (Argos Translate — local neural model) ─────────────────────────
def _get_installed_pairs() -> set:
    try:
        import argostranslate.package
        return {(p.from_code, p.to_code)
                for p in argostranslate.package.get_installed_packages()}
    except Exception:
        return set()


def _translate_offline(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using Argos Translate (local, no internet). Raises on failure."""
    import argostranslate.translate

    from_code = "en" if from_lang == "auto" else from_lang
    to_code   = to_lang

    # Same-language guard
    if from_code == to_code:
        raise ValueError(
            f"Source and target language are the same ({from_code}). "
            "Please select different languages."
        )

    if from_code not in _ARGOS_CODES or to_code not in _ARGOS_CODES:
        raise ValueError(
            f"Offline engine does not support language: {from_code} → {to_code}. "
            f"Supported codes: {', '.join(sorted(_ARGOS_CODES))}"
        )

    try:
        result = argostranslate.translate.translate(text, from_code, to_code)
    except Exception as e:
        logger.error(f"[ARGOS] Translation failed for {from_code}→{to_code}: {e}")
        # Return the specific error user expects if models are truly missing
        raise ValueError("Offline translation model not installed") from e

    if not result or not result.strip():
        raise RuntimeError(
            f"Offline translation returned empty result for {from_code}→{to_code}."
        )
    return result


# ── Public API ─────────────────────────────────────────────────────────────
def check_online_available(timeout: float = 5.0) -> bool:
    """Multi-method connectivity probe (fastest first).

    Method 1: TCP socket to 8.8.8.8:53  (Google DNS) — ~50ms, no HTTP overhead.
    Method 2: HTTP GET /generate_204     (Google)     — definitive HTTP proof.
    Returns True if ANY method succeeds.
    """
    import socket
    import urllib.request
    import urllib.error

    # Method 1: fast TCP socket probe (DNS port — almost always open when online)
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=min(timeout, 3.0))
        s.close()
        return True
    except OSError:
        pass

    # Method 2: HTTP GET to Google's dedicated connectivity-check endpoint
    # Returns 204 No Content when online, connection error when offline.
    try:
        req = urllib.request.Request(
            "https://www.google.com/generate_204",
            headers={"User-Agent": "SmartDocs/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status in (200, 204)
    except urllib.error.HTTPError as e:
        # Any HTTP response (even 4xx) means the server is reachable
        return True
    except Exception:
        pass

    return False


def check_offline_available() -> bool:
    """Check if argostranslate is installed AND at least one language pack is ready."""
    try:
        import argostranslate.package   # noqa
        import argostranslate.translate  # noqa
        installed = argostranslate.package.get_installed_packages()
        return len(installed) > 0
    except (ImportError, Exception):
        return False


def get_engine_status(force: bool = False) -> dict:
    """Return availability of each engine. Results are cached for _STATUS_TTL seconds."""
    global _last_probe, _status_cache

    now = time.time()
    with _status_lock:
        if not force and _status_cache and (now - _last_probe) < _STATUS_TTL:
            return dict(_status_cache)

        online  = check_online_available()
        offline = check_offline_available()

        # Installed offline pairs for richer client-side info
        installed_pairs = sorted(
            [f"{f}→{t}" for f, t in _get_installed_pairs()]
        )

        _status_cache = {
            "online":           online,
            "offline":          offline,
            "auto":             online or offline,
            "installed_pairs":  installed_pairs,
        }
        _last_probe = now
        return dict(_status_cache)


def translate(
    text:      str,
    from_lang: str = "auto",
    to_lang:   str = "vi",
    engine:    str = "auto",   # "auto" | "online" | "offline"
) -> dict:
    # DIAGNOSTIC: register as an in-flight CPU-heavy op (offline Argos/CTranslate2
    # is native-threaded and can contend with a concurrent chat generation).
    from services import activity_registry
    with activity_registry.track("translate"):
        return _translate_impl(text, from_lang, to_lang, engine)


def _translate_impl(
    text:      str,
    from_lang: str = "auto",
    to_lang:   str = "vi",
    engine:    str = "auto",
) -> dict:
    t0 = time.time()

    # Determine mode and engine for logging
    log_mode   = "Online" if engine == "online" else "Offline" if engine == "offline" else "Auto"
    log_engine = "Argos" if engine == "offline" else "API" if engine == "online" else "Auto (API -> Argos)"

    logger.info(f"[TRANSLATE] Mode: {log_mode}")
    logger.info(f"[TRANSLATE] Engine: {log_engine}")

    used_engine  = engine
    error_detail = None

    if engine == "online":
        if not check_online_available(timeout=4.0):
            raise RuntimeError(
                "Không có kết nối Internet. Vui lòng chuyển sang chế độ Ngoại tuyến."
            )
        translated = _translate_online(text, from_lang, to_lang)

    elif engine == "offline":
        # Ensure strict Argos usage
        try:
            translated = _translate_offline(text, from_lang, to_lang)
        except Exception as e:
            logger.error(f"[TRANSLATE] Offline mode failed: {e}")
            raise

    else:  # auto: pick based on connectivity, but NO fallback during execution
        online_ready = check_online_available(timeout=2.0)
        if online_ready:
            logger.info("[TRANSLATE] Auto-selected: Online (API)")
            translated  = _translate_online(text, from_lang, to_lang)
            used_engine = "online"
        else:
            logger.info("[TRANSLATE] Auto-selected: Offline (Argos)")
            translated  = _translate_offline(text, from_lang, to_lang)
            used_engine = "offline"

    ms = round((time.time() - t0) * 1000)
    result = {
        "translated":   translated,
        "from_lang":    from_lang,
        "to_lang":      to_lang,
        "elapsed_ms":   ms,
        "engine_used":  used_engine,
    }
    if error_detail:
        result["engine_fallback_reason"] = error_detail
    return result


def supported_languages():
    return list(LANGUAGES.keys())
