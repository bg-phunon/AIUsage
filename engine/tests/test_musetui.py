"""% ของ Muse จากจอ `/upgrade` ของ TUI — อ่านจอ เก็บเป็นจุด และกติกาว่าถามเมื่อไร

จอจริงที่จับได้ 2026-10-12 (Muse Code 1.4.6) หลังลอก ANSI ออก:
    You are currently subscribed to the Muse Code Everyday Usage usage plan.
    Current 20% used · Resets at 6:10 PM
    Weekly 6% used · Resets Oct 19 at 7:00 AM
    as of 2:17 PM
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aiusage import musetui  # noqa: E402

BKK = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 12, 14, 17, tzinfo=BKK)
SCREEN = (
    "You are currently subscribed to the Muse Code Everyday Usage usage plan.\n"
    "Current 20% used · Resets at 6:10 PM\n"
    "Weekly 6% used · Resets Oct 19 at 7:00 AM\n"
    "as of 2:17 PM\n")


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class ParseScreenTest(unittest.TestCase):
    def test_reads_both_windows(self):
        got = musetui.parse_screen(SCREEN, NOW)
        self.assertEqual(got["plan"], "everyday")
        self.assertEqual(got["session"]["usedPct"], 20)
        self.assertEqual(got["weekly"]["usedPct"], 6)
        self.assertEqual(got["session"]["resetAt"].astimezone(BKK),
                         datetime(2026, 10, 12, 18, 10, tzinfo=BKK))
        self.assertEqual(got["weekly"]["resetAt"].astimezone(BKK),
                         datetime(2026, 10, 19, 7, 0, tzinfo=BKK))

    def test_survives_ansi_between_words(self):
        raw = ("\x1b[2J\x1b[1;1HCurrent\x1b[1;20H20% used · Resets at 6:10 PM"
               "\x1b[2;1HWeekly\x1b[38;5;8m 6% used · Resets Oct 19 at 7:00 AM\x1b[0m")
        got = musetui.parse_screen(musetui.strip_ansi(raw), NOW)
        self.assertEqual((got["session"]["usedPct"], got["weekly"]["usedPct"]), (20, 6))

    def test_last_redraw_wins(self):
        text = SCREEN.replace("20%", "18%") + SCREEN
        self.assertEqual(musetui.parse_screen(text, NOW)["session"]["usedPct"], 20)

    def test_time_already_passed_today_means_tomorrow(self):
        text = "Current 3% used · Resets at 1:05 AM\n"
        got = musetui.parse_screen(text, NOW)
        self.assertEqual(got["session"]["resetAt"].astimezone(BKK),
                         datetime(2026, 10, 13, 1, 5, tzinfo=BKK))

    def test_reset_a_few_seconds_ago_is_not_tomorrow(self):
        # จอละเอียดแค่นาที — 18:10:30 ยังต้องอ่าน "6:10 PM" เป็นวันนี้
        now = datetime(2026, 10, 12, 18, 10, 30, tzinfo=BKK)
        got = musetui.parse_screen("Current 99% used · Resets at 6:10 PM\n", now)
        self.assertEqual(got["session"]["resetAt"].astimezone(BKK),
                         datetime(2026, 10, 12, 18, 10, tzinfo=BKK))

    def test_midnight_and_noon(self):
        got = musetui.parse_screen(
            "Current 1% used · Resets at 12:30 AM\n"
            "Weekly 1% used · Resets Oct 19 at 12:00 PM\n", NOW)
        self.assertEqual(got["session"]["resetAt"].astimezone(BKK).hour, 0)
        self.assertEqual(got["weekly"]["resetAt"].astimezone(BKK).hour, 12)

    def test_24h_clock(self):
        got = musetui.parse_screen("Current 5% used · Resets at 18:10\n", NOW)
        self.assertEqual(got["session"]["resetAt"].astimezone(BKK).hour, 18)

    def test_weekly_across_new_year(self):
        now = datetime(2026, 12, 29, 9, 0, tzinfo=BKK)
        got = musetui.parse_screen("Weekly 6% used · Resets Jan 4 at 7:00 AM\n", now)
        self.assertEqual(got["weekly"]["resetAt"].astimezone(BKK),
                         datetime(2027, 1, 4, 7, 0, tzinfo=BKK))

    def test_over_quota_is_kept_verbatim(self):
        got = musetui.parse_screen("Current 104% used · Resets at 6:10 PM\n", NOW)
        self.assertEqual(got["session"]["usedPct"], 104)

    def test_one_window_is_still_an_answer(self):
        got = musetui.parse_screen("Weekly 6% used · Resets Oct 19 at 7:00 AM\n", NOW)
        self.assertNotIn("session", got)
        self.assertEqual(got["weekly"]["usedPct"], 6)

    def test_unreadable_screen_is_none_not_zero(self):
        self.assertIsNone(musetui.parse_screen("Do you trust this workspace?", NOW))
        self.assertIsNone(musetui.parse_screen("Current usage · unavailable", NOW))
        self.assertIsNone(
            musetui.parse_screen("Current 20% used · Resets at 25:99 PM", NOW))


class MergeAnchorTest(unittest.TestCase):
    def reading(self, session=20, weekly=6, session_reset=None):
        return {"plan": "everyday",
                "session": {"usedPct": session,
                            "resetAt": session_reset or utc(2026, 10, 12, 11, 10)},
                "weekly": {"usedPct": weekly, "resetAt": utc(2026, 10, 19, 0, 0)}}

    def test_first_reading_is_one_point_per_window(self):
        a = musetui.merge_anchor(None, self.reading(), utc(2026, 10, 12, 7, 17))
        self.assertEqual(a["at"], "2026-10-12T07:17:00Z")
        self.assertEqual(a["session"]["resetAt"], "2026-10-12T11:10:00Z")
        self.assertEqual(a["session"]["points"],
                         [{"usedPct": 20, "at": "2026-10-12T07:17:00Z",
                           "plan": "everyday"}])

    def test_same_window_appends(self):
        a = musetui.merge_anchor(None, self.reading(20), utc(2026, 10, 12, 7, 17))
        b = musetui.merge_anchor(a, self.reading(31), utc(2026, 10, 12, 7, 40))
        self.assertEqual([p["usedPct"] for p in b["session"]["points"]], [20, 31])
        self.assertEqual(len(b["weekly"]["points"]), 2)

    def test_new_reset_time_drops_old_points(self):
        a = musetui.merge_anchor(None, self.reading(90), utc(2026, 10, 12, 7, 17))
        b = musetui.merge_anchor(
            a, self.reading(2, session_reset=utc(2026, 10, 12, 16, 30)),
            utc(2026, 10, 12, 11, 40))
        self.assertEqual([p["usedPct"] for p in b["session"]["points"]], [2])
        # สัปดาห์ยังรอบเดิม ต้องไม่โดนล้างไปด้วย
        self.assertEqual(len(b["weekly"]["points"]), 2)

    def test_minute_jitter_is_the_same_window(self):
        a = musetui.merge_anchor(None, self.reading(20), utc(2026, 10, 12, 7, 17))
        b = musetui.merge_anchor(
            a, self.reading(25, session_reset=utc(2026, 10, 12, 11, 11)),
            utc(2026, 10, 12, 7, 40))
        self.assertEqual(len(b["session"]["points"]), 2)
        self.assertEqual(b["session"]["resetAt"], "2026-10-12T11:10:00Z")

    def test_unread_window_keeps_previous(self):
        a = musetui.merge_anchor(None, self.reading(), utc(2026, 10, 12, 7, 17))
        only_weekly = {"plan": "everyday", "weekly": self.reading(weekly=7)["weekly"]}
        b = musetui.merge_anchor(a, only_weekly, utc(2026, 10, 12, 7, 40))
        self.assertEqual(b["session"], a["session"])

    def test_point_cap_keeps_the_first_point(self):
        a = None
        for i in range(musetui.MAX_POINTS + 5):
            a = musetui.merge_anchor(a, self.reading(i),
                                     utc(2026, 10, 12, 7, 0) + timedelta(minutes=i))
        pts = a["session"]["points"]
        self.assertEqual(len(pts), musetui.MAX_POINTS)
        self.assertEqual(pts[0]["usedPct"], 0)
        self.assertEqual(pts[-1]["usedPct"], musetui.MAX_POINTS + 4)


class NewerAnchorTest(unittest.TestCase):
    def test_probe_after_the_hand_written_note_wins(self):
        cfg = {"at": "2026-10-12T07:05:00Z"}
        live = {"at": "2026-10-12T07:17:00Z"}
        self.assertIs(musetui.newer_anchor(cfg, live), live)

    def test_hand_written_note_after_the_probe_wins(self):
        cfg = {"at": "2026-10-12T08:00:00Z"}
        self.assertIs(musetui.newer_anchor(cfg, {"at": "2026-10-12T07:17:00Z"}), cfg)

    def test_missing_sides(self):
        live = {"at": "2026-10-12T07:17:00Z"}
        self.assertIs(musetui.newer_anchor(None, live), live)
        self.assertIsNone(musetui.newer_anchor(None, None))
        cfg = {"at": "2026-10-12T07:05:00Z"}
        self.assertIs(musetui.newer_anchor(cfg, {"at": "garbage"}), cfg)


class DueTest(unittest.TestCase):
    def test_no_muse_activity_never_asks(self):
        self.assertFalse(musetui.due({}, None, 10_000))

    def test_first_time_with_activity_asks(self):
        self.assertTrue(musetui.due({}, 9_000, 10_000))

    def test_waits_out_the_interval(self):
        entry = {"triedAt": 10_000}
        self.assertFalse(musetui.due(entry, 10_500, 10_000 + musetui.MIN_INTERVAL - 1))
        self.assertTrue(musetui.due(entry, 10_500, 10_000 + musetui.MIN_INTERVAL))

    def test_no_new_activity_since_last_try_never_asks(self):
        # เลิกใช้ Muse แล้ว % ไม่ขยับ — เปิด TUI ไปก็แค่เขียน auth.json ทิ้งเปล่าๆ
        self.assertFalse(musetui.due({"triedAt": 10_000}, 9_999, 99_999))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "muse-live.json")

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_kick_stamps_before_spawning(self):
        seen = []

        def spawn(path):
            seen.append(self.read()["triedAt"])

        self.assertTrue(musetui.kick(900, path=self.path, clock=lambda: 1000,
                                     spawn=spawn))
        self.assertEqual(seen, [1000])
        # รอบถัดไปของเอนจิน (60 วิ) ลูกยังไม่เสร็จ — ต้องไม่เปิดซ้อน
        self.assertFalse(musetui.kick(1050, path=self.path, clock=lambda: 1060,
                                      spawn=lambda p: self.fail("spawned twice")))

    def test_kick_does_nothing_when_not_due(self):
        self.assertFalse(musetui.kick(None, path=self.path, clock=lambda: 1000,
                                      spawn=lambda p: self.fail("spawned")))
        self.assertFalse(os.path.exists(self.path))

    def test_probe_stores_anchor(self):
        reading = {"plan": "everyday",
                   "session": {"usedPct": 20, "resetAt": utc(2026, 10, 12, 11, 10)},
                   "weekly": {"usedPct": 6, "resetAt": utc(2026, 10, 19, 0, 0)}}
        now = utc(2026, 10, 12, 7, 17).timestamp()
        self.assertTrue(musetui.probe(self.path, fetch=lambda: reading,
                                      clock=lambda: now))
        anchor = musetui.live_anchor(self.path)
        self.assertEqual(anchor["session"]["points"][0]["usedPct"], 20)
        self.assertEqual(self.read()["fetchedAt"], now)

    def test_failed_probe_keeps_old_anchor(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"triedAt": 5, "fetchedAt": 5, "anchor": {"at": "x"}}, fh)
        self.assertFalse(musetui.probe(self.path, fetch=lambda: None,
                                       clock=lambda: 99))
        self.assertEqual(self.read(), {"triedAt": 5, "fetchedAt": 5,
                                       "anchor": {"at": "x"}})

    def test_live_anchor_missing_file(self):
        self.assertIsNone(musetui.live_anchor(self.path))


if __name__ == "__main__":
    unittest.main()
