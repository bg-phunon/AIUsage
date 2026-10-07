"""จุดยึดโควตา Muse จากหน้า usage — มีประวัติหลายจุดไว้วัดอัตราแบบ albb

Muse ไม่มี quota API ที่ยืนยันแล้ว (log ไม่มีเลข CLI ไม่มีคำสั่ง) ตัวเลขสองแถบ
จึงมาจากการจดมือ — จุดเดียว = lower_bound ค้างจนรีเซ็ต แต่ถ้ามีสองจุดขึ้นไปจะวัด
อัตรา %/token แล้วประมาณต่อเองระหว่างรอบที่จด

อัตราเป็น "everyday-equivalent %" (จุดคูณตัวคูณแผนตอนที่จด) อัปเกรดแผนกลาง
หน้าต่างแล้วเลขจึงปรับตามเองโดยไม่ต้องจดใหม่ — 20% บน everyday = 4% ทันทีที่ขึ้น
high (5X) โดยอัตราเดิมยังใช้ต่อได้เพราะอยู่ในหน่วยเดียวกัน
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_muse_anchor", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def point(pct, at, plan="everyday"):
    return {"usedPct": pct, "at": at, "mult": engine.muse_plan_mult(plan)}


class ParseTest(unittest.TestCase):
    def test_reads_points_and_plans(self):
        a = engine.parse_muse_anchor({
            "at": iso(NOW), "plan": "high",
            "session": {"resetAt": iso(NOW + timedelta(hours=3)), "points": [
                {"usedPct": 18, "at": iso(NOW - timedelta(minutes=11))},
                {"usedPct": 20, "at": iso(NOW - timedelta(minutes=1)),
                 "plan": "everyday"},
            ]},
        })
        pts = a["session"]["points"]
        self.assertEqual([(p["usedPct"], p["mult"]) for p in pts],
                         [(18.0, 5), (20.0, 1)])
        self.assertEqual(a["mult"], 5)
        self.assertEqual(a["at"], NOW)

    def test_unknown_plan_falls_back_to_everyday(self):
        a = engine.parse_muse_anchor({
            "at": iso(NOW), "plan": "mystery",
            "session": {"resetAt": iso(NOW + timedelta(hours=3)), "points": [
                {"usedPct": 18, "at": iso(NOW)}]}})
        self.assertEqual(a["mult"], 1)
        self.assertEqual(a["session"]["points"][0]["mult"], 1)

    def test_legacy_single_reading_still_works(self):
        a = engine.parse_muse_anchor({
            "at": iso(NOW - timedelta(minutes=1)),
            "session": {"usedPct": 18, "resetAt": iso(NOW + timedelta(hours=3))},
        })
        pts = a["session"]["points"]
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["usedPct"], 18.0)
        self.assertEqual(pts[0]["at"], NOW - timedelta(minutes=1))

    def test_junk_is_ignored_rather_than_crashing(self):
        self.assertIsNone(engine.parse_muse_anchor(None))
        self.assertIsNone(engine.parse_muse_anchor({"weekly": {"usedPct": 6}}))
        self.assertIsNone(engine.parse_muse_anchor({"at": "ไม่ใช่เวลา"}))

    def test_a_window_without_a_reset_time_is_dropped(self):
        a = engine.parse_muse_anchor({"at": iso(NOW), "weekly": {"points": [
            {"usedPct": 6, "at": iso(NOW)}]}})
        self.assertIsNone(a)


class EstimateTest(unittest.TestCase):
    def test_two_points_estimate_live(self):
        p1 = point(18, NOW - timedelta(minutes=11))
        p2 = point(20, NOW - timedelta(minutes=1))
        # ระหว่างจุด: 2% ต่อ 3.54M · หลังจุด: 1.77M = +1%
        series = [(NOW - timedelta(minutes=5), 3_540_000),
                  (NOW - timedelta(seconds=30), 1_770_000)]
        pct, conf = engine.estimate_muse_pct([p1, p2], series, NOW)
        self.assertAlmostEqual(pct, 21.0)
        self.assertEqual(conf, "estimated")

    def test_single_point_holds_as_lower_bound(self):
        pct, conf = engine.estimate_muse_pct([point(20, NOW - timedelta(minutes=1))],
                                             [(NOW, 9_999_999)], NOW)
        self.assertEqual((pct, conf), (20.0, "lower_bound"))

    def test_upgrade_rescales_without_a_fresh_jot(self):
        """ขึ้น high กลางหน้าต่าง 20% เดิมต้องกลายเป็น 4% ทันที ไม่ต้องรอจดใหม่"""
        pct, conf = engine.estimate_muse_pct([point(20, NOW - timedelta(minutes=1))],
                                             [], NOW, current_mult=5)
        self.assertEqual((pct, conf), (4.0, "estimated"))

    def test_rate_survives_an_upgrade_mid_window(self):
        """จุด everyday 20% แล้วจดใหม่ 4.5% บน high — อัตราต้องต่อกันได้ในหน่วย
        everyday-equivalent (20 → 22.5) ไม่ใช่เริ่มนับใหม่"""
        p1 = point(20, NOW - timedelta(minutes=11), "everyday")
        p2 = point(4.5, NOW - timedelta(minutes=1), "high")
        series = [(NOW - timedelta(minutes=5), 2_500_000),
                  (NOW - timedelta(seconds=30), 2_500_000)]
        pct, conf = engine.estimate_muse_pct([p1, p2], series, NOW, current_mult=5)
        # 2.5 equiv-% ต่อ 2.5M หลังจุดอีก 2.5M = 25 equiv-% = 5% บน high
        self.assertAlmostEqual(pct, 5.0)
        self.assertEqual(conf, "estimated")

    def test_unmoved_window_holds_instead_of_estimating(self):
        p1 = point(6, NOW - timedelta(minutes=11))
        p2 = point(6, NOW - timedelta(minutes=1))
        pct, conf = engine.estimate_muse_pct([p1, p2], [(NOW, 1_000_000)], NOW)
        self.assertEqual((pct, conf), (6.0, "lower_bound"))

    def test_future_points_are_ignored(self):
        pct, _ = engine.estimate_muse_pct(
            [point(20, NOW - timedelta(minutes=1)), point(99, NOW + timedelta(hours=1))],
            [], NOW)
        self.assertEqual(pct, 20.0)
        self.assertIsNone(engine.estimate_muse_pct(
            [point(99, NOW + timedelta(hours=1))], [], NOW))

    def test_percent_is_clamped_to_a_hundred(self):
        p1 = point(90, NOW - timedelta(minutes=11))
        p2 = point(95, NOW - timedelta(minutes=1))
        series = [(NOW - timedelta(minutes=5), 5_000_000),
                  (NOW, 99_000_000)]
        pct, _ = engine.estimate_muse_pct([p1, p2], series, NOW)
        self.assertEqual(pct, 100.0)


if __name__ == "__main__":
    unittest.main()
