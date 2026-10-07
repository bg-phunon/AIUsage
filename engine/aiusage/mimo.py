"""Xiaomi MiMo Token Plan — โควตารายเดือนนับเป็น credit

ต่างจาก Alibaba (ไม่ประกาศสูตร token → credit จึงต้องจดจุดจาก console): MiMo
ประกาศอัตรา credit ต่อ token แยกตามโมเดลและชนิด token เอง พร้อมยอด credit ต่อแผน
และตัวคูณกลางคืน % จึงคำนวณได้จาก log ตรงๆ
ที่มา: https://mimo.mi.com/docs/en-US/price/token-plan (ตรวจ 2026-10-07)

ยังเป็น "estimated" ไม่ใช่ตัวเลขทางการ เพราะ (1) log ของ Claude Code เห็นแค่ traffic
ที่ผ่าน Claude Code — OpenClaw/Codex/MiMo Claw ที่ใช้แผนเดียวกันมองไม่เห็น
(2) MiMo ไม่บอกว่า cache write คิดแบบไหน ที่นี่นับเป็น cache miss
"""

import calendar
from datetime import datetime, timezone
from typing import Dict, Optional

HOST_SUFFIX = "xiaomimimo.com"

# credit ต่อ token: (input cache hit, input cache miss, output)
CREDIT_RATES = {
    "mimo-v2.6-pro": (2.5, 300, 600),
    "mimo-v2.6-flash": (2, 100, 200),
    "mimo-v2.5-pro": (2.5, 300, 600),
    "mimo-v2.5": (2, 100, 200),
}

# credit ต่อเดือนของแผน Individual (Team มี standard/pro/max ยอดเท่ากัน)
PLAN_CREDITS = {
    "lite": 4_100_000_000,
    "standard": 11_000_000_000,
    "pro": 38_000_000_000,
    "max": 82_000_000_000,
}

# 00:00–08:00 เวลาปักกิ่ง = UTC 16:00–24:00 → กิน credit 0.8 เท่า
NIGHT_START_UTC_HOUR = 16
NIGHT_FACTOR = 0.8


def is_plan_host(host: str) -> bool:
    """token-plan-<region>.xiaomimimo.com — pay-as-you-go (api.) ไม่มีโควตาให้นับ"""
    bare = (host or "").split(":")[0].lower()
    return bare.endswith("." + HOST_SUFFIX) and bare.startswith("token-plan")


def _rates(model: Optional[str]):
    if not isinstance(model, str):
        return None
    name = model.strip().lower()
    if name.endswith("]") and "[" in name:   # mimo-v2.6-pro[1m]
        name = name[: name.index("[")]
    return CREDIT_RATES.get(name)


def credits(model: Optional[str], usage: dict, ts: datetime) -> Optional[float]:
    """credit ที่ call นี้กิน · None = โมเดลที่ไม่รู้อัตรา (ห้ามกลายเป็น 0)"""
    rates = _rates(model)
    if rates is None:
        return None
    hit, miss, out = rates

    def n(key):
        try:
            return max(0, int(usage.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    total = (n("cache_read_input_tokens") * hit
             + (n("input_tokens") + n("cache_creation_input_tokens")) * miss
             + n("output_tokens") * out)
    if ts.astimezone(timezone.utc).hour >= NIGHT_START_UTC_HOUR:
        total *= NIGHT_FACTOR
    return total


def _add_months(dt: datetime, months: int, day: int) -> datetime:
    """เลื่อนทีละเดือนโดยยึดวันเดิม — เดือนที่สั้นกว่าหนีบไว้ที่วันสุดท้าย"""
    index = dt.month - 1 + months
    year, month = dt.year + index // 12, index % 12 + 1
    return dt.replace(year=year, month=month,
                      day=min(day, calendar.monthrange(year, month)[1]))


def _parse_ts(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_plans(raw, now: datetime) -> Dict[str, dict]:
    """config ``mimoPlan: {"<โปรไฟล์ ccs>": {"plan": "pro", "resetAt": "...Z"}}``

    resetAt คือวันต่ออายุรอบใดรอบหนึ่ง (ดูจาก console) แผนต่ออายุเองทุกเดือน
    วันที่ผ่านไปแล้วจึงเลื่อนไปรอบถัดไปเอง ไม่ต้องกลับมาแก้ทุกเดือน
    คืน {profile: {"budget", "start", "resetAt"}}
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for profile, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        plan = entry.get("plan")
        budget = PLAN_CREDITS.get(plan.strip().lower()) if isinstance(plan, str) else None
        reset = _parse_ts(entry.get("resetAt"))
        if budget is None or reset is None:
            continue
        day = reset.day
        k = 0
        while _add_months(reset, k, day) <= now:
            k += 1
        while _add_months(reset, k - 1, day) > now:   # จดวันล่วงหน้าเกินเดือน
            k -= 1
        current = _add_months(reset, k, day)
        out[profile] = {"budget": budget, "resetAt": current,
                        "start": _add_months(reset, k - 1, day)}
    return out


def month_window(plan: dict, credits_used: float, unknown_calls: int) -> dict:
    """หน้าต่าง 1mo สำหรับ modelWindows · มี call ของโมเดลที่ไม่รู้อัตรา = lower_bound"""
    pct = min(100.0, credits_used / plan["budget"] * 100.0)
    return {"label": "1mo", "pct": round(pct, 2),
            "confidence": "lower_bound" if unknown_calls else "estimated",
            "resetAt": plan["resetAt"].isoformat().replace("+00:00", "Z")}
