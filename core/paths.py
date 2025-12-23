from __future__ import annotations

from pathlib import Path

APP_DISPLAY_NAME = "BCX Comic Lister"

# Legacy (older builds)
_LEGACY_ROOT = Path.home() / "BCX"
_LEGACY_STAGING = _LEGACY_ROOT / "staging" / "clz_images"
_LEGACY_PROCESSED = _LEGACY_ROOT / "processed"

# Preferred (deployable) locations
_APP_SUPPORT = Path.home() / "Library" / "Application Support" / APP_DISPLAY_NAME
_LOGS_DIR = Path.home() / "Library" / "Logs" / "BCX"

_STAGING_ROOT = _APP_SUPPORT / "Staged Images"
_PROCESSED_ROOT = _APP_SUPPORT / "Processed Images"
_WEB_PROFILE_ROOT = _APP_SUPPORT / "clz_web_profile"


def logs_dir() -> Path:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return _LOGS_DIR


def app_support_dir() -> Path:
    _APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    return _APP_SUPPORT


def web_profile_dir(*, prefer_legacy: bool = True) -> Path:
    d = _WEB_PROFILE_ROOT
    d.mkdir(parents=True, exist_ok=True)
    return d


def staging_root_dir(*, prefer_legacy: bool = True) -> Path:
    # Prefer legacy if it exists and contains files (don’t break existing installs).
    if prefer_legacy and _LEGACY_STAGING.exists():
        try:
            if any(_LEGACY_STAGING.rglob("*")):
                _LEGACY_STAGING.mkdir(parents=True, exist_ok=True)
                return _LEGACY_STAGING
        except Exception:
            pass

    _STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    return _STAGING_ROOT


def processed_root_dir(*, prefer_legacy: bool = True) -> Path:
    if prefer_legacy and _LEGACY_PROCESSED.exists():
        try:
            if any(_LEGACY_PROCESSED.rglob("*")):
                _LEGACY_PROCESSED.mkdir(parents=True, exist_ok=True)
                return _LEGACY_PROCESSED
        except Exception:
            pass

    _PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    return _PROCESSED_ROOT


def ensure_all_dirs() -> None:
    app_support_dir()
    logs_dir()
    staging_root_dir(prefer_legacy=True)
    processed_root_dir(prefer_legacy=True)
    web_profile_dir(prefer_legacy=True)