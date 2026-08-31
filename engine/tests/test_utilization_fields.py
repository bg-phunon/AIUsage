import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage.utilization import Utilization, Window  # noqa: E402

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_uf", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)


def win(kind, percent, scope=None, is_active=False, resets_in_hours=24):
    return Window(kind=kind, percent=float(percent),
                  resets_at=NOW + timedelta(hours=resets_in_hours),
                  severity="normal", scope=scope, is_active=is_active)


def util_of(*windows):
    return Utilization(fetched_at=NOW - timedelta(minutes=1), windows=list(windows))


class UtilizationFieldsTest(unittest.TestCase):
    def test_fable_gauge_is_its_own_window_not_max_into_weekly(self):
        """gauge ต่อโมเดล (Fable) ต้องแยกแถว — ไม่ถูก max() กลืนจน 7d โกหก"""
        fields = engine.utilization_fields(
            util_of(win("session", 12),
                    win("weekly_all", 5),
                    win("weekly_scoped", 30, scope="Fable")),
            last_activity=None, now=NOW)
        self.assertEqual(fields["pct"], 12)
        self.assertEqual(fields["weekPct"], 5, "7d ต้องเป็นตัวรวมทุกโมเดลจริง ไม่ใช่ max")
        self.assertEqual(len(fields["modelWindows"]), 1)
        gauge = fields["modelWindows"][0]
        self.assertEqual(gauge["label"], "Fable")
        self.assertEqual(gauge["pct"], 30.0)
        self.assertEqual(gauge["confidence"], "valid")

    def test_no_scoped_windows_means_empty_model_windows(self):
        fields = engine.utilization_fields(
            util_of(win("session", 12), win("weekly_all", 5)),
            last_activity=None, now=NOW)
        self.assertEqual(fields["modelWindows"], [])
        self.assertEqual(fields["weekPct"], 5)

    def test_scoped_only_doubles_as_weekly_without_duplicate_row(self):
        """ไม่มี weekly_all เลย — scoped ตัวเดียวทำหน้าที่ 7d ไป ไม่ต้องซ้ำสองที่"""
        fields = engine.utilization_fields(
            util_of(win("weekly_scoped", 30, scope="Fable")),
            last_activity=None, now=NOW)
        self.assertEqual(fields["weekPct"], 30)
        self.assertEqual(fields["modelWindows"], [])

    def test_active_scoped_limit_reports_model_name(self):
        fields = engine.utilization_fields(
            util_of(win("session", 100, is_active=True),
                    win("weekly_all", 40),
                    win("weekly_scoped", 90, scope="Fable")),
            last_activity=None, now=NOW)
        self.assertEqual(fields["activeLimit"], "session")
        self.assertEqual(fields["severity"], "normal")

    def test_weekly_window_reports_its_own_reset_time(self):
        """7d มีเวลารีเซ็ตของตัวเอง — ไม่ใช่ยืมของ session ที่หมุนทุก 5 ชม."""
        fields = engine.utilization_fields(
            util_of(win("session", 12, resets_in_hours=3),
                    win("weekly_all", 5, resets_in_hours=96)),
            last_activity=None, now=NOW)
        self.assertEqual(fields["resetAt"], NOW + timedelta(hours=3))
        self.assertEqual(fields["weekResetAt"], NOW + timedelta(hours=96))

    def test_no_weekly_window_means_no_week_reset(self):
        fields = engine.utilization_fields(
            util_of(win("session", 12)), last_activity=None, now=NOW)
        self.assertIsNone(fields["weekResetAt"])

    def test_expired_scoped_window_without_activity_reads_zero(self):
        """หน้าต่างที่รีเซ็ตไปแล้วและไม่มีการใช้งานหลังจากนั้น = ศูนย์แน่นอน"""
        expired = Window(kind="weekly_scoped", percent=80.0,
                         resets_at=NOW - timedelta(hours=2),
                         severity="normal", scope="Fable", is_active=False)
        fields = engine.utilization_fields(
            util_of(win("weekly_all", 5), expired), last_activity=None, now=NOW)
        self.assertEqual(fields["modelWindows"][0]["pct"], 0.0)
        self.assertEqual(fields["modelWindows"][0]["confidence"], "zero")


if __name__ == "__main__":
    unittest.main()
