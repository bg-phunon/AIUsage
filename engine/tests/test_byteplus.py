import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import byteplus


def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# เคสจริง 2026-10-10: console ถ่ายตอน 11:41Z
REAL = {"bp": {"plan": "lite", "startAt": "2026-10-10T11:12:00Z",
               "resetAt": "2026-11-10T16:00:00Z",
               "anchor": {"at": "2026-10-10T11:41:00Z",
                          "session": 36.71, "week": 6.15, "month": 3.07}}}
REAL_SERIES = [(dt("2026-10-10T11:27:58Z"), 117_773), (dt("2026-10-10T11:28:01Z"), 117_861),
               (dt("2026-10-10T11:28:04Z"), 123_483), (dt("2026-10-10T11:28:45Z"), 124_145),
               (dt("2026-10-10T11:28:57Z"), 128_852), (dt("2026-10-10T11:29:06Z"), 130_984),
               (dt("2026-10-10T11:29:16Z"), 133_133), (dt("2026-10-10T11:29:59Z"), 136_802)]


class EndpointTest(unittest.TestCase):
    def test_only_coding_path_is_the_plan(self):
        host = "ark.ap-southeast.bytepluses.com"
        self.assertTrue(byteplus.is_plan_endpoint(host, "/api/coding"))
        self.assertTrue(byteplus.is_plan_endpoint(host, "/api/coding/v3"))
        self.assertFalse(byteplus.is_plan_endpoint(host, "/api/v3"))
        self.assertFalse(byteplus.is_plan_endpoint(host, "/api/codingx"))
        self.assertFalse(byteplus.is_plan_endpoint("api.z.ai", "/api/coding"))


class ParsePlansTest(unittest.TestCase):
    now = dt("2026-10-10T12:00:00Z")

    def test_garbage_is_ignored(self):
        self.assertEqual(byteplus.parse_plans(None, self.now), {})
        self.assertEqual(byteplus.parse_plans({"bp": {"plan": "ultra"}}, self.now), {})
        self.assertEqual(byteplus.parse_plans({"bp": "lite"}, self.now), {})

    def test_bad_or_future_anchor_is_dropped(self):
        for anchor in ({"at": "2026-10-11T00:00:00Z", "session": 5},
                       {"at": "2026-10-10T11:00:00Z", "session": 0},
                       {"at": "nope", "session": 5}):
            plans = byteplus.parse_plans({"bp": {"plan": "lite", "anchor": anchor}}, self.now)
            self.assertIsNone(plans["bp"]["anchor"])


class WindowsTest(unittest.TestCase):
    def test_session_starts_at_first_request_not_the_hour(self):
        series = [(dt("2026-10-10T03:00:00Z"), 5),               # หน้าต่างเก่า หมดแล้ว
                  (dt("2026-10-10T08:20:00Z"), 7), (dt("2026-10-10T11:00:00Z"), 11)]
        self.assertEqual(byteplus.session_window(series, dt("2026-10-10T12:00:00Z")),
                         (dt("2026-10-10T08:20:00Z"), 18))
        self.assertIsNone(byteplus.session_window(series, dt("2026-10-10T13:20:00Z")))

    def test_week_starts_monday_local(self):
        tz = timezone(timedelta(hours=8))
        self.assertEqual(byteplus.week_start(dt("2026-10-10T12:00:00Z"), tz),
                         dt("2026-10-04T16:00:00Z"))
        self.assertEqual(byteplus.week_start(dt("2026-10-05T23:00:00Z"), tz),
                         dt("2026-10-04T16:00:00Z"))

    def test_first_month_runs_past_the_purchase_day(self):
        plan = byteplus.parse_plans(REAL, dt("2026-10-10T12:00:00Z"))["bp"]
        expected = (dt("2026-10-10T11:12:00Z"), dt("2026-11-10T16:00:00Z"))
        # ก่อนและหลังเส้นเที่ยงคืนวันที่ 11 ต.ค. — ยังเป็นรอบแรกทั้งคู่
        self.assertEqual(byteplus.month_window(plan, dt("2026-10-10T12:00:00Z")), expected)
        self.assertEqual(byteplus.month_window(plan, dt("2026-10-20T00:00:00Z")), expected)
        # รอบถัดไปเริ่มที่เส้นรีเซ็ตจริง
        self.assertEqual(byteplus.month_window(plan, dt("2026-11-15T00:00:00Z")),
                         (dt("2026-11-10T16:00:00Z"), dt("2026-12-10T16:00:00Z")))


class RealCaseTest(unittest.TestCase):
    def test_anchor_reproduces_console(self):
        now = dt("2026-10-10T11:41:00Z")
        plan = byteplus.parse_plans(REAL, now)["bp"]
        f = byteplus.plan_fields(plan, REAL_SERIES, now)
        self.assertEqual(f["pct"], 36.7)
        self.assertEqual(f["weekPct"], 6.2)   # 6.15 ปัดหนึ่งตำแหน่ง
        self.assertEqual(f["modelWindows"][0]["pct"], 3.07)
        self.assertEqual(f["resetAt"], "2026-10-10T16:27:58Z")
        self.assertEqual(f["weekResetAt"], "2026-10-11T16:00:00Z")
        self.assertEqual(f["modelWindows"][0]["resetAt"], "2026-11-10T16:00:00Z")

    def test_default_caps_match_the_measurement(self):
        now = dt("2026-10-10T11:41:00Z")
        raw = {"bp": dict(REAL["bp"])}
        del raw["bp"]["anchor"]
        f = byteplus.plan_fields(byteplus.parse_plans(raw, now)["bp"], REAL_SERIES, now)
        self.assertAlmostEqual(f["pct"], 36.7, delta=0.1)
        self.assertAlmostEqual(f["weekPct"], 6.15, delta=0.1)

    def test_caps_carry_over_to_later_windows(self):
        later = dt("2026-10-12T03:00:00Z")    # สัปดาห์ใหม่ session ใหม่
        plan = byteplus.parse_plans(REAL, later)["bp"]
        series = REAL_SERIES + [(dt("2026-10-12T02:00:00Z"), 276_000)]
        f = byteplus.plan_fields(plan, series, later)
        self.assertAlmostEqual(f["pct"], 10.0, delta=0.1)
        self.assertAlmostEqual(f["weekPct"], 276_000 / 16_470_000 * 100, delta=0.1)

    def test_caps_at_100(self):
        now = dt("2026-10-10T12:00:00Z")
        plan = byteplus.parse_plans({"bp": {"plan": "lite"}}, now)["bp"]
        f = byteplus.plan_fields(plan, [(dt("2026-10-10T11:00:00Z"), 9_000_000)], now)
        self.assertEqual(f["pct"], 100.0)
        self.assertEqual(f["modelWindows"], [])


if __name__ == "__main__":
    unittest.main()
