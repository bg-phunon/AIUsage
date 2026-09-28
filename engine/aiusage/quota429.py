"""พาร์สข้อความ 429 ของ token-plan (Qwen Cloud) — แหล่งความจริงที่ไม่ต้องมี auth

dashboard ของ qwencloud.com ใช้ cookie ของ console จึง sync ตรงๆ ไม่ได้
แต่ตัว endpoint บอกสถานะมาในข้อความ 429 ครบถ้วน:

    Your token-plan 5-hour quota has been exhausted. The quota will reset at 08-05 18:03:00 UTC.
    Your token-plan 1-week quota has been exhausted. The quota will reset at 08-12 13:03:00 UTC.

ตราบใดที่เวลารีเซ็ตยังไม่ถึง หน้าต่างนั้นคือ 100% แน่นอน — เป็นคำประกาศ
จากผู้ให้บริการเอง ไม่ใช่การประมาณ (ตรวจกับ dashboard แล้วเวลาตรงกันเป๊ะ)
"""

import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

_HIT_RE = re.compile(
    r"token[- ]plan\s+(?P<win>5-hour|1-week|1-month)\s+quota has been exhausted"
    r".*?reset at\s+(?P<md>\d{2}-\d{2})\s+(?P<hms>\d{2}:\d{2}:\d{2})\s*UTC",
    re.IGNORECASE | re.DOTALL,
)

# "1-month" ยังไม่เคยเห็นของจริง — เดาจากรูปแบบสองตัวแรกสำหรับแผนรายเดือนของ
# Alibaba Cloud ถ้าข้อความจริงต่างไปแค่จะไม่ match ไม่ได้แปลผิด
_WINDOW_KEY = {"5-hour": "5h", "1-week": "week", "1-month": "month"}


def parse_hit(text: str, event_ts: datetime) -> Optional[Tuple[str, datetime]]:
    """คืน (window, reset_at) จากข้อความ 429 หรือ None ถ้าไม่ใช่

    ข้อความไม่มีปี — เดาจากปีของ event แล้วขยับไปปีถัดไปถ้าได้เวลาที่
    ย้อนหลังเกิน 1 วัน (กันเคสข้าม ธ.ค. → ม.ค. โดยยังยอมรับ reset
    ที่ผ่านมาแล้วไม่กี่ชั่วโมงในวันเดียวกัน)
    """
    if not isinstance(text, str):
        return None
    m = _HIT_RE.search(text)
    if not m:
        return None
    window = _WINDOW_KEY[m.group("win").lower()]
    month, day = (int(x) for x in m.group("md").split("-"))
    hh, mm, ss = (int(x) for x in m.group("hms").split(":"))
    try:
        reset = datetime(event_ts.year, month, day, hh, mm, ss, tzinfo=timezone.utc)
    except ValueError:
        return None
    if (event_ts - reset).total_seconds() > 86400:
        try:
            reset = reset.replace(year=event_ts.year + 1)
        except ValueError:
            return None
    return window, reset


def merge_hits(hits) -> Dict[str, datetime]:
    """รวมหลาย hit ต่อหน้าต่าง เก็บเวลารีเซ็ตล่าสุด — hit ใหม่ทับ hit เก่าเสมอ"""
    out: Dict[str, datetime] = {}
    for window, reset in hits:
        if window not in out or reset > out[window]:
            out[window] = reset
    return out
