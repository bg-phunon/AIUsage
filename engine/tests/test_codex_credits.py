"""เครดิตของ Codex — ตัวเลขที่ล็อกส่งมาอยู่แล้วแต่ไม่เคยถูกอ่าน

หน้า usage ของ OpenAI โชว์ "Credits remaining" คู่กับ weekly limit และ log ก็มี
ฟิลด์ credits ติดมาในทุกก้อน rate_limits — เครดิตคือโควตาส่วนที่ใช้ต่อได้หลังชน
เพดานแผน จึงเป็นคนละเรื่องกับ % และต้องไม่ถูกยุบรวมกัน
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_credits", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def record(ts, credits, pct=36.0):
    return {"timestamp": ts.isoformat().replace("+00:00", "Z"), "type": "event_msg",
            "payload": {"type": "token_count",
                        "info": {"last_token_usage": {"total_tokens": 5}},
                        "rate_limits": {
                            "limit_id": "codex", "limit_name": None,
                            "primary": {"used_percent": pct, "window_minutes": 10080,
                                        "resets_at": (ts + timedelta(days=4)).timestamp()},
                            "secondary": None, "credits": credits}}}


class CreditsTest(unittest.TestCase):
    def setUp(self):
        self.saved = engine.now_utc
        engine.now_utc = lambda: NOW

    def tearDown(self):
        engine.now_utc = self.saved

    def stats(self, records):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "sessions", "2026", "09", "10")
            os.makedirs(d)
            with open(os.path.join(d, "rollout.jsonl"), "w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
            return engine.codex_stats(tmp)

    def test_reads_the_balance(self):
        cs = self.stats([record(NOW - timedelta(minutes=5),
                                {"has_credits": True, "unlimited": False, "balance": "250"})])
        self.assertEqual(cs["credits"], {"balance": 250.0, "unlimited": False})

    def test_zero_balance_is_a_real_zero_not_a_missing_value(self):
        """0 เครดิตต่างจาก "ไม่รู้ว่ามีกี่เครดิต" — อันแรกบอกได้ว่าใช้ต่อไม่ได้แล้ว"""
        cs = self.stats([record(NOW - timedelta(minutes=5),
                                {"has_credits": False, "unlimited": False, "balance": "0"})])
        self.assertEqual(cs["credits"], {"balance": 0.0, "unlimited": False})

    def test_unlimited_is_carried_through_not_flattened_to_a_number(self):
        cs = self.stats([record(NOW - timedelta(minutes=5),
                                {"has_credits": True, "unlimited": True, "balance": "0"})])
        self.assertEqual(cs["credits"], {"balance": 0.0, "unlimited": True})

    def test_the_newest_record_wins(self):
        cs = self.stats([
            record(NOW - timedelta(hours=2), {"has_credits": True, "unlimited": False, "balance": "500"}),
            record(NOW - timedelta(minutes=1), {"has_credits": True, "unlimited": False, "balance": "120"}),
        ])
        self.assertEqual(cs["credits"]["balance"], 120.0)

    def test_no_credits_field_at_all_stays_none(self):
        rec = record(NOW - timedelta(minutes=5), None)
        del rec["payload"]["rate_limits"]["credits"]
        self.assertIsNone(self.stats([rec])["credits"])

    def test_a_balance_that_is_not_a_number_is_ignored(self):
        cs = self.stats([record(NOW - timedelta(minutes=5),
                                {"has_credits": True, "unlimited": False, "balance": "หลายอัน"})])
        self.assertIsNone(cs["credits"])


if __name__ == "__main__":
    unittest.main()
