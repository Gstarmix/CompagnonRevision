"""
runtime_settings.py : settings éditables à chaud (seuils quota, caps contexte).

Persisté dans ``_secrets/runtime_settings.json``. Lu à chaque appel des
fonctions ``get_*`` pour que les changements depuis la GUI prennent effet
immédiatement sans redémarrage du compagnon.

Schéma v1 :
    {
      "schema_version": 1,
      "session_threshold_pct": 85,
      "weekly_threshold_pct": 90,
      "context_caps": {
        "cm_transcription_words": 4000,
        "perso_material_words": 6000,
        "correction_total_chars": 80000
      },
      "updated_at": "2026-05-05T15:00:00+02:00"
    }

Tolérant : si le fichier est absent / corrompu, retourne les défauts.
"""

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


# ============================================================ Défauts

DEFAULT_SESSION_THRESHOLD_PCT = 85
DEFAULT_WEEKLY_THRESHOLD_PCT = 90

#: Phase A.8.6 : seuil au-delà duquel la reprise bascule du replay complet
#: au résumé Gemini Flash ≤120 mots (cf. `_should_replay_transcript`).
#: 300 par défaut = quasi-jamais déclenché dans l'usage courant (sessions
#: typiques 30-80 tours, max observé ~115).
DEFAULT_REPLAY_HARD_CAP_EXCHANGES = 300

DEFAULT_CONTEXT_CAPS: dict[str, int] = {
    "cm_transcription_words": 4000,
    "perso_material_words": 6000,
    "correction_total_chars": 80_000,
}

#: Mémoire de la dernière sélection du formulaire de lancement (Phase A.7.1).
#: Restaurée au boot de la GUI, sauvée à chaque clic Lancer. Les types
#: indicatifs ici servent de typage pour le merge : strings vides et bools.
DEFAULT_LAST_SELECTION: dict[str, object] = {
    "matiere": "",
    "type": "",
    "num": "",
    "exo": "full",
    "annee": "",
    "mode": "colle",
    # Phase v15.7.4 : format colle (oral|photos|mixte). Restauré au
    # boot GUI, sauvé au clic Lancer. Champ additif, merge avec defaults
    # via _merge_with_defaults.
    "colle_format": "mixte",
    # Phase v15.7.30 : ancrage corrigé (strict|consultatif|aucun). Idem
    # colle_format : restauré au boot, sauvé au clic Lancer. Default
    # "strict" = comportement v0.5 historique.
    "corrige_anchor": "strict",
    "enable_audio": False,
    "skip_quota": False,
    # Phase A.10.13 (2026-05-14) : `ignore_enonce` retiré de la
    # persistance. Reste une option ponctuelle (checkbox 🎲 dans le
    # form) mais décochée à chaque boot. User : « je n'ai pas vu de
    # paramètre pour activer ça dans le GUI ». La persistance avait
    # propagé un clic d'erreur antérieur à toutes les séances.
    # Phase A.9 : source workspace. Quand non-vide, le compagnon bascule
    # en `mode=workspace` au démarrage : tutorat sur un dossier disque
    # arbitraire (codebase, docs, CV, etc.) avec accès Read/Grep/Glob
    # scopé via cwd. Cf. PROMPT_SYSTEME_WORKSPACE.md.
    "workspace_root": "",
    # Sous-dossier de focus optionnel (relatif au workspace_root) pour
    # zoomer l'arbre injecté en contexte initial.
    "workspace_focus_subdir": "",
}

# ============================================================ Workspace (Phase A.9)
# Stockés au top-level (pas dans last_selection) car partagés entre
# sessions et pas spécifiques à la dernière sélection.

#: Liste de chemins workspace fréquents (Quick presets dans la GUI Tk).
DEFAULT_WORKSPACE_PRESETS: list[str] = []

#: Liste de patterns d'exclusion personnalisés, en plus des défauts
#: hard-codés dans `prompt_builder.WORKSPACE_DEFAULT_EXCLUDES`. Une entrée
#: par pattern (basename ou *.ext).
DEFAULT_WORKSPACE_EXCLUDES: list[str] = []


def _default_settings() -> dict:
    return {
        "schema_version": SCHEMA_VERSION_RUNTIME_SETTINGS,
        "session_threshold_pct": DEFAULT_SESSION_THRESHOLD_PCT,
        "weekly_threshold_pct": DEFAULT_WEEKLY_THRESHOLD_PCT,
        # Phase A.8.6 : éditable depuis la GUI Tk panneau Quota, lu en live
        # par app._should_replay_transcript à chaque reprise de session.
        "replay_hard_cap_exchanges": DEFAULT_REPLAY_HARD_CAP_EXCHANGES,
        "context_caps": dict(DEFAULT_CONTEXT_CAPS),
        # Phase A.9 : workspace presets & excludes globaux (partagés entre
        # sessions). Le `workspace_root` courant est dans last_selection.
        "workspace_presets": list(DEFAULT_WORKSPACE_PRESETS),
        "workspace_excludes": list(DEFAULT_WORKSPACE_EXCLUDES),
        "last_selection": dict(DEFAULT_LAST_SELECTION),
        "updated_at": None,
    }


# ============================================================ I/O

def load_settings(path: Optional[Path] = None) -> dict:
    """Charge les settings, fallback aux défauts si absent ou malformé.

    Garantit que tous les champs attendus sont présents (merge avec les
    défauts) : si tu ajoutes un nouveau champ au schéma, les anciens
    fichiers continuent de fonctionner sans migration explicite.

    ``path`` résolu à l'appel (pas en default-arg) pour que les tests
    qui ``patch.object(rs, "RUNTIME_SETTINGS_PATH", ...)`` agissent aussi
    sur les appels sans argument.
    """
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
    """Atomic write des settings. Met à jour ``updated_at``."""
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
    # Phase A.9 : workspace_presets et workspace_excludes (list[str])
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


# ============================================================ Accesseurs typés

def get_session_threshold_pct() -> int:
    return load_settings()["session_threshold_pct"]


def get_weekly_threshold_pct() -> int:
    return load_settings()["weekly_threshold_pct"]


def get_replay_hard_cap_exchanges() -> int:
    """Phase A.8.6 : seuil tours au-delà duquel la reprise bascule en résumé."""
    return load_settings()["replay_hard_cap_exchanges"]


def get_workspace_presets() -> list[str]:
    """Phase A.9 : liste des chemins workspace en presets rapide."""
    return list(load_settings()["workspace_presets"])


def get_workspace_excludes() -> list[str]:
    """Phase A.9 : patterns d'exclusion personnalisés (additifs aux défauts)."""
    return list(load_settings()["workspace_excludes"])


def update_workspace_presets(presets: list[str]) -> None:
    """Atomic write des presets workspace. Dédup + strip auto."""
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
    """Atomic write des patterns d'exclusion workspace."""
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
    """``name`` ∈ DEFAULT_CONTEXT_CAPS. KeyError si nom inconnu."""
    if name not in DEFAULT_CONTEXT_CAPS:
        raise KeyError(f"context cap inconnu : {name!r}")
    return load_settings()["context_caps"][name]


def update_settings(**kwargs: Any) -> dict:
    """Patch partiel : merge les kwargs avec les settings actuels et sauve.

    Les clés acceptées : ``session_threshold_pct``, ``weekly_threshold_pct``,
    ``context_caps`` (dict). Toute autre clé est ignorée avec warning.
    """
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
    """Snapshot des dernières valeurs du formulaire de lancement (GUI)."""
    return load_settings()["last_selection"]


def update_last_selection(**kwargs: Any) -> dict:
    """Patch partiel sur ``last_selection``. Clés inconnues ignorées.

    Coerce ``bool`` pour les flags (``enable_audio``, ``skip_quota``) et
    ``str`` pour les autres champs. Atomic write.
    """
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
