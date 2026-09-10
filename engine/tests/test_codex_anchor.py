"""จุดยึดโควตา Codex จากหน้า usage — แบบเดียวกับที่ Qwen ใช้อยู่

หลัง Codex เปลี่ยนแผน rate_limits ในล็อกกลายเป็นช่องเปล่า (0% ค้าง เวลารีเซ็ตเลื่อน
ตามนาฬิกา) แต่หน้าเว็บของ OpenAI ยังบอกตัวเลขจริง — และ token ที่นับได้ก็เทียบกลับ
เป็น % ไม่ได้ เพราะอัตรา token ต่อ 1% ที่วัดจากล็อกของแผนเก่าไหลจาก 443k ลงไป 375k
(คลาด ~15%) แปลว่า % ของ OpenAI ไม่ได้นับ token ตรงๆ

จุดยึดคือ "% ที่ใช้ไปแล้ว ณ เวลาหนึ่ง" ที่ผู้ใช้จดมาจากหน้าเว็บ โควตามีแต่ใช้เพิ่ม
ไม่มีคืน ค่านั้นจึงเป็น lower bound ที่ซื่อสัตย์จนกว่าหน้าต่างจะรีเซ็ต
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_anchor", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


class ParseTest(unittest.TestCase):
    def test_reads_both_windows(self):
        a = engine.parse_codex_anchor({
            "at": iso(NOW - timedelta(hours=1)),
            "session": {"usedPct": 12, "resetAt": iso(NOW + timedelta(hours=3))},
            "weekly": {"usedPct": 33, "resetAt": iso(NOW + timedelta(days=4))},
        })
        self.assertEqual(a["session"]["usedPct"], 12.0)
        self.assertEqual(a["weekly"]["usedPct"], 33.0)
        self.assertEqual(a["at"], NOW - timedelta(hours=1))

    def test_one_window_alone_is_fine(self):
        a = engine.parse_codex_anchor({
            "at": iso(NOW), "weekly": {"usedPct": 33, "resetAt": iso(NOW + timedelta(days=4))}})
        self.assertIsNone(a["session"])
        self.assertIsNotNone(a["weekly"])

    def test_junk_is_ignored_rather_than_crashing(self):
        self.assertIsNone(engine.parse_codex_anchor(None))
        self.assertIsNone(engine.parse_codex_anchor({"weekly": {"usedPct": 33}}))
        self.assertIsNone(engine.parse_codex_anchor({"at": "ไม่ใช่เวลา"}))

    def test_a_window_without_a_reset_time_is_dropped(self):
        """ไม่มีวันหมดอายุ = ค้างจอตลอดกาล ซึ่งเป็นสิ่งที่เพิ่งแก้ไปทั้งไฟล์"""
        a = engine.parse_codex_anchor({"at": iso(NOW), "weekly": {"usedPct": 33}})
        self.assertIsNone(a)


class ApplyTest(unittest.TestCase):
    """จุดยึดเติมเฉพาะช่องที่ล็อกตอบไม่ได้ ห้ามทับเลขทางการ"""

    def anchor(self, session_pct=None, week_pct=None, at=None,
               session_reset=None, week_reset=None):
        raw = {"at": iso(at or NOW - timedelta(hours=1))}
        if session_pct is not None:
            raw["session"] = {"usedPct": session_pct,
                              "resetAt": iso(session_reset or NOW + timedelta(hours=3))}
        if week_pct is not None:
            raw["weekly"] = {"usedPct": week_pct,
                             "resetAt": iso(week_reset or NOW + timedelta(days=4))}
        return engine.parse_codex_anchor(raw)

    def empty_fields(self):
        return {"pct": None, "confidence": "unsure", "weekPct": None,
                "weekConfidence": "unsure", "resetAt": None, "weekResetAt": None,
                "window": "5 ชม."}

    def test_fills_the_gap_the_log_left(self):
        out = engine.apply_codex_anchor(self.empty_fields(), self.anchor(week_pct=33), NOW)
        self.assertEqual(out["weekPct"], 33.0)
        self.assertEqual(out["weekConfidence"], "lower_bound",
                         "โควตามีแต่ใช้เพิ่ม ค่าที่จดมาจึงเป็นพื้น ไม่ใช่ค่าปัจจุบันเป๊ะ")
        self.assertEqual(out["weekResetAt"], NOW + timedelta(days=4))

    def test_official_numbers_always_win(self):
        fields = self.empty_fields()
        fields["weekPct"], fields["weekConfidence"] = 71.0, "valid"
        out = engine.apply_codex_anchor(fields, self.anchor(week_pct=33), NOW)
        self.assertEqual(out["weekPct"], 71.0, "จุดยึดห้ามทับเลขที่ OpenAI ส่งมาเอง")
        self.assertEqual(out["weekConfidence"], "valid")

    def test_an_expired_anchor_is_ignored(self):
        """หน้าต่างหมุนไปแล้ว ค่าที่จดไว้เป็นของหน้าต่างเก่า"""
        out = engine.apply_codex_anchor(
            self.empty_fields(),
            self.anchor(week_pct=33, week_reset=NOW - timedelta(minutes=1)), NOW)
        self.assertIsNone(out["weekPct"])

    def test_an_anchor_from_the_future_is_ignored(self):
        out = engine.apply_codex_anchor(
            self.empty_fields(), self.anchor(week_pct=33, at=NOW + timedelta(hours=2)), NOW)
        self.assertIsNone(out["weekPct"])

    def test_the_five_hour_window_works_the_same_way(self):
        out = engine.apply_codex_anchor(self.empty_fields(), self.anchor(session_pct=12), NOW)
        self.assertEqual(out["pct"], 12.0)
        self.assertEqual(out["confidence"], "lower_bound")
        self.assertEqual(out["resetAt"], NOW + timedelta(hours=3))

    def test_no_anchor_changes_nothing(self):
        before = self.empty_fields()
        self.assertEqual(engine.apply_codex_anchor(dict(before), None, NOW), before)

    def test_percent_is_clamped_to_a_hundred(self):
        out = engine.apply_codex_anchor(self.empty_fields(), self.anchor(week_pct=140), NOW)
        self.assertEqual(out["weekPct"], 100.0)


if __name__ == "__main__":
    unittest.main()
