"""BytePlus ModelArk Coding Plan — % ต่อหน้าต่าง 5 ชม. / 7 วัน / 30 วัน จาก token ใน log

ที่มา: docs.byteplus.com/en/docs/modelark/coding-plan-personal-plan-overview (ตรวจ 2026-10-10)
และหน้า console (Package usage limit) ที่ผู้ใช้ถ่ายมา 2026-10-10

**เอกสารบอกเพดานเป็น "จำนวน request" แต่ของจริงไม่ใช่** — เคสจริง 2026-10-10:
8 request (รวม 1.01M token, cache read 83%) = session 36.71% · 7-day 6.15% ·
30-day 3.07% ถ้านับ request จะได้ 0.4% ตารางในเอกสาร (Lite ~1,900/12,000/24,000)
เป็นแค่ค่าประมาณจากโมเดล dola-seed-2.0-lite ตามที่ FAQ ยอมรับเอง จึงนับเป็น token
(สูตรเดียวกับ ``total_tokens`` ของเอนจิน) แล้วหารด้วยเพดาน token ต่อหน้าต่าง

เพดานปริยายวัดจากจุดเดียวนั้น: 1,013,033 token ÷ % ของแต่ละหน้าต่าง → Lite
~2.76M / 16.5M / 33.0M (สัดส่วน 1 : 6 : 12) · Pro = 5 เท่าตามเอกสาร (ยังไม่เคยวัด)
ยังไม่รู้ว่า BytePlus ถ่วงน้ำหนัก cache read / output ต่างจาก input ไหม — จดจุดใหม่
ใน config ``anchor`` แล้วเพดานจะ calibrate ใหม่จาก log ของหน้าต่างตอนนั้นเอง

หน้าต่าง (ตรงกับเวลารีเซ็ตบน console ถึงระดับนาที):
- 5 ชม. นับจาก request แรก ไม่ปัดลงต้นชั่วโมงแบบ Claude
- 7 วัน รีเซ็ตวันจันทร์ 00:00 UTC+8 (ap-southeast-1 · ตั้ง ``utcOffset`` ได้)
- 30 วัน = รอบสมาชิก ซื้อวันที่ 10 → ใช้ได้ถึง 23:59 ของวันที่ 10 เดือนหน้า
  → รีเซ็ต 00:00 วันที่ 11 · ``resetAt`` คือเวลานั้น ``startAt`` คือ Start time ของ
  รอบแรก (รอบแรกเริ่มกลางวัน ไม่ใช่ตอนรีเซ็ต)

ยังเป็น "estimated" เพราะ traffic จากเครื่องมืออื่นที่ใช้แผนเดียวกัน (Ark CLI,
Cursor, Cline, OpenCode) ไม่อยู่ใน log ของ Claude Code
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from . import mimo as _mimo

HOST_SUFFIX = "bytepluses.com"
PLAN_PATH = "/api/coding"

# เพดาน token ต่อหน้าต่าง (5 ชม., 7 วัน, 30 วัน)
LITE_CAPS = (2_760_000, 16_470_000, 33_000_000)
PLAN_CAPS = {
    "lite": LITE_CAPS,
    "pro": tuple(cap * 5 for cap in LITE_CAPS),
}

DEFAULT_UTC_OFFSET = 8
SESSION = timedelta(hours=5)
WINDOWS = ("session", "week", "month")

Series = List[Tuple[datetime, int]]


def is_plan_endpoint(host: str, path: str) -> bool:
    """ark.<region>.bytepluses.com/api/coding — /api/v3 คือ pay-as-you-go ไม่กินโควตาแผน"""
    bare = (host or "").split(":")[0].lower()
    if not (bare == HOST_SUFFIX or bare.endswith("." + HOST_SUFFIX)):
        return False
    path = (path or "").rstrip("/")
    return path == PLAN_PATH or path.startswith(PLAN_PATH + "/")


def _pct(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0 < value <= 100 else None


def _month_bounds(reset: datetime, tz: timezone, at: datetime):
    """(start, resetAt) ของรอบสมาชิกที่ครอบ ``at`` — เลื่อนทีละเดือนจากวันรีเซ็ตใดก็ได้"""
    local = reset.astimezone(tz)
    day, k = local.day, 0
    while _mimo._add_months(local, k, day) <= at:
        k += 1
    while _mimo._add_months(local, k - 1, day) > at:
        k -= 1
    return (_mimo._add_months(local, k - 1, day).astimezone(timezone.utc),
            _mimo._add_months(local, k, day).astimezone(timezone.utc))


def parse_plans(raw, now: datetime) -> Dict[str, dict]:
    """config ``byteplusPlan``::

        {"<โปรไฟล์ ccs>": {"plan": "lite", "resetAt": "...Z", "startAt": "...Z",
                           "utcOffset": 8,
                           "anchor": {"at": "...Z", "session": 36.71, "week": 6.15, "month": 3.07}}}

    resetAt ไม่บังคับ — ไม่มีก็ได้แค่ 5 ชม. กับ 7 วัน
    คืน {profile: {"caps", "tz", "reset", "startAt", "anchor"}}
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for profile, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        plan = entry.get("plan")
        caps = PLAN_CAPS.get(plan.strip().lower()) if isinstance(plan, str) else None
        if caps is None:
            continue
        offset = entry.get("utcOffset", DEFAULT_UTC_OFFSET)
        if not isinstance(offset, (int, float)) or isinstance(offset, bool) or abs(offset) > 14:
            offset = DEFAULT_UTC_OFFSET
        anchor = None
        raw_anchor = entry.get("anchor")
        if isinstance(raw_anchor, dict):
            at = _mimo._parse_ts(raw_anchor.get("at"))
            pcts = {w: _pct(raw_anchor.get(w)) for w in WINDOWS}
            if at is not None and at <= now and any(v is not None for v in pcts.values()):
                anchor = {"at": at, **pcts}
        out[profile] = {"caps": caps, "tz": timezone(timedelta(hours=offset)),
                        "reset": _mimo._parse_ts(entry.get("resetAt")),
                        "startAt": _mimo._parse_ts(entry.get("startAt")),
                        "anchor": anchor}
    return out


def earliest_needed(plan: dict, now: datetime) -> datetime:
    """log ต้องย้อนไปถึงไหน — หน้าต่างปัจจุบันทุกใบ และหน้าต่างของจุด anchor"""
    points = [now - timedelta(days=8)]
    for at in (now, (plan["anchor"] or {}).get("at")):
        if at is None:
            continue
        points.append(week_start(at, plan["tz"]) - SESSION)
        month = month_window(plan, at)
        if month is not None:
            points.append(month[0])
    return min(points)


def week_start(at: datetime, tz: timezone) -> datetime:
    local = at.astimezone(tz)
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc)


def month_window(plan: dict, at: datetime):
    if plan["reset"] is None:
        return None
    start, reset = _month_bounds(plan["reset"], plan["tz"], at)
    first = plan["startAt"]
    if first is not None and start < first < reset:
        start = first
        # รอบแรกยาวเกินเดือนนิดหน่อย (ซื้อ 10 ต.ค. 18:12 → รีเซ็ต 00:00 วันที่ 11 พ.ย.)
        # เส้นที่ตกไม่ถึงเดือนหลังวันซื้อ (00:00 วันที่ 11 ต.ค.) จึงไม่ใช่รอบจริง
        if reset - first < timedelta(days=28):
            reset = _month_bounds(plan["reset"], plan["tz"], reset)[1]
    elif first is not None and first < start and start - first < timedelta(days=28):
        start = first      # หลังเส้นปลอมนั้นไปแล้ว ยังเป็นรอบแรกอยู่
    elif first is not None and reset <= first:
        return None
    return start, reset


def session_window(series: Series, at: datetime):
    """(start, tokens) ของหน้าต่าง 5 ชม. ที่ครอบ ``at`` — นับจาก request แรกของหน้าต่าง"""
    start, used = None, 0
    for ts, tokens in sorted(series):
        if ts > at:
            break
        if start is None or ts >= start + SESSION:
            start, used = ts, 0
        used += tokens
    if start is None or at >= start + SESSION:
        return None
    return start, used


def _used(series: Series, start: datetime, at: datetime) -> int:
    return sum(tokens for ts, tokens in series if start <= ts <= at)


def window_usage(plan: dict, series: Series, at: datetime) -> Dict[str, Optional[tuple]]:
    """{window: (tokens, resetAt) | None} ณ เวลา ``at``"""
    out: Dict[str, Optional[tuple]] = {}
    session = session_window(series, at)
    out["session"] = (session[1], session[0] + SESSION) if session else None
    monday = week_start(at, plan["tz"])
    out["week"] = (_used(series, monday, at), monday + timedelta(days=7))
    month = month_window(plan, at)
    out["month"] = (_used(series, month[0], at), month[1]) if month else None
    return out


def calibrated_caps(plan: dict, series: Series) -> Tuple[int, int, int]:
    """เพดานจากจุดที่จดจาก console · หน้าต่างไหนวัดไม่ได้ใช้ค่าปริยาย"""
    caps = list(plan["caps"])
    anchor = plan["anchor"]
    if anchor is None:
        return tuple(caps)
    usage = window_usage(plan, series, anchor["at"])
    for i, window in enumerate(WINDOWS):
        pct, used = anchor.get(window), usage.get(window)
        if pct is not None and used is not None and used[0] > 0:
            caps[i] = int(used[0] / (pct / 100.0))
    return tuple(caps)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def plan_fields(plan: dict, series: Series, now: datetime) -> dict:
    """ช่อง pct/weekPct/modelWindows ของแถว · series = (เวลา, token) ทุก request ของแผน รวมทุกบัญชี"""
    caps = dict(zip(WINDOWS, calibrated_caps(plan, series)))
    usage = window_usage(plan, series, now)
    fields = {"pct": 0.0, "confidence": "estimated", "resetAt": None,
              "weekPct": None, "weekConfidence": "estimated", "weekResetAt": None,
              "modelWindows": []}

    def pct(window):
        return min(100.0, usage[window][0] / caps[window] * 100.0)

    if usage["session"] is not None:
        fields["pct"] = round(pct("session"), 1)
        fields["resetAt"] = _iso(usage["session"][1])
    fields["weekPct"] = round(pct("week"), 1)
    fields["weekResetAt"] = _iso(usage["week"][1])
    if usage["month"] is not None:
        fields["modelWindows"].append({
            "label": "30d", "pct": round(pct("month"), 2),
            "confidence": "estimated", "resetAt": _iso(usage["month"][1])})
    return fields
