"""
utils.py : helpers transverses (atomic write JSON, ISO timestamps).

Importé par session_state.py, parser.py, quota_check.py, etc.

Cf. CLAUDE.md §3.4 et ARCHITECTURE.md §6.3.
"""

import json
import logging
import os
import time as _time_mod
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import TIMEZONE

logger = logging.getLogger(__name__)

# Phase Z.8.7 : retry sur os.replace pour OneDrive / antivirus Windows.
# Sur Windows, OneDrive (et certains antivirus) lockent brièvement les
# fichiers fraîchement écrits pour les indexer/synchroniser. `os.replace`
# lance alors PermissionError [WinError 5] sur la cible. Le lock dure
# typiquement 50-500 ms. On retry avec un backoff exponentiel doux.
_REPLACE_RETRY_DELAYS_S = (0.05, 0.15, 0.4, 1.0, 2.0)  # cumulé ~3.6s max


def _replace_with_retry(src: Path, dst: Path) -> None:
    """os.replace + retry sur PermissionError (lock OneDrive/antivirus Windows).

    Tente jusqu'à 6 fois (1ʳᵉ + 5 retries) avec backoff exponentiel.
    Lève la dernière PermissionError si tout échoue.
    """
    last_err: Optional[BaseException] = None
    for attempt, delay in enumerate(_REPLACE_RETRY_DELAYS_S, start=1):
        try:
            os.replace(str(src), str(dst))
            if attempt > 1:
                logger.info(
                    "atomic_write: os.replace OK après %d tentatives (target=%s)",
                    attempt, dst.name,
                )
            return
        except PermissionError as e:
            last_err = e
            logger.warning(
                "atomic_write: PermissionError sur replace (tentative %d/%d, "
                "retry dans %.2fs, target=%s) : %s",
                attempt, len(_REPLACE_RETRY_DELAYS_S) + 1, delay, dst.name, e,
            )
            _time_mod.sleep(delay)
    # Dernier essai sans sleep (le caller doit voir la vraie erreur)
    try:
        os.replace(str(src), str(dst))
        return
    except PermissionError as e:
        last_err = e
    if last_err is not None:
        raise last_err


def atomic_write_json(path: Path, data: dict) -> None:
    """Écrit data en JSON dans path de façon atomique (.tmp + os.replace).

    Crée les dossiers parents si absents. Encodage utf-8 sans escape ASCII
    (les accents et emojis restent lisibles en clair dans le JSON).

    Phase Z.8.7 : retry sur ``os.replace`` pour absorber les locks
    transitoires de OneDrive / antivirus Windows. Cf. ``_replace_with_retry``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        _replace_with_retry(tmp, path)
    except PermissionError:
        # En dernier recours, on essaie de supprimer le .tmp pour ne pas
        # laisser de fichier résiduel qui polluerait l'arbo. Si même ça
        # échoue, on laisse : la PermissionError remonte vers le caller.
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def now_iso() -> str:
    """Heure courante en ISO 8601 timezone-aware Europe/Paris.

    Format : ``2026-05-02T19:30:00+02:00`` (résolution seconde).
    """
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def parse_iso(s: str) -> datetime:
    """Parse un ISO 8601 (suffixe ``Z`` accepté) en datetime aware."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def seconds_since(iso_string: Optional[str]) -> Optional[float]:
    """Secondes écoulées depuis l'ISO timestamp donné.

    Retourne ``None`` si l'argument est nul ou non parsable. Utilisé pour
    détecter les sessions reprenables (last_alive ancien), cf.
    ARCHITECTURE.md §1.3.
    """
    if not iso_string:
        return None
    try:
        past = parse_iso(iso_string)
    except (ValueError, TypeError):
        return None
    return (datetime.now(TIMEZONE) - past).total_seconds()
