"""อ่าน cachedUsageUtilization ที่ Claude Code เขียนไว้ใน .claude.json"""

import json
import os
from datetime import datetime, timezone
from typing import List, NamedTuple, Optional

CONFIRMED_ZERO = "zero"
VALID = "valid"
LOWER_BOUND = "lower_bound"
UNSURE = "unsure"


class Window(NamedTuple):
    kind: str
    percent: float
    resets_at: datetime
    severity: str
    scope: Optional[str]
    is_active: bool


class Utilization(NamedTuple):
    fetched_at: datetime
    windows: List[Window]


def _parse_ts(raw) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _config_paths(config_dir: str):
    stripped = config_dir.rstrip("/")
    return (os.path.join(config_dir, ".claude.json"), stripped + ".json")


def windows_from_limits(raw_limits) -> List[Window]:
    """แปลง limits (รูปเดียวกันทั้งในแคชและ response สดจาก endpoint) เป็น Window"""
    windows = []
    for lim in raw_limits or []:
        if not isinstance(lim, dict):
            continue
        resets = _parse_ts(lim.get("resets_at"))
        if resets is None:
            continue
        scope_obj = (lim.get("scope") or {}).get("model") or {}
        windows.append(Window(
            kind=str(lim.get("kind") or "unknown"),
            percent=float(lim.get("percent") or 0),
            resets_at=resets,
            severity=str(lim.get("severity") or "normal"),
            scope=scope_obj.get("display_name") or None,
            is_active=bool(lim.get("is_active")),
        ))
    return windows


def read_utilization(config_dir: str) -> Optional[Utilization]:
    for path in _config_paths(config_dir):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        cached = (data or {}).get("cachedUsageUtilization")
        if not isinstance(cached, dict):
            continue
        fetched_ms = cached.get("fetchedAtMs")
        if not isinstance(fetched_ms, (int, float)):
            continue
        fetched_at = datetime.fromtimestamp(fetched_ms / 1000, timezone.utc)
        windows = windows_from_limits((cached.get("utilization") or {}).get("limits"))
        if windows:
            return Utilization(fetched_at=fetched_at, windows=windows)
    return None


def window_confidence(window: Window, fetched_at: datetime,
                      last_activity: Optional[datetime],
                      now: datetime) -> str:
    if now >= window.resets_at:
        if last_activity is None or last_activity < window.resets_at:
            return CONFIRMED_ZERO
        return UNSURE
    if last_activity is not None and last_activity > fetched_at:
        return LOWER_BOUND
    return VALID
