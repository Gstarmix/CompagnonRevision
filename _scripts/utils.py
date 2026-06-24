import json
import logging
import os
import time as _time_mod
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import TIMEZONE
logger = logging.getLogger(__name__)
_REPLACE_RETRY_DELAYS_S = (0.05, 0.15, 0.4, 1.0, 2.0)
def _replace_with_retry(src: Path, dst: Path) -> None:
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
    try:
        os.replace(str(src), str(dst))
        return
    except PermissionError as e:
        last_err = e
    if last_err is not None:
        raise last_err
def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        _replace_with_retry(tmp, path)
    except PermissionError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
def now_iso() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")
def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
def seconds_since(iso_string: Optional[str]) -> Optional[float]:
    if not iso_string:
        return None
    try:
        past = parse_iso(iso_string)
    except (ValueError, TypeError):
        return None
    return (datetime.now(TIMEZONE) - past).total_seconds()