"""แถว Antigravity จากผลอ่านจอ `/usage` ของ agy"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_antigravity", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 11, 22, 13, 0, tzinfo=timezone.utc)
FETCHED = (NOW - timedelta(minutes=5)).timestamp()


def reading():
    return {"plan": "AI Pro", "groups": [
        {"label": "Gemini",
         "session": {"usedPct": 13.18, "resetAt": NOW + timedelta(hours=4)},
         "weekly": {"usedPct": 4.48, "resetAt": NOW + timedelta(days=6)}},
        {"label": "Claude",
         "session": {"usedPct": 0.0, "resetAt": None},
         "weekly": {"usedPct": 0.0, "resetAt": None}},
        {"label": "Argon", "weekly": {"usedPct": 0.0, "resetAt": None}},
    ]}


class AntigravityItemTest(unittest.TestCase):
    def test_gemini_is_primary_others_are_model_windows(self):
        it = engine.antigravity_item(reading(), FETCHED, FETCHED, None, NOW)
        self.assertEqual((it["group"], it["label"], it["plan"]), ("Antigravity", "Antigravity", "AI Pro"))
        self.assertEqual(it["pct"], 13.2)
        self.assertEqual(it["weekPct"], 4.5)
        self.assertEqual([w["label"] for w in it["modelWindows"]], ["Claude 5h", "Claude 7d", "Argon"])
        self.assertIsNone(it["confidence"])
        self.assertEqual(it["pctSource"], "official")
        self.assertIsNotNone(it["dataFetchedAt"])
        self.assertIsNone(it["error"])

    def test_use_after_reading_is_lower_bound(self):
        it = engine.antigravity_item(reading(), FETCHED, FETCHED + 600, None, NOW)
        self.assertEqual(it["confidence"], "lower_bound")
        self.assertEqual(it["weekConfidence"], "lower_bound")
        self.assertTrue(all(w["confidence"] == "lower_bound" for w in it["modelWindows"]))

    def test_window_past_reset_is_unknown_not_zero(self):
        later = NOW + timedelta(hours=5)
        it = engine.antigravity_item(reading(), FETCHED, FETCHED, None, later)
        self.assertIsNone(it["pct"])
        self.assertEqual(it["weekPct"], 4.5)

    def test_error_without_reading(self):
        it = engine.antigravity_item(None, None, None, "trust_prompt", NOW)
        self.assertIsNone(it["pct"])
        self.assertIsNone(it["plan"])
        self.assertIn("trust", it["error"])
        self.assertIsNone(it["pctSource"])

    def test_error_hidden_when_old_reading_exists(self):
        it = engine.antigravity_item(reading(), FETCHED, FETCHED, "screen_unparsed", NOW)
        self.assertIsNone(it["error"])


if __name__ == "__main__":
    unittest.main()
