"""ใบรีเซ็ตลิมิตของ Codex — "Usage limit resets" บนหน้า usage ของ OpenAI

ใบรีเซ็ตคือทางออกตอนชนเพดาน กดแล้วโควตากลับมาเต็ม แต่มันมีวันหมดอายุ ("Expires
Oct 4, 8:06 AM") ใช้ไม่ทันก็หายไปเฉยๆ การรู้ว่าเหลือกี่ใบและใบแรกหมดเมื่อไหร่
จึงเป็นข้อมูลที่มีค่าพอๆ กับ %

ไม่มีแหล่งในเครื่องเลย — ไม่อยู่ในล็อก ไม่อยู่ใน sqlite ไม่อยู่ใน config ของ Codex
จึงต้องจดมาจากหน้าเว็บเหมือน codexAnchor และต้องหมดอายุเองตามเวลาจริง
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_resets", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


class ParseTest(unittest.TestCase):
    def test_reads_the_expiry_list(self):
        r = engine.parse_codex_resets({"expiring": [iso(NOW + timedelta(days=24)),
                                                    iso(NOW + timedelta(days=25))]})
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0], NOW + timedelta(days=24))

    def test_sorted_soonest_first_regardless_of_input_order(self):
        """ใบที่จะหมดก่อนคือใบที่ต้องรีบใช้ — ลำดับที่จดมาไม่จำเป็นต้องเรียง"""
        r = engine.parse_codex_resets({"expiring": [iso(NOW + timedelta(days=25)),
                                                    iso(NOW + timedelta(days=24))]})
        self.assertEqual(r[0], NOW + timedelta(days=24))

    def test_junk_entries_are_dropped_not_fatal(self):
        r = engine.parse_codex_resets({"expiring": [iso(NOW + timedelta(days=2)),
                                                    "ไม่ใช่เวลา", None, 5]})
        self.assertEqual(len(r), 1)

    def test_nothing_configured_is_none(self):
        self.assertIsNone(engine.parse_codex_resets(None))
        self.assertIsNone(engine.parse_codex_resets({}))
        self.assertIsNone(engine.parse_codex_resets({"expiring": []}))


class ExpiryTest(unittest.TestCase):
    """ใบที่หมดอายุแล้วต้องหายไปเอง ไม่ต้องรอใครมาลบ"""

    def resets(self, *offsets):
        return engine.parse_codex_resets(
            {"expiring": [iso(NOW + timedelta(days=d)) for d in offsets]})

    def test_expired_ones_are_not_counted(self):
        live = engine.live_codex_resets(self.resets(-1, 3), NOW)
        self.assertEqual(len(live), 1)

    def test_all_expired_means_none_left(self):
        self.assertEqual(engine.live_codex_resets(self.resets(-5, -1), NOW), [])

    def test_a_reset_expiring_this_very_minute_is_already_gone(self):
        self.assertEqual(engine.live_codex_resets(self.resets(0), NOW), [])

    def test_none_in_none_out(self):
        self.assertEqual(engine.live_codex_resets(None, NOW), [])


class FieldsTest(unittest.TestCase):
    def test_item_gets_the_count_and_the_soonest_expiry(self):
        resets = engine.parse_codex_resets(
            {"expiring": [iso(NOW + timedelta(days=25)), iso(NOW + timedelta(days=24))]})
        live = engine.live_codex_resets(resets, NOW)
        self.assertEqual(len(live), 2)
        self.assertEqual(live[0], NOW + timedelta(days=24),
                         "ใบที่หมดก่อนต้องมาก่อน UI จะได้บอกได้ว่าต้องรีบใช้เมื่อไหร่")


if __name__ == "__main__":
    unittest.main()
