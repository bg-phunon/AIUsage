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
    # None = หน้าต่างยังไม่เริ่มเดิน (percent 0) — ไม่ใช่ "ไม่รู้เวลา"
    resets_at: Optional[datetime]
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
        raw_percent = lim.get("percent")
        percent = float(raw_percent or 0)
        # ไม่มีเวลารีเซ็ตแล้วยังรับไว้ได้กรณีเดียว: บอกมาตรงๆ ว่าใช้ไป 0%
        # แปลว่ายังไม่ได้ใช้อะไรเลย หน้าต่างจึงยังไม่เริ่มเดิน ศูนย์นั้นคือคำตอบที่รู้จริง
        # — มีเลขแต่ไม่บอกวันหมดอายุ = ค้างจอตลอดกาล ส่วนไม่มีฟิลด์ percent เลย
        # = แถวขยะที่ไม่ได้บอกอะไร ทั้งสองแบบต้องทิ้ง
        if resets is None and not (isinstance(raw_percent, (int, float))
                                   and not isinstance(raw_percent, bool)
                                   and percent == 0):
            continue
        scope_obj = (lim.get("scope") or {}).get("model") or {}
        windows.append(Window(
            kind=str(lim.get("kind") or "unknown"),
            percent=percent,
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


def _ms(raw) -> Optional[datetime]:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return datetime.fromtimestamp(raw / 1000, timezone.utc)


def read_unused_reset_hint(config_dir: str, now: datetime) -> Optional[dict]:
    """ใบรีเซ็ตลิมิตจาก `unusedLimitResetStatusCache` ที่ CLI (≥ 2.1.322) จดไว้เอง

    CLI ถาม server ด้วย `?cedar_ember=1` แล้วจด {accountUuid, holdsUnusedReset,
    checkedAt, validUntil} · validUntil = min(checkedAt + 3 วัน, วันหมดอายุของใบ)
    จึงรู้แค่ "มีอย่างน้อยหนึ่งใบ" ไม่รู้จำนวน ไม่รู้วันหมดอายุจริง
    `false` ห้ามอ่านเป็นศูนย์ — CLI เขียน false ทั้งตอนไม่เหลือใบและตอน eligible false
    คืนรูปเดียวกับ clilive.reset_state พร้อม `atLeast: True`
    """
    for path in _config_paths(config_dir):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        cache = data.get("unusedLimitResetStatusCache")
        account = (data.get("oauthAccount") or {}).get("accountUuid")
        if not isinstance(cache, dict) or not account:
            continue
        # สลับบัญชีใน config dir เดิม — แคชของบัญชีก่อนไม่ใช่ของเรา (CLI ก็เช็กแบบนี้)
        if cache.get("accountUuid") != account or cache.get("holdsUnusedReset") is not True:
            return None
        checked, valid = _ms(cache.get("checkedAt")), _ms(cache.get("validUntil"))
        if checked is None or valid is None or checked > now or valid <= now:
            return None
        return {"count": 1, "atLeast": True, "expiring": [], "nextAvailableAt": None}
    return None


def window_confidence(window: Window, fetched_at: datetime,
                      last_activity: Optional[datetime],
                      now: datetime) -> str:
    if window.resets_at is None:
        # ยังไม่มีหน้าต่างเดินอยู่ จึงไม่มีอะไรหมดอายุ — แต่ถ้าใช้งานหลังเวลา fetch
        # ศูนย์ก้อนนั้นเป็นได้แค่ขอบล่าง เหมือนหน้าต่างปกติที่ข้อมูลตามไม่ทัน
        if last_activity is not None and last_activity > fetched_at:
            return LOWER_BOUND
        return VALID
    if now >= window.resets_at:
        if last_activity is None or last_activity < window.resets_at:
            return CONFIRMED_ZERO
        return UNSURE
    if last_activity is not None and last_activity > fetched_at:
        return LOWER_BOUND
    return VALID
