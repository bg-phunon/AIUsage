import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aiusage import agytui  # noqa: E402

NOW = datetime(2026, 11, 22, 12, 40, tzinfo=timezone.utc)

# จอจริงจาก agy 1.5.14 (2026-11-22) หลัง strip ANSI — มีทั้งหน้าแรกและหน้าที่เลื่อนลง
SCREEN = """\
 Welcome to the Antigravity CLI.
▀▀▀▀▀▀       someone@example.com (Google AI Pro)
└ Models & Quota

  Account: someone@example.com

GEMINI MODELS
  Models within this group: Gemini 4 Neon, Gemini 4 Hydrogen, Orchestrator (Neon), Gemini 3.8 Flash

  Weekly Limit Remaining
    [█████████████████████████████████████████████████░] 99.65%
    Refreshes in 167h 56m

  Five Hour Limit Remaining
[█████████████████████████████████████████████████░] 98.76%
Refreshes in 4h 56m


CLAUDE AND GPT MODELS
  Models within this group: Claude Opus 5.5, Claude Sonnet 5.5, GPT-OSS 120B

  Weekly Limit Remaining
[██████████████████████████████████████████████████] 100.00%
Quota available

  Five Hour Limit Remaining
[██████████████████████████████████████████████████] 100.00%
Quota available


GEMINI 4 ARGON
  For paid Pro plans, Argon quota is separate. Higher Argon quota (included as part of the larger Gemini quota bucket) i

  (1–27 of 38 lines)
5m
CLAUDE AND GPT MODELS
  Weekly Limit Remaining
[██████████████████████████████████████████████████] 100.00%
Quota available
GEMINI 4 ARGON
  Gemini 4 Argon Weekly Limit
[██████████████████████████████████████████████████] 100.00%
Quota available
  │Within each group, models share a weekly limit and a 5-hour limit. Quota is
  │consumed proportionally to the cost of the tokens.
2–38 of 38 lines)
"""


class ParseScreenTest(unittest.TestCase):
    def test_real_screen(self):
        got = agytui.parse_screen(SCREEN, NOW)
        self.assertEqual(got["plan"], "AI Pro")
        labels = [g["label"] for g in got["groups"]]
        self.assertEqual(labels, ["Gemini", "Claude", "Argon"])
        gem = got["groups"][0]
        # จอบอก "ที่เหลือ" — เก็บเป็น "ที่ใช้ไป"
        self.assertAlmostEqual(gem["weekly"]["usedPct"], 0.35)
        self.assertAlmostEqual(gem["session"]["usedPct"], 1.24)
        self.assertEqual(gem["weekly"]["resetAt"], NOW + timedelta(hours=167, minutes=56))
        self.assertEqual(gem["session"]["resetAt"], NOW + timedelta(hours=4, minutes=56))
        claude = got["groups"][1]
        self.assertEqual(claude["weekly"], {"usedPct": 0.0, "resetAt": None})
        self.assertEqual(claude["session"], {"usedPct": 0.0, "resetAt": None})
        argon = got["groups"][2]
        self.assertEqual(argon["weekly"]["usedPct"], 0.0)
        self.assertNotIn("session", argon)

    def test_explanation_text_does_not_create_windows(self):
        # ย่อหน้าอธิบายพูดถึง "weekly limit" แต่ไม่มี % ตาม — ต้องไม่งอกช่อง
        got = agytui.parse_screen(SCREEN, NOW)
        self.assertEqual(set(got["groups"][2]), {"label", "weekly"})

    def test_nothing_readable_is_none(self):
        self.assertIsNone(agytui.parse_screen("Welcome\n? for shortcuts\n", NOW))

    def test_day_units(self):
        text = "GEMINI MODELS\n Weekly Limit Remaining\n [██░] 40.00%\n Refreshes in 2d 3h\n"
        got = agytui.parse_screen(text, NOW)
        self.assertEqual(got["groups"][0]["weekly"]["resetAt"], NOW + timedelta(days=2, hours=3))
        self.assertAlmostEqual(got["groups"][0]["weekly"]["usedPct"], 60.0)
        self.assertIsNone(got["plan"])

    def test_ansi_is_stripped(self):
        raw = "\x1b[1mGEMINI MODELS\x1b[0m\r\n Weekly Limit Remaining\x1b[2K\r\n [█] 75.5%\r\n"
        got = agytui.parse_screen(agytui.strip_ansi(raw), NOW)
        self.assertAlmostEqual(got["groups"][0]["weekly"]["usedPct"], 24.5)


class SerializeTest(unittest.TestCase):
    def test_round_trip(self):
        reading = agytui.parse_screen(SCREEN, NOW)
        back = agytui.load_reading(json.loads(json.dumps(agytui.serialize(reading))))
        self.assertEqual(back, reading)

    def test_bad_shape_is_none(self):
        self.assertIsNone(agytui.load_reading({"groups": "x"}))
        self.assertIsNone(agytui.load_reading({"groups": [{"label": "Gemini"}]}))


class TrustTest(unittest.TestCase):
    def screen(self, path, selected="> Yes, I trust this folder"):
        return ("Accessing workspace:\n\n%s\n\nDo you trust the contents of this project?\n"
                "%s\n  No, exit\n" % (path, selected))

    def test_accept_only_our_folder(self):
        self.assertEqual(agytui.trust_prompt_action(self.screen(agytui.PROBE_DIR)), "accept")

    def test_other_folder_aborts(self):
        self.assertEqual(agytui.trust_prompt_action(self.screen("/Users/x/project")), "abort")

    def test_no_selected_yes_aborts(self):
        got = agytui.trust_prompt_action(self.screen(agytui.PROBE_DIR, "  Yes, I trust this folder"))
        self.assertEqual(got, "abort")

    def test_no_prompt(self):
        self.assertIsNone(agytui.trust_prompt_action("? for shortcuts"))


class DueTest(unittest.TestCase):
    def test_never_used(self):
        self.assertFalse(agytui.due({}, None, 10_000))

    def test_first_time(self):
        self.assertTrue(agytui.due({}, 5_000, 10_000))

    def test_too_soon(self):
        self.assertFalse(agytui.due({"triedAt": 9_500}, 9_900, 10_000))

    def test_probe_own_traces_do_not_count(self):
        # การถามรอบก่อนแตะ conversation ของ CLI เอง — ไม่ใช่การใช้งาน
        tried = 10_000
        self.assertFalse(agytui.due({"triedAt": tried}, tried + 30, tried + 2_000))

    def test_real_use_after_probe(self):
        tried = 10_000
        self.assertTrue(agytui.due({"triedAt": tried}, tried + 600, tried + 2_000))


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "agy-live.json")

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_success_stores_reading(self):
        ok = agytui.probe(self.path, fetch=lambda: agytui.parse_screen(SCREEN, NOW),
                          clock=lambda: 1000.0)
        self.assertTrue(ok)
        store = self.read()
        self.assertEqual(store["fetchedAt"], 1000.0)
        self.assertEqual(store["reading"]["plan"], "AI Pro")
        self.assertNotIn("lastError", store)

    def test_failure_records_error(self):
        def boom():
            raise RuntimeError("trust_prompt")
        self.assertFalse(agytui.probe(self.path, fetch=boom, clock=lambda: 50.0))
        store = self.read()
        self.assertEqual(store["lastError"], "trust_prompt")
        self.assertEqual(store["lastErrorAt"], 50.0)

    def test_unparsed_keeps_old_reading(self):
        agytui.probe(self.path, fetch=lambda: agytui.parse_screen(SCREEN, NOW),
                     clock=lambda: 1000.0)
        agytui.probe(self.path, fetch=lambda: None, clock=lambda: 2000.0)
        store = self.read()
        self.assertEqual(store["lastError"], "screen_unparsed")
        self.assertEqual(store["fetchedAt"], 1000.0)
        self.assertIn("reading", store)

    def test_kick_records_tried_before_spawn(self):
        spawned = []
        agytui.kick(5_000, self.path, clock=lambda: 10_000.0, spawn=spawned.append)
        self.assertEqual(spawned, [self.path])
        self.assertEqual(self.read()["triedAt"], 10_000.0)
        self.assertFalse(agytui.kick(5_000, self.path, clock=lambda: 10_060.0,
                                     spawn=spawned.append))


class ActivityTest(unittest.TestCase):
    def test_latest_mtime_across_dirs(self):
        base = tempfile.mkdtemp()
        conv = os.path.join(base, "antigravity", "conversations")
        os.makedirs(conv)
        f = os.path.join(conv, "a.pb")
        open(f, "w").close()
        os.utime(f, (5000, 5000))
        os.utime(conv, (4000, 4000))
        self.assertEqual(agytui.latest_activity(base), 5000)

    def test_missing_dirs(self):
        self.assertIsNone(agytui.latest_activity(tempfile.mkdtemp()))


if __name__ == "__main__":
    unittest.main()
