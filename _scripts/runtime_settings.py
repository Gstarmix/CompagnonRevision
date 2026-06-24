import json
import logging
from pathlib import Path
from typing import Any, Optional
from config import (
    RUNTIME_SETTINGS_PATH,
    SCHEMA_VERSION_RUNTIME_SETTINGS,
    SECRETS_DIR,
)
from utils import atomic_write_json, now_iso
logger = logging.getLogger(__name__)
DEFAULT_SESSION_THRESHOLD_PCT = 85
DEFAULT_WEEKLY_THRESHOLD_PCT = 90
DEFAULT_REPLAY_HARD_CAP_EXCHANGES = 300
DEFAULT_CONTEXT_CAPS: dict[str, int] = {
    "cm_transcription_words": 4000,
    "perso_material_words": 6000,
    "correction_total_chars": 80_000,
}
DEFAULT_LAST_SELECTION: dict[str, object] = {
    "matiere": "",
    "type": "",
    "num": "",
    "exo": "full",
    "annee": "",
    "mode": "colle",
    "colle_format": "mixte",
    "corrige_anchor": "strict",
    "enable_audio": False,
    "skip_quota": False,
    "workspace_root": "",
    "workspace_focus_subdir": "",
}
DEFAULT_WORKSPACE_PRESETS: list[str] = []
DEFAULT_WORKSPACE_EXCLUDES: list[str] = []
def _default_settings() -> dict:
    return {
        "schema_version": SCHEMA_VERSION_RUNTIME_SETTINGS,
        "session_threshold_pct": DEFAULT_SESSION_THRESHOLD_PCT,
        "weekly_threshold_pct": DEFAULT_WEEKLY_THRESHOLD_PCT,
        "replay_hard_cap_exchanges": DEFAULT_REPLAY_HARD_CAP_EXCHANGES,
        "context_caps": dict(DEFAULT_CONTEXT_CAPS),
        "workspace_presets": list(DEFAULT_WORKSPACE_PRESETS),
        "workspace_excludes": list(DEFAULT_WORKSPACE_EXCLUDES),
        "last_selection": dict(DEFAULT_LAST_SELECTION),
        "updated_at": None,
    }
def load_settings(path: Optional[Path] = None) -> dict:
    if path is None:
        path = RUNTIME_SETTINGS_PATH
    if not path.exists():
        return _default_settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(
            "runtime_settings illisible (%s) : fallback defauts", e,
        )
        return _default_settings()
    if not isinstance(raw, dict):
        logger.warning("runtime_settings n'est pas un dict : fallback defauts")
        return _default_settings()
    return _merge_with_defaults(raw)
def save_settings(data: dict, path: Optional[Path] = None) -> None:
    if path is None:
        path = RUNTIME_SETTINGS_PATH
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    payload = _merge_with_defaults(data)
    payload["schema_version"] = SCHEMA_VERSION_RUNTIME_SETTINGS
    payload["updated_at"] = now_iso()
    atomic_write_json(path, payload)
def _merge_with_defaults(raw: dict) -> dict:
    out = _default_settings()
    for key in ("session_threshold_pct", "weekly_threshold_pct",
                "replay_hard_cap_exchanges"):
        if key in raw and isinstance(raw[key], (int, float)):
            out[key] = int(raw[key])
    if isinstance(raw.get("context_caps"), dict):
        for k, default in DEFAULT_CONTEXT_CAPS.items():
            v = raw["context_caps"].get(k, default)
            if isinstance(v, (int, float)):
                out["context_caps"][k] = int(v)
    if isinstance(raw.get("last_selection"), dict):
        for k, default in DEFAULT_LAST_SELECTION.items():
            if k in raw["last_selection"]:
                v = raw["last_selection"][k]
                if isinstance(default, bool):
                    out["last_selection"][k] = bool(v)
                else:
                    out["last_selection"][k] = "" if v is None else str(v)
    for list_key in ("workspace_presets", "workspace_excludes"):
        if isinstance(raw.get(list_key), list):
            cleaned: list[str] = []
            for item in raw[list_key]:
                if isinstance(item, str) and item.strip():
                    s = item.strip()
                    if s not in cleaned:
                        cleaned.append(s)
            out[list_key] = cleaned
    if "updated_at" in raw:
        out["updated_at"] = raw["updated_at"]
    return out
def get_session_threshold_pct() -> int:
    return load_settings()["session_threshold_pct"]
def get_weekly_threshold_pct() -> int:
    return load_settings()["weekly_threshold_pct"]
def get_replay_hard_cap_exchanges() -> int:
    return load_settings()["replay_hard_cap_exchanges"]
def get_workspace_presets() -> list[str]:
    return list(load_settings()["workspace_presets"])
def get_workspace_excludes() -> list[str]:
    return list(load_settings()["workspace_excludes"])
def update_workspace_presets(presets: list[str]) -> None:
    current = load_settings()
    cleaned: list[str] = []
    for p in presets:
        if isinstance(p, str) and p.strip():
            s = p.strip()
            if s not in cleaned:
                cleaned.append(s)
    current["workspace_presets"] = cleaned
    save_settings(current)
def update_workspace_excludes(excludes: list[str]) -> None:
    current = load_settings()
    cleaned: list[str] = []
    for p in excludes:
        if isinstance(p, str) and p.strip():
            s = p.strip()
            if s not in cleaned:
                cleaned.append(s)
    current["workspace_excludes"] = cleaned
    save_settings(current)
def get_context_cap(name: str) -> int:
    if name not in DEFAULT_CONTEXT_CAPS:
        raise KeyError(f"context cap inconnu : {name!r}")
    return load_settings()["context_caps"][name]
def update_settings(**kwargs: Any) -> dict:
    current = load_settings()
    for key, value in kwargs.items():
        if key in ("session_threshold_pct", "weekly_threshold_pct",
                   "replay_hard_cap_exchanges"):
            current[key] = int(value)
        elif key == "context_caps" and isinstance(value, dict):
            for cap_key, cap_val in value.items():
                if cap_key in DEFAULT_CONTEXT_CAPS:
                    current["context_caps"][cap_key] = int(cap_val)
        else:
            logger.warning("update_settings: cle ignoree %r", key)
    save_settings(current)
    return current
def get_last_selection() -> dict:
    return load_settings()["last_selection"]
def update_last_selection(**kwargs: Any) -> dict:
    current = load_settings()
    for key, value in kwargs.items():
        if key not in DEFAULT_LAST_SELECTION:
            logger.warning("update_last_selection: cle ignoree %r", key)
            continue
        default = DEFAULT_LAST_SELECTION[key]
        if isinstance(default, bool):
            current["last_selection"][key] = bool(value)
        else:
            current["last_selection"][key] = "" if value is None else str(value)
    save_settings(current)
    return current