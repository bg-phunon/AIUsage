"""ใบรีเซ็ตลิมิตของ Claude ที่จดมือ — ทางสำรองเมื่อ server ไม่ยอมบอก

server ตอบเรื่องใบรีเซ็ตเฉพาะ Claude Code (ineligible_reason "surface") และ
control request get_usage ของ CLI ไม่แนบก้อนนี้มา (ตรวจซ้ำกับ CLI 2.1.292
2026-10-07) ส่วน `/limit-reset` คือคำสั่งที่ใช้ใบจริง เอนจินห้ามเรียกเด็ดขาด
ตัวเลขจึงต้องจดจากบรรทัด "/limit-reset to refill your limits · N left · use by
DATE" ที่ CLI แสดงตอนชนเพดาน — แบบเดียวกับ codexLimitResets
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_claude_resets", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def state(raw, label="work"):
    return engine.claude_config_resets(raw, label, NOW)


class CountAndUseByTest(unittest.TestCase):
    """รูปที่ CLI แสดง: จำนวนที่เหลือ + วันใช้ได้ถึง"""

    def test_count_with_use_by(self):
        until = NOW + timedelta(days=10)
        s = state({"work": {"count": 2, "useBy": iso(until)}})
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["expiring"], [until, until])

    def test_past_use_by_means_none_left(self):
        s = state({"work": {"count": 2, "useBy": iso(NOW - timedelta(minutes=1))}})
        self.assertEqual(s["count"], 0, "เลยวันใช้แล้ว = ยืนยันว่าไม่เหลือ ไม่ใช่ไม่รู้")
        self.assertEqual(s["expiring"], [])

    def test_count_without_use_by_never_expires_by_itself(self):
        s = state({"work": {"count": 1}})
        self.assertEqual(s["count"], 1)
        self.assertEqual(s["expiring"], [])

    def test_zero_is_kept_as_zero(self):
        self.assertEqual(state({"work": {"count": 0}})["count"], 0)


class ExpiringListTest(unittest.TestCase):
    def test_list_drops_expired_and_sorts(self):
        a, b = NOW + timedelta(days=5), NOW + timedelta(days=2)
        s = state({"work": {"expiring": [iso(a), iso(NOW - timedelta(days=1)), iso(b)]}})
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["expiring"], [b, a])


class KeyingTest(unittest.TestCase):
    def test_other_account_gets_nothing(self):
        self.assertIsNone(state({"mooz": {"count": 1}}, label="work"))

    def test_missing_or_broken_is_unknown_not_zero(self):
        for raw in (None, {}, {"work": None}, {"work": {}}, {"work": {"count": "x"}},
                    {"work": {"count": -1}}, [1, 2]):
            self.assertIsNone(state(raw), raw)

    def test_shape_matches_live_state(self):
        s = state({"work": {"count": 1}})
        self.assertEqual(set(s), {"count", "expiring", "nextAvailableAt"})
        self.assertIsNone(s["nextAvailableAt"])


if __name__ == "__main__":
    unittest.main()
