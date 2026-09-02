import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import utilization as u

T0 = datetime(2026, 8, 7, 6, 38, 6, tzinfo=timezone.utc)
SAMPLE = {"cachedUsageUtilization": {
    "fetchedAtMs": int(T0.timestamp() * 1000),
    "utilization": {"limits": [
        {"kind": "session", "percent": 5, "severity": "normal",
         "resets_at": "2026-08-07T07:10:00.238547+00:00", "scope": None, "is_active": False},
        {"kind": "weekly_all", "percent": 96, "severity": "critical",
         "resets_at": "2026-08-08T20:00:00.238567+00:00", "scope": None, "is_active": False},
        {"kind": "weekly_scoped", "percent": 100, "severity": "critical",
         "resets_at": "2026-08-08T20:00:00.238771+00:00",
         "scope": {"model": {"display_name": "Fable"}}, "is_active": True},
    ]}}}


class ReadUtilizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "acct")
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump(SAMPLE, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_windows_and_metadata(self):
        value = u.read_utilization(self.dir)
        self.assertEqual(value.fetched_at, T0)
        self.assertEqual([w.kind for w in value.windows], ["session", "weekly_all", "weekly_scoped"])
        self.assertEqual(value.windows[1].percent, 96)
        self.assertEqual(value.windows[2].scope, "Fable")
        self.assertTrue(value.windows[2].is_active)
        self.assertIsNotNone(value.windows[0].resets_at.tzinfo)

    def test_sibling_and_invalid_paths(self):
        alt = os.path.join(self.tmp.name, "other")
        with open(alt + ".json", "w", encoding="utf-8") as f:
            json.dump(SAMPLE, f)
        self.assertIsNotNone(u.read_utilization(alt))
        self.assertIsNone(u.read_utilization("/nonexistent/zzz"))


class ConfidenceTest(unittest.TestCase):
    def setUp(self):
        self.win = u.Window("session", 42.0, datetime(2026, 8, 7, 7, 10, tzinfo=timezone.utc), "normal", None, False)

    def test_confidence_states(self):
        reset = self.win.resets_at
        self.assertEqual(u.window_confidence(self.win, T0, None, reset + timedelta(hours=2)), u.CONFIRMED_ZERO)
        self.assertEqual(u.window_confidence(self.win, T0, reset + timedelta(minutes=30), reset + timedelta(hours=2)), u.UNSURE)
        self.assertEqual(u.window_confidence(self.win, T0, T0 + timedelta(minutes=10), T0 + timedelta(minutes=20)), u.LOWER_BOUND)
        self.assertEqual(u.window_confidence(self.win, T0, None, T0 + timedelta(minutes=7)), u.VALID)


class WindowWithoutResetTimeTest(unittest.TestCase):
    """หน้าต่างที่ยังไม่เริ่มเดิน — endpoint ส่ง percent 0 มาพร้อม resets_at: null

    เคสจริง 2026-09-02: บัญชี work ไม่ได้ใช้งานมาพักหนึ่ง endpoint จึงตอบ
    session = {"percent": 0, "resets_at": null} เพราะไม่มีหน้าต่างไหนเดินอยู่
    โค้ดเดิมทิ้งทั้งก้อนเพราะแปลงเวลาไม่ได้ แถว 5h จึงเป็น "—" ค้างตลอด
    ทั้งที่ศูนย์คือคำตอบที่รู้จริง — ผู้ใช้เห็นเป็น "ไม่อัปเดต"
    """

    @staticmethod
    def limits(percent, resets_at):
        return [{"kind": "session", "percent": percent, "severity": "normal",
                 "resets_at": resets_at, "scope": None, "is_active": False}]

    def test_zero_without_reset_time_is_kept_as_a_real_zero(self):
        windows = u.windows_from_limits(self.limits(0, None))
        self.assertEqual(len(windows), 1, "ศูนย์ที่ยืนยันได้ถูกทิ้งไปทั้งหน้าต่าง")
        self.assertEqual(windows[0].percent, 0.0)
        self.assertIsNone(windows[0].resets_at)

    def test_a_number_without_reset_time_is_still_dropped(self):
        """มีเลขแต่ไม่รู้ว่าหมดอายุเมื่อไหร่ = ค้างจอได้ตลอดกาล ห้ามรับไว้"""
        self.assertEqual(u.windows_from_limits(self.limits(42, None)), [])

    def test_missing_percent_field_is_still_garbage(self):
        """ไม่มีฟิลด์ percent เลย ต่างจากบอกมาว่า 0 — อันแรกไม่ได้บอกอะไรเลย"""
        self.assertEqual(u.windows_from_limits([{"kind": "session"}]), [])

    def test_confidence_of_a_window_that_never_started(self):
        win = u.windows_from_limits(self.limits(0, None))[0]
        self.assertEqual(u.window_confidence(win, T0, None, T0 + timedelta(hours=9)),
                         u.VALID, "ไม่มีหน้าต่างเดินอยู่ ก็ไม่มีอะไรหมดอายุ")
        self.assertEqual(u.window_confidence(win, T0, T0 + timedelta(minutes=5),
                                             T0 + timedelta(minutes=9)),
                         u.LOWER_BOUND, "ใช้งานหลังเวลา fetch — ศูนย์เป็นได้แค่ขอบล่าง")


if __name__ == "__main__":
    unittest.main()
