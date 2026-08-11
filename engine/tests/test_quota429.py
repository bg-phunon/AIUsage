import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import quota429  # noqa: E402

TS = datetime(2026, 8, 7, 14, 42, 6, tzinfo=timezone.utc)

# ข้อความจริงจาก transcript — อย่าแต่งใหม่ให้สวยกว่าของจริง
WEEK_MSG = ("API Error: Request rejected (429) · Your token-plan 1-week quota has been "
            "exhausted. The quota will reset at 08-12 13:03:00 UTC.")
HOUR_MSG = ("API Error: Request rejected (429) · Your token-plan 5-hour quota has been "
            "exhausted. The quota will reset at 08-05 18:03:00 UTC.")


class ParseHitTest(unittest.TestCase):
    def test_parses_the_real_weekly_message(self):
        window, reset = quota429.parse_hit(WEEK_MSG, TS)
        self.assertEqual(window, "week")
        # 13:03 UTC = 20:03 UTC+7 ตรงกับที่ dashboard แสดง
        self.assertEqual(reset, datetime(2026, 8, 12, 13, 3, 0, tzinfo=timezone.utc))

    def test_parses_the_real_five_hour_message(self):
        window, reset = quota429.parse_hit(HOUR_MSG, datetime(2026, 8, 5, 14, 13, tzinfo=timezone.utc))
        self.assertEqual(window, "5h")
        self.assertEqual(reset, datetime(2026, 8, 5, 18, 3, 0, tzinfo=timezone.utc))

    def test_year_rolls_forward_across_december(self):
        """event ปลายธันวา รีเซ็ตต้นมกรา — ปีต้องขยับ ไม่ใช่ย้อนไป 12 เดือน"""
        ts = datetime(2026, 12, 31, 22, 0, tzinfo=timezone.utc)
        msg = ("Your token-plan 1-week quota has been exhausted. "
               "The quota will reset at 01-02 10:00:00 UTC.")
        _, reset = quota429.parse_hit(msg, ts)
        self.assertEqual(reset.year, 2027)

    def test_reset_a_few_hours_in_the_past_keeps_same_year(self):
        """เจอ hit ตอน 19:00 ที่บอก reset 18:03 วันเดียวกัน — อย่าดันไปปีหน้า"""
        ts = datetime(2026, 8, 5, 19, 0, tzinfo=timezone.utc)
        _, reset = quota429.parse_hit(HOUR_MSG, ts)
        self.assertEqual(reset.year, 2026)

    def test_unrelated_text_is_none(self):
        self.assertIsNone(quota429.parse_hit("rate limited, try again", TS))
        self.assertIsNone(quota429.parse_hit("token-plan is great value", TS))
        self.assertIsNone(quota429.parse_hit(None, TS))

    def test_glm_bracket_errors_do_not_match(self):
        """[1308] เป็นของ GLM คนละกลไก — ต้องไม่หลงเข้ามาที่นี่"""
        msg = "[1308][Usage limit reached for 5 hour. Your limit will reset at 2026-07-23 17:25:53]"
        self.assertIsNone(quota429.parse_hit(msg, TS))


class MergeHitsTest(unittest.TestCase):
    def test_latest_reset_wins_per_window(self):
        early = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
        late = datetime(2026, 8, 12, 13, 3, tzinfo=timezone.utc)
        merged = quota429.merge_hits([("week", early), ("week", late), ("5h", early)])
        self.assertEqual(merged["week"], late)
        self.assertEqual(merged["5h"], early)

    def test_empty_is_empty(self):
        self.assertEqual(quota429.merge_hits([]), {})


if __name__ == "__main__":
    unittest.main()
