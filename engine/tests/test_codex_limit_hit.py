"""Codex ชนลิมิตแล้ว แต่ rate_limits ไม่เคยรายงาน 100% — ต้องอ่านจาก error event

เคสจริง 2026-09-11: rate_limits ของถังจริงไต่จาก 52% ถึง 79% (08:40:05Z) แล้วเงียบไป
สี่ชั่วโมง ก่อนที่ 12:43:58Z จะมี event แบบนี้โผล่มา

    {"type": "event_msg", "payload": {"type": "task_complete", "error": {
        "message": "You've hit your usage limit. ... try again at Sep 15th, 2026 2:37 PM.",
        "codex_error_info": "usage_limit_exceeded"}}}

แอปค้างที่ 79% ทั้งที่ OpenAI ประกาศไปแล้วว่าหมด — เพราะเอนจินอ่านแต่ rate_limits
และตัวกรองบรรทัดข้ามทุกบรรทัดที่ไม่มีคำว่า token_count ทิ้งตั้งแต่ด่านแรก

เวลาใน "try again at" คือเวลารีเซ็ตของหน้าต่างที่ชน แสดงเป็นเวลาท้องถิ่นของเครื่อง
ตัดวินาทีทิ้ง (2:37 PM +07 = 07:37 UTC ตรงกับ resets_at 07:37:11Z ของ weekly)
จึงใช้บอกได้ว่าหน้าต่างไหนหมด — เหมือนที่ 429 ของ token-plan เป็นคำประกาศว่า 100%
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_limit_hit", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

BKK = timezone(timedelta(hours=7))
NOW = datetime(2026, 9, 11, 13, 0, tzinfo=timezone.utc)
WEEK_END = datetime(2026, 9, 15, 7, 37, 11, tzinfo=timezone.utc)
READ_AT = datetime(2026, 9, 11, 8, 40, 5, tzinfo=timezone.utc)
HIT_AT = datetime(2026, 9, 11, 12, 43, 58, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def message(retry):
    return ("You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
            "to purchase more credits or try again at %s." % retry)


def reading_record(ts, pct, minutes=10080, end=WEEK_END):
    return {"timestamp": iso(ts), "type": "event_msg",
            "payload": {"type": "token_count",
                        "info": {"last_token_usage": {"total_tokens": 10}},
                        "rate_limits": {"limit_id": "codex", "limit_name": None,
                                        "primary": {"used_percent": pct,
                                                    "window_minutes": minutes,
                                                    "resets_at": end.timestamp()},
                                        "secondary": None}}}


def hit_record(ts, retry):
    return {"timestamp": iso(ts), "type": "event_msg",
            "payload": {"type": "task_complete", "last_agent_message": None,
                        "error": {"message": message(retry),
                                  "codex_error_info": "usage_limit_exceeded"}}}


class RetryTimeTest(unittest.TestCase):
    """สองรูปที่เจอในล็อกจริง: "2:19 PM" (วันเดียวกัน) กับ "Sep 15th, 2026 2:37 PM" """

    def test_full_date_form(self):
        got = engine.parse_retry_time(message("Sep 15th, 2026 2:37 PM"), HIT_AT, BKK)
        self.assertEqual(got, datetime(2026, 9, 15, 7, 37, tzinfo=timezone.utc))

    def test_ordinal_suffixes_all_parse(self):
        for text, day in (("Aug 1st, 2026 9:00 AM", 1), ("Aug 2nd, 2026 9:00 AM", 2),
                          ("Aug 3rd, 2026 9:00 AM", 3), ("Aug 27th, 2026 9:00 AM", 27)):
            got = engine.parse_retry_time(message(text), HIT_AT, BKK)
            self.assertEqual(got, datetime(2026, 8, day, 2, 0, tzinfo=timezone.utc), text)

    def test_time_only_means_the_same_local_day(self):
        """เคสจริง 2026-09-10: ชนตอน 03:09:56Z (10:09 น.) บอก "2:19 PM" = 07:19Z"""
        hit = datetime(2026, 9, 10, 3, 9, 56, tzinfo=timezone.utc)
        got = engine.parse_retry_time(message("2:19 PM"), hit, BKK)
        self.assertEqual(got, datetime(2026, 9, 10, 7, 19, tzinfo=timezone.utc))

    def test_time_only_that_already_passed_today_means_tomorrow(self):
        """ชนตอนห้าทุ่มครึ่ง บอก "2:19 AM" — ตีสองของวันนี้ผ่านไปแล้ว ต้องเป็นพรุ่งนี้"""
        hit = datetime(2026, 9, 10, 16, 30, tzinfo=timezone.utc)   # 23:30 +07
        got = engine.parse_retry_time(message("2:19 AM"), hit, BKK)
        self.assertEqual(got, datetime(2026, 9, 10, 19, 19, tzinfo=timezone.utc))

    def test_twelve_oclock_edges(self):
        self.assertEqual(engine.parse_retry_time(message("Sep 15th, 2026 12:05 AM"), HIT_AT, BKK),
                         datetime(2026, 9, 14, 17, 5, tzinfo=timezone.utc))
        self.assertEqual(engine.parse_retry_time(message("Sep 15th, 2026 12:05 PM"), HIT_AT, BKK),
                         datetime(2026, 9, 15, 5, 5, tzinfo=timezone.utc))

    def test_unreadable_is_none_not_a_guess(self):
        self.assertIsNone(engine.parse_retry_time("You've hit your usage limit.", HIT_AT, BKK))
        self.assertIsNone(engine.parse_retry_time(message("soon"), HIT_AT, BKK))
        self.assertIsNone(engine.parse_retry_time(None, HIT_AT, BKK))


class StatsCaptureTest(unittest.TestCase):
    """ตัวกรองบรรทัดต้องปล่อย event ชนลิมิตผ่าน — ไม่งั้นทุกอย่างข้างล่างไม่มีความหมาย"""

    def setUp(self):
        self.saved = (engine.now_utc, engine.LOCAL_TZ)
        engine.now_utc = lambda: NOW
        engine.LOCAL_TZ = BKK

    def tearDown(self):
        engine.now_utc, engine.LOCAL_TZ = self.saved

    def stats(self, records):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "sessions", "2026", "09", "11")
            os.makedirs(d)
            with open(os.path.join(d, "rollout.jsonl"), "w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
            return engine.codex_stats(tmp)

    def test_the_hit_event_is_captured(self):
        cs = self.stats([reading_record(READ_AT, 79.0),
                         hit_record(HIT_AT, "Sep 15th, 2026 2:37 PM")])
        self.assertEqual(cs["limitHit"]["at"], HIT_AT)
        self.assertEqual(cs["limitHit"]["retry"],
                         datetime(2026, 9, 15, 7, 37, tzinfo=timezone.utc))

    def test_the_newest_hit_wins(self):
        cs = self.stats([hit_record(HIT_AT - timedelta(hours=3), "2:19 PM"),
                         hit_record(HIT_AT, "Sep 15th, 2026 2:37 PM")])
        self.assertEqual(cs["limitHit"]["at"], HIT_AT)

    def test_no_hit_means_none(self):
        self.assertIsNone(self.stats([reading_record(READ_AT, 79.0)])["limitHit"])

    def test_replay_of_the_real_day_ends_at_a_hundred(self):
        """เล่นซ้ำลำดับจริงของ 2026-09-11 ทั้งเส้น — จากล็อกถึงฟิลด์ที่ UI อ่าน"""
        cs = self.stats([reading_record(READ_AT - timedelta(hours=2), 52.0),
                         reading_record(READ_AT, 79.0),
                         hit_record(HIT_AT, "Sep 15th, 2026 2:37 PM")])
        out = engine.codex_fields(cs, NOW)
        self.assertEqual(out["weekPct"], 100.0,
                         "OpenAI ประกาศว่าหมดแล้ว แต่แอปยังโชว์เลขเก่า 79%")
        self.assertEqual(out["weekConfidence"], "valid")
        self.assertEqual(out["activeLimit"], "weekly")


class ApplyTest(unittest.TestCase):
    """คำประกาศชนลิมิตทับเฉพาะหน้าต่างที่เวลารีเซ็ตตรงกัน และเฉพาะตอนที่มันใหม่กว่า"""

    @staticmethod
    def cs(win_minutes=10080, end=WEEK_END, pct=79.0, read_at=READ_AT, hit=None):
        return {"tokens": 1, "lastActivity": read_at,
                "windows": {"primary": {"win": {"used_percent": pct,
                                                "window_minutes": win_minutes,
                                                "resets_at": end.timestamp()},
                                        "ts": read_at, "seen": []}},
                "limitHit": hit}

    def test_weekly_hit_reports_a_hundred_until_reset(self):
        out = engine.codex_fields(self.cs(hit={"at": HIT_AT, "retry": WEEK_END.replace(second=0)}), NOW)
        self.assertEqual(out["weekPct"], 100.0)
        self.assertEqual(out["weekConfidence"], "valid",
                         "เป็นคำประกาศจากผู้ให้บริการเอง ไม่ใช่ค่าที่เราเดา")
        self.assertEqual(out["activeLimit"], "weekly")
        self.assertEqual(out["severity"], "critical")

    def test_five_hour_hit_marks_the_session_window(self):
        end = NOW + timedelta(hours=2)
        out = engine.codex_fields(self.cs(win_minutes=300, end=end,
                                          hit={"at": HIT_AT, "retry": end.replace(second=0)}), NOW)
        self.assertEqual(out["pct"], 100.0)
        self.assertEqual(out["activeLimit"], "session")

    def test_a_reading_newer_than_the_hit_wins(self):
        """กดใช้ใบรีเซ็ตแล้วโควตากลับมา — เลขจริงที่มาทีหลังต้องชนะคำประกาศเก่า"""
        out = engine.codex_fields(self.cs(pct=4.0, read_at=HIT_AT + timedelta(minutes=10),
                                          hit={"at": HIT_AT, "retry": WEEK_END.replace(second=0)}),
                                  NOW + timedelta(minutes=20))
        self.assertEqual(out["weekPct"], 4.0)
        self.assertIsNone(out["activeLimit"])

    def test_after_the_window_resets_the_hit_no_longer_applies(self):
        later = WEEK_END + timedelta(minutes=5)
        out = engine.codex_fields(self.cs(hit={"at": HIT_AT, "retry": WEEK_END.replace(second=0)}), later)
        self.assertNotEqual(out["weekPct"], 100.0)
        self.assertIsNone(out["activeLimit"])

    def test_a_retry_time_matching_no_window_changes_nothing(self):
        """ไม่รู้ว่าหน้าต่างไหนหมด — ห้ามเดาเอาหน้าต่างที่มีอยู่ไปใส่ 100%"""
        out = engine.codex_fields(self.cs(hit={"at": HIT_AT, "retry": NOW + timedelta(hours=1)}), NOW)
        self.assertEqual(out["weekPct"], 79.0)
        self.assertIsNone(out["activeLimit"])

    def test_unreadable_retry_with_a_single_window_still_applies(self):
        """ข้อความอ่านไม่ออก แต่มีหน้าต่างให้เลือกแค่อันเดียว — ไม่มีอะไรให้สับสน"""
        out = engine.codex_fields(self.cs(hit={"at": HIT_AT, "retry": None}), NOW)
        self.assertEqual(out["weekPct"], 100.0)

    def test_no_hit_changes_nothing(self):
        out = engine.codex_fields(self.cs(), NOW)
        self.assertEqual(out["weekPct"], 79.0)
        self.assertIsNone(out["activeLimit"])
        self.assertIsNone(out["severity"])


if __name__ == "__main__":
    unittest.main()
