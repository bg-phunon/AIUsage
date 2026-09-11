"""เลขสดของ Codex จาก `codex app-server` → account/rateLimits/read

เคสจริง 2026-09-11: session ที่เปิดค้างตอนชนลิมิตเขียนแต่ถัง Spark ลงล็อก แอปจึงค้าง
6% อยู่สามชั่วโมงทั้งที่ของจริง 23% — ถาม CLI ตรงๆ ได้เลขสดโดยไม่เรียกโมเดล
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_live", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

FETCHED = 1_789_600_000.0
WEEK_END = 1_789_739_172

# รูปเดียวกับคำตอบจริงของ 2026-09-11
RESULT = {
    "rateLimits": {"limitId": "codex_bengalfox",
                   "primary": {"usedPercent": 0, "windowDurationMins": 300, "resetsAt": 1789163567}},
    "rateLimitsByLimitId": {
        "codex": {"limitId": "codex", "secondary": None,
                  "primary": {"usedPercent": 23, "windowDurationMins": 10080, "resetsAt": WEEK_END}},
        "codex_bengalfox": {"limitId": "codex_bengalfox",
                            "primary": {"usedPercent": 0, "windowDurationMins": 300, "resetsAt": 1}}},
    "rateLimitResetCredits": {"availableCount": 1, "credits": [
        {"id": "b", "status": "available", "expiresAt": 1791153674, "grantedAt": 1},
        {"id": "a", "status": "redeemed", "expiresAt": 1791000000, "grantedAt": 1}]},
}


class WindowsTest(unittest.TestCase):
    def test_takes_the_real_codex_bucket_not_the_spark_placeholder(self):
        wins = engine.codex_live_windows({"fetchedAt": FETCHED, "result": RESULT})
        self.assertEqual(wins["primary"]["win"]["used_percent"], 23.0)
        self.assertEqual(wins["primary"]["win"]["window_minutes"], 10080)
        self.assertNotIn("secondary", wins)

    def test_live_reading_beats_a_stale_log_reading(self):
        stale = {"win": {"used_percent": 6.0, "window_minutes": 10080, "resets_at": WEEK_END},
                 "ts": datetime.fromtimestamp(FETCHED - 3 * 3600, timezone.utc), "seen": []}
        cs = {"tokens": 1, "lastActivity": None, "windows": {"primary": stale}}
        for slot, entry in engine.codex_live_windows({"fetchedAt": FETCHED, "result": RESULT}).items():
            cs["windows"][slot] = entry
        now = datetime.fromtimestamp(FETCHED + 60, timezone.utc)
        self.assertEqual(engine.codex_fields(cs, now)["weekPct"], 23.0)

    def test_nothing_yields_nothing(self):
        self.assertEqual(engine.codex_live_windows(None), {})


class ResetsTest(unittest.TestCase):
    def test_only_available_credits_count(self):
        got = engine.codex_live_resets({"fetchedAt": FETCHED, "result": RESULT})
        self.assertEqual(got, [datetime.fromtimestamp(1791153674, timezone.utc)])

    def test_server_saying_zero_is_an_empty_list_not_none(self):
        got = engine.codex_live_resets({"fetchedAt": FETCHED, "result": {
            "rateLimitResetCredits": {"availableCount": 0, "credits": []}}})
        self.assertEqual(got, [])

    def test_no_summary_is_none_so_the_config_can_fill_in(self):
        self.assertIsNone(engine.codex_live_resets({"fetchedAt": FETCHED, "result": {}}))
        self.assertIsNone(engine.codex_live_resets(None))


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "codex-live.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_within_ttl_the_cli_is_not_asked_again(self):
        calls = []
        fetch = lambda: calls.append(1) or RESULT
        engine.codex_live(fetch=fetch, path=self.path, clock=lambda: FETCHED)
        engine.codex_live(fetch=fetch, path=self.path, clock=lambda: FETCHED + 30)
        self.assertEqual(len(calls), 1, "ถาม CLI ถี่เกินไป — ทุกรอบคือ process ใหม่หนึ่งตัว")

    def test_a_failed_ask_falls_back_to_the_old_answer(self):
        engine.codex_live(fetch=lambda: RESULT, path=self.path, clock=lambda: FETCHED)
        got = engine.codex_live(fetch=lambda: None, path=self.path,
                                clock=lambda: FETCHED + engine.CODEX_LIVE_TTL + 1)
        self.assertEqual(got["fetchedAt"], FETCHED, "อายุของคำตอบเก่าต้องติดไปด้วย")

    def test_missing_binary_is_none_not_a_crash(self):
        self.assertIsNone(engine.fetch_codex_rate_limits(binary="/nonexistent/codex", timeout=1))


if __name__ == "__main__":
    unittest.main()
