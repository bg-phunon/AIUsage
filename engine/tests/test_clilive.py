"""ถาม Claude Code CLI ตรงๆ แทนการยิง endpoint เอง

เหตุผลเดียวกับที่ทำกับ Codex (`codex app-server`): CLI ถือ auth ของตัวเองอยู่แล้ว
เอนจินจึงไม่ต้องอ่าน token จาก Keychain และไม่ต้องต่ออายุ refresh token ซึ่งเป็น
จุดเสี่ยงที่สุดของโปรเจกต์ — refresh token ถูก rotate เก็บตัวใหม่ไม่ทันคือบัญชีหลุด

`get_usage` เป็น control request ไม่ใช่ prompt จึงไม่เรียกโมเดลและไม่เสียโควตา
(วัดจริง 2026-09-24: total_cost_usd 0, total_api_duration_ms 0)
"""

import importlib.util
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aiusage import clilive  # noqa: E402

HOME = os.path.expanduser("~")
DEFAULT_DIR = os.path.join(HOME, ".claude")
OTHER_DIR = os.path.join(HOME, ".ccs", "instances", "mooz")


def reply(rate_limits, request_id="1", ready=False):
    return {"type": "control_response",
            "response": {"subtype": "success", "request_id": request_id,
                         "response": {"subscription_type": "pro",
                                      "rate_limits_available": ready,
                                      "rate_limits": rate_limits}}}


def limits_rows():
    return [{"kind": "session", "group": "session", "percent": 59.0,
             "resets_at": "2026-09-24T12:10:00+00:00", "severity": "normal",
             "is_active": False, "scope": None},
            {"kind": "weekly_all", "group": "weekly", "percent": 79.0,
             "resets_at": "2026-09-26T20:00:00+00:00", "severity": "warning",
             "is_active": True, "scope": None}]


class EnvTest(unittest.TestCase):
    """บัญชี default ต้องไม่ตั้ง CLAUDE_CONFIG_DIR

    เคสจริง 2026-09-24: ตั้ง CLAUDE_CONFIG_DIR=~/.claude ซึ่งเป็นค่าเดียวกับ
    ค่าปริยาย แล้ว CLI กลับไปหา keychain ชื่อที่ hash จาก path (คนละใบกับ
    "Claude Code-credentials") จึงตอบ plan=None rows=0 ทั้งที่บัญชีนั้นใช้งานได้
    """

    def test_the_default_account_gets_no_config_dir(self):
        env = clilive.cli_env(DEFAULT_DIR, base={"PATH": "/usr/bin"})
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_a_named_account_gets_its_directory(self):
        env = clilive.cli_env(OTHER_DIR, base={})
        self.assertEqual(env["CLAUDE_CONFIG_DIR"], OTHER_DIR)

    def test_an_inherited_config_dir_is_dropped_for_the_default_account(self):
        env = clilive.cli_env(DEFAULT_DIR, base={"CLAUDE_CONFIG_DIR": OTHER_DIR})
        self.assertNotIn("CLAUDE_CONFIG_DIR", env)


class ReplyTest(unittest.TestCase):
    def test_a_control_response_gives_the_rate_limits_block(self):
        rl = {"limits": limits_rows()}
        self.assertEqual(clilive.usage_from_reply(reply(rl)), rl)

    def test_other_messages_are_not_answers(self):
        for msg in ({"type": "system", "subtype": "hook_started"},
                    {"type": "result"},
                    {"response": {}},
                    "ไม่ใช่ dict"):
            self.assertIsNone(clilive.usage_from_reply(msg))

    def test_a_failed_control_response_is_not_an_answer(self):
        msg = {"type": "control_response",
               "response": {"subtype": "error", "request_id": "1", "error": "nope"}}
        self.assertIsNone(clilive.usage_from_reply(msg))


class FetchTest(unittest.TestCase):
    """CLI ตอบทันทีด้วยของที่มีในมือ — ตอบมาว่างต้องถามซ้ำ ไม่ใช่สรุปว่าไม่มี

    เคสจริง 2026-09-24: คำตอบแรกของบางบัญชีมาก่อนที่ CLI จะดึง usage เสร็จ
    ได้ rows=0 ทั้งที่ถามซ้ำอีกวินาทีเดียวก็ได้ครบ
    """

    @staticmethod
    def talker(replies):
        """จำลอง CLI — คืนคำตอบทีละอันตามลำดับที่กำหนด"""
        seen = []

        def send(request_id):
            seen.append(request_id)
            return replies[min(len(seen) - 1, len(replies) - 1)]
        send.seen = seen
        return send

    def test_a_full_answer_is_taken_on_the_first_try(self):
        send = self.talker([reply({"limits": limits_rows()})])
        out = clilive.ask(send, tries=3, pause=lambda _: None)
        self.assertEqual(len(out["limits"]), 2)
        self.assertEqual(len(send.seen), 1)

    def test_an_empty_answer_is_asked_again(self):
        send = self.talker([reply({"limits": []}), reply({"limits": limits_rows()})])
        out = clilive.ask(send, tries=3, pause=lambda _: None)
        self.assertEqual(len(out["limits"]), 2)
        self.assertEqual(len(send.seen), 2)

    def test_an_empty_but_finished_answer_is_the_answer(self):
        """rate_limits_available: true + ไม่มีแถว = "ตอบแล้ว และว่างจริง"

        เคสจริง 2026-09-24: บัญชี Team ตอบแบบนี้ค้างอยู่หลายนาที ถามซ้ำแปดครั้ง
        ก็ได้เท่าเดิม — การถามซ้ำจึงเป็นการรอเปล่าๆ ครั้งละ 3-4 วินาทีทุกรอบ
        """
        send = self.talker([reply({"limits": []}, ready=True)])
        out = clilive.ask(send, tries=3, pause=lambda _: None)
        self.assertEqual(out, {"limits": []})
        self.assertEqual(len(send.seen), 1)

    def test_an_account_with_nothing_to_report_gives_up(self):
        """บัญชีที่ยังไม่ได้ล็อกอินตอบว่างจริงๆ — ห้ามวนไม่เลิก"""
        send = self.talker([reply({"limits": []})])
        self.assertIsNone(clilive.ask(send, tries=3, pause=lambda _: None))
        self.assertEqual(len(send.seen), 3)

    def test_a_silent_cli_is_not_an_answer(self):
        self.assertIsNone(clilive.ask(lambda _: None, tries=2, pause=lambda _: None))


class ResetsTest(unittest.TestCase):
    """ใบรีเซ็ตลิมิตของ Claude — server ตอบเฉพาะ client ที่มีสิทธิ์

    juniper_tide = ใบเดียวต่อสัปดาห์ (`/limit-reset` รีเซ็ตหน้าต่าง 5 ชม.)
    cedar_ember  = ใบเป็นใบๆ มีวันหมดอายุ แบบเดียวกับของ Codex

    "ไม่มีสิทธิ์" กับ "ไม่เหลือใบ" คนละเรื่องกัน — อันแรกต้องเป็น None (ไม่รู้)
    ห้ามกลายเป็น 0 ที่อ่านว่า "ใช้หมดแล้ว"
    """

    def test_no_block_at_all_means_we_do_not_know(self):
        self.assertIsNone(clilive.reset_state({"limits": limits_rows()}))
        self.assertIsNone(clilive.reset_state({}))

    def test_an_ineligible_client_learns_nothing(self):
        rl = {"juniper_tide": {"eligible": False, "ineligible_reason": "surface",
                               "available": False, "next_available_at": None,
                               "weekly_resets_at": None, "resets_per_week": 1}}
        self.assertIsNone(clilive.reset_state(rl))

    def test_a_weekly_reset_that_is_ready_counts_as_one(self):
        rl = {"juniper_tide": {"eligible": True, "available": True,
                               "next_available_at": None,
                               "weekly_resets_at": "2026-10-01T00:00:00+00:00",
                               "resets_per_week": 1}}
        state = clilive.reset_state(rl)
        self.assertEqual(state["count"], 1)
        self.assertEqual(state["expiring"], [])

    def test_a_spent_weekly_reset_is_zero_with_the_day_it_returns(self):
        rl = {"juniper_tide": {"eligible": True, "available": False,
                               "next_available_at": "2026-10-01T00:00:00+00:00",
                               "weekly_resets_at": "2026-10-01T00:00:00+00:00",
                               "resets_per_week": 1}}
        state = clilive.reset_state(rl)
        self.assertEqual(state["count"], 0)
        self.assertEqual(state["nextAvailableAt"],
                         datetime(2026, 10, 1, tzinfo=timezone.utc))

    def test_grants_are_counted_with_their_deadlines(self):
        rl = {"cedar_ember": {"eligible": True, "at_limit": False, "grants": [
            {"id": "g1", "resets_left": 2, "resets_total": 3,
             "ends_at": "2026-10-04T22:41:14+00:00"},
            {"id": "g2", "resets_left": 1, "resets_total": 1,
             "ends_at": "2026-10-02T10:00:00+00:00"}]}}
        state = clilive.reset_state(rl)
        self.assertEqual(state["count"], 3)
        self.assertEqual(state["expiring"],
                         [datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
                          datetime(2026, 10, 4, 22, 41, 14, tzinfo=timezone.utc)])

    def test_an_eligible_client_with_no_grants_left_is_a_real_zero(self):
        rl = {"cedar_ember": {"eligible": True, "grants": [], "at_limit": False}}
        self.assertEqual(clilive.reset_state(rl)["count"], 0)


class CacheTest(unittest.TestCase):
    """สปอว์น CLI แพงกว่ายิง HTTP — ถามใหม่ไม่ถี่กว่า TTL"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "claude-live.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_fresh_answer_is_reused_without_spawning_again(self):
        calls = []

        def fetch(config_dir):
            calls.append(config_dir)
            return {"limits": limits_rows()}
        clock = [1000.0]
        first = clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path,
                             clock=lambda: clock[0])
        clock[0] += clilive.TTL - 1
        again = clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path,
                             clock=lambda: clock[0])
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["result"], again["result"])

    def test_a_stale_answer_is_refreshed(self):
        calls = []

        def fetch(config_dir):
            calls.append(config_dir)
            return {"limits": limits_rows()}
        clock = [1000.0]
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: clock[0])
        clock[0] += clilive.TTL + 1
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: clock[0])
        self.assertEqual(len(calls), 2)

    def test_each_account_is_cached_on_its_own(self):
        calls = []

        def fetch(config_dir):
            calls.append(config_dir)
            return {"limits": limits_rows()}
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: 1000.0)
        clilive.live(OTHER_DIR, fetch=fetch, path=self.path, clock=lambda: 1000.0)
        self.assertEqual(calls, [DEFAULT_DIR, OTHER_DIR])

    def test_a_failed_ask_keeps_the_old_answer(self):
        clilive.live(DEFAULT_DIR, fetch=lambda d: {"limits": limits_rows()},
                     path=self.path, clock=lambda: 1000.0)
        out = clilive.live(DEFAULT_DIR, fetch=lambda d: None, path=self.path,
                           clock=lambda: 1000.0 + clilive.TTL + 1)
        self.assertEqual(len(out["result"]["limits"]), 2)
        self.assertEqual(out["fetchedAt"], 1000.0, "อายุต้องเป็นของเดิม ไม่ใช่ตอนนี้")

    def test_an_account_that_cannot_answer_is_not_asked_again_every_minute(self):
        """บัญชีที่ยังไม่ได้ล็อกอินตอบว่างเสมอ และการถามแต่ละครั้งกิน 3-4 วินาที

        ถ้าจำแต่ครั้งที่สำเร็จ บัญชีแบบนี้จะถูกสปอว์นใหม่ทุกรอบ 60 วินาทีตลอดไป
        """
        calls = []

        def fetch(config_dir):
            calls.append(config_dir)
            return None
        clock = [1000.0]
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: clock[0])
        clock[0] += 60
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: clock[0])
        self.assertEqual(len(calls), 1)

    def test_it_tries_again_once_the_backoff_is_over(self):
        calls = []

        def fetch(config_dir):
            calls.append(config_dir)
            return None
        clock = [1000.0]
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: clock[0])
        clock[0] += clilive.TTL + 1
        clilive.live(DEFAULT_DIR, fetch=fetch, path=self.path, clock=lambda: clock[0])
        self.assertEqual(len(calls), 2)

    def test_nothing_cached_and_nothing_fetched_is_none(self):
        self.assertIsNone(clilive.live(DEFAULT_DIR, fetch=lambda d: None,
                                       path=self.path, clock=lambda: 1.0))


class WarmTest(unittest.TestCase):
    """ถามทุกบัญชีพร้อมกัน — เรียงกันทีละตัวกินเวลารวม 20 วินาทีต่อรอบ

    เคสจริง 2026-09-24: สี่บัญชี สปอว์นเรียงกันได้ 21.5 วินาที ขณะที่เอนจินมี
    เพดาน 45 วินาทีและยังต้องไปไล่อ่าน rollout ของ Codex ต่ออีก
    """

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "claude-live.json")
        self.dirs = [DEFAULT_DIR, OTHER_DIR, "/tmp/a", "/tmp/b"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_account_is_asked(self):
        seen = []
        clilive.warm(self.dirs, fetch=lambda d: seen.append(d) or {"limits": limits_rows()},
                     path=self.path, clock=lambda: 1000.0)
        self.assertEqual(sorted(seen), sorted(self.dirs))

    def test_the_answers_land_in_the_cache(self):
        clilive.warm(self.dirs, fetch=lambda d: {"limits": limits_rows()},
                     path=self.path, clock=lambda: 1000.0)
        calls = []
        entry = clilive.live(DEFAULT_DIR, fetch=lambda d: calls.append(d),
                             path=self.path, clock=lambda: 1000.0)
        self.assertEqual(calls, [], "อุ่นแคชแล้วยังไปสปอว์นซ้ำอีก")
        self.assertEqual(len(entry["result"]["limits"]), 2)

    def test_accounts_answered_recently_are_left_alone(self):
        clilive.warm(self.dirs, fetch=lambda d: {"limits": limits_rows()},
                     path=self.path, clock=lambda: 1000.0)
        seen = []
        clilive.warm(self.dirs, fetch=lambda d: seen.append(d),
                     path=self.path, clock=lambda: 1000.0 + clilive.TTL - 1)
        self.assertEqual(seen, [])

    def test_they_really_run_side_by_side(self):
        def slow(config_dir):
            time.sleep(0.2)
            return {"limits": limits_rows()}
        t0 = time.time()
        clilive.warm(self.dirs, fetch=slow, path=self.path, clock=lambda: 1000.0)
        self.assertLess(time.time() - t0, 0.5,
                        "สี่บัญชีเรียงกันคือ 0.8 วินาที — แปลว่ายังไม่ได้ถามพร้อมกัน")


class AtWallTest(unittest.TestCase):
    """server ส่งก้อนใบรีเซ็ตมาเฉพาะเมื่อ client บอกว่าชนเพดานแล้ว (`?at_wall=1`)

    เราจึงถามได้ตอนที่มันเป็นความจริงเท่านั้น — ซึ่งบังเอิญเป็นตอนเดียวที่คนอยากรู้
    """

    @staticmethod
    def util(*percents):
        from aiusage.utilization import Utilization, Window
        return Utilization(fetched_at=datetime.now(timezone.utc),
                           windows=[Window(kind="session", percent=p, resets_at=None,
                                           severity="normal", scope=None, is_active=True)
                                    for p in percents])

    def test_a_full_window_is_the_wall(self):
        self.assertTrue(clilive.at_wall(self.util(3.0, 100.0)))

    def test_almost_full_is_close_enough(self):
        self.assertTrue(clilive.at_wall(self.util(99.0)))

    def test_room_left_is_not_the_wall(self):
        self.assertFalse(clilive.at_wall(self.util(3.0, 98.0)))

    def test_nothing_to_read_is_not_the_wall(self):
        self.assertFalse(clilive.at_wall(None))
        self.assertFalse(clilive.at_wall(self.util()))


class UtilizationTest(unittest.TestCase):
    def test_the_cli_answer_becomes_windows(self):
        util = clilive.utilization({"limits": limits_rows()},
                                   fetched_at=datetime(2026, 9, 24, 8, tzinfo=timezone.utc))
        self.assertEqual([w.kind for w in util.windows], ["session", "weekly_all"])
        self.assertEqual(util.windows[1].percent, 79.0)

    def test_an_answer_without_rows_is_no_reading(self):
        self.assertIsNone(clilive.utilization({"limits": []},
                                              fetched_at=datetime.now(timezone.utc)))


if __name__ == "__main__":
    unittest.main()
