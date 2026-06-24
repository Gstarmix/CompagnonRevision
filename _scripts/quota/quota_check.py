import logging
import sys
from config import ARSENAL_PATH
from runtime_settings import (
    DEFAULT_SESSION_THRESHOLD_PCT,
    DEFAULT_WEEKLY_THRESHOLD_PCT,
    get_session_threshold_pct,
    get_weekly_threshold_pct,
)
if str(ARSENAL_PATH) not in sys.path:
    sys.path.insert(0, str(ARSENAL_PATH))
from claude_usage import Quota, fetch_usage
logger = logging.getLogger(__name__)
THRESHOLD_5H_BLOCK_SESSION_DEFAULT = DEFAULT_SESSION_THRESHOLD_PCT
THRESHOLD_7D_BLOCK_SESSION_DEFAULT = DEFAULT_WEEKLY_THRESHOLD_PCT
THRESHOLD_5H_WARN_INSESSION = 90
def can_start_session() -> tuple[bool, str]:
    try:
        usage = fetch_usage()
    except Exception as e:
        logger.warning(
            "Quota check echoue (%s : %s) : autorisation par defaut",
            type(e).__name__, e,
        )
        return True, ""
    session_threshold = get_session_threshold_pct()
    weekly_threshold = get_weekly_threshold_pct()
    if usage.session_pct > session_threshold:
        return False, (
            f"Quota 5h a {usage.session_pct:.0f}% (seuil {session_threshold}%), "
            f"reset {_fmt_reset(usage.session_resets_at)}"
        )
    if usage.weekly_pct > weekly_threshold:
        return False, (
            f"Quota hebdo a {usage.weekly_pct:.0f}% (seuil {weekly_threshold}%), "
            f"reset {_fmt_reset(usage.weekly_resets_at)}"
        )
    return True, ""
def get_usage_snapshot() -> dict:
    try:
        usage = fetch_usage()
    except Exception as e:
        return {"error": "unavailable", "detail": f"{type(e).__name__}: {e}"}
    return _quota_to_dict(usage)
def _fmt_reset(dt) -> str:
    if dt is None:
        return "(inconnu)"
    return dt.isoformat(timespec="minutes")
def _quota_to_dict(q: Quota) -> dict:
    def iso(dt):
        return dt.isoformat() if dt is not None else None
    return {
        "session_pct": q.session_pct,
        "session_resets_at": iso(q.session_resets_at),
        "weekly_pct": q.weekly_pct,
        "weekly_resets_at": iso(q.weekly_resets_at),
        "weekly_sonnet_pct": q.weekly_sonnet_pct,
        "weekly_sonnet_resets_at": iso(q.weekly_sonnet_resets_at),
        "extra_used_credits": q.extra_used_credits,
        "extra_limit_credits": q.extra_limit_credits,
        "extra_pct": q.extra_pct,
        "fetched_at": iso(q.fetched_at),
    }