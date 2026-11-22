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

    def test_a_failed_ask_records_last_error_but_keeps_the_old_answer(self):
        # เคสจริง 2026-11-15: token หมดอายุ ถามล้มทุกรอบอยู่ 5 วันโดยไม่มีร่องรอย
        # ที่ไหนเลยว่าเพราะอะไร — แคชค้างที่ 10 พ.ย. และจอโชว์เลขเก่าอย่างมั่นใจ
        engine.codex_live(fetch=lambda: RESULT, path=self.path, clock=lambda: FETCHED)
        engine._codex_last_error = "401 token_expired"
        got = engine.codex_live(fetch=lambda: None, path=self.path,
                                clock=lambda: FETCHED + engine.CODEX_LIVE_TTL + 1)
        self.assertEqual(got["fetchedAt"], FETCHED, "คำตอบเก่าต้องยังอยู่ครบ")
        self.assertEqual(got["result"], RESULT)
        self.assertEqual(got["lastError"], "401 token_expired")
        self.assertEqual(got["lastErrorAt"], FETCHED + engine.CODEX_LIVE_TTL + 1)
        on_disk = engine.read_json(self.path, None)
        self.assertEqual(on_disk["lastError"], "401 token_expired",
                         "error ต้องลงไฟล์ด้วย — รอบถัดไปเป็น process ใหม่")

    def test_success_after_failure_clears_last_error(self):
        engine.codex_live(fetch=lambda: RESULT, path=self.path, clock=lambda: FETCHED)
        engine._codex_last_error = "401 token_expired"
        engine.codex_live(fetch=lambda: None, path=self.path,
                          clock=lambda: FETCHED + engine.CODEX_LIVE_TTL + 1)
        later = FETCHED + 2 * engine.CODEX_LIVE_TTL + 2
        got = engine.codex_live(fetch=lambda: RESULT, path=self.path, clock=lambda: later)
        self.assertEqual(got["fetchedAt"], later)
        self.assertNotIn("lastError", got)
        self.assertNotIn("lastErrorAt", got)


class FetchErrorTest(unittest.TestCase):
    """CLI ตอบ error กลับมา (ไม่ใช่ result) — ข้อความต้องไม่หายไปกับ DEVNULL"""

    def _fake_binary(self, body):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "codex")
        with open(path, "w") as f:
            f.write("#!%s\n%s" % (sys.executable, body))
        os.chmod(path, 0o755)
        return path

    def test_rpc_error_message_is_kept(self):
        fake = self._fake_binary(
            "import json,sys\n"
            "for line in sys.stdin:\n"
            "    m=json.loads(line)\n"
            "    if m.get('id')==1: print(json.dumps({'id':1,'result':{}}),flush=True)\n"
            "    elif m.get('id')==2: print(json.dumps({'id':2,'error':{'code':-32603,"
            "'message':'failed: 401 token_expired'}}),flush=True)\n")
        engine._codex_last_error = None
        self.assertIsNone(engine.fetch_codex_rate_limits(binary=fake, timeout=5))
        self.assertIn("token_expired", engine._codex_last_error or "")


class LiveMetaTest(unittest.TestCase):
    """เมตาของคำตอบสดที่ collect() ต้องส่งต่อไป snapshot"""

    def test_fetched_at_comes_from_the_cache_stamp(self):
        got = engine.codex_live_fetched_at({"fetchedAt": FETCHED, "result": RESULT})
        self.assertEqual(got, datetime.fromtimestamp(FETCHED, timezone.utc))

    def test_error_only_cache_has_no_fetched_at(self):
        self.assertIsNone(engine.codex_live_fetched_at({"lastError": "x", "lastErrorAt": 1}))
        self.assertIsNone(engine.codex_live_fetched_at(None))

    def test_dead_live_source_surfaces_as_item_error(self):
        live = {"fetchedAt": FETCHED, "result": RESULT,
                "lastError": "401 token_expired", "lastErrorAt": FETCHED + 999}
        stale = {"win": {"used_percent": 100.0, "window_minutes": 10080,
                         "resets_at": WEEK_END},
                 "ts": datetime.fromtimestamp(FETCHED, timezone.utc), "seen": []}
        cs = {"windows": {"primary": stale}}
        self.assertEqual(engine.codex_live_error(live, cs), "401 token_expired")

    def test_fresher_log_reading_silences_the_error(self):
        # แหล่งสดตาย แต่ล็อกมีเลขใหม่กว่าแคช — เลขบนจอมีที่มา ไม่ต้องขึ้นว่าพัง
        live = {"fetchedAt": FETCHED, "result": RESULT,
                "lastError": "401 token_expired", "lastErrorAt": FETCHED + 999}
        fresh = {"win": {"used_percent": 3.0, "window_minutes": 10080,
                         "resets_at": WEEK_END},
                 "ts": datetime.fromtimestamp(FETCHED + 500, timezone.utc), "seen": []}
        cs = {"windows": {"primary": fresh}}
        self.assertIsNone(engine.codex_live_error(live, cs))

    def test_no_error_recorded_means_no_item_error(self):
        live = {"fetchedAt": FETCHED, "result": RESULT}
        self.assertIsNone(engine.codex_live_error(live, {"windows": {}}))
        self.assertIsNone(engine.codex_live_error(None, {"windows": {}}))


if __name__ == "__main__":
    unittest.main()
