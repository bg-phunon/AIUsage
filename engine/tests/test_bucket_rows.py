import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage.buckets import Bucket  # noqa: E402

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")

spec = importlib.util.spec_from_file_location("engine_main", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

QWEN = Bucket("qwenc", "Qwen Cloud", "dashscope.aliyuncs.com", False)
TABLE = {"deepseek-v4-flash-0731": QWEN}


def iso_z(dt):
    return dt.isoformat().replace("+00:00", "Z")


def hit_record(event_ts, reset, window="1-week"):
    text = ("API Error: Request rejected (429) · Your token-plan %s quota has been "
            "exhausted. The quota will reset at %s UTC."
            % (window, reset.strftime("%m-%d %H:%M:%S")))
    return {
        "timestamp": iso_z(event_ts),
        "error": "rate_limit",
        "apiErrorIsTransient": False,
        "message": {"content": [{"type": "text", "text": text}]},
    }


def usage_record(event_ts, model):
    return {
        "timestamp": iso_z(event_ts),
        "requestId": "req-%s" % event_ts.timestamp(),
        "message": {
            "id": "msg-%s" % event_ts.timestamp(),
            "model": model,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    }


class BucketRowsQwenHitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.acc = {"dir": self.tmp.name, "label": "default"}
        self.now = engine.now_utc().replace(microsecond=0)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, records):
        proj = os.path.join(self.tmp.name, "projects", "p")
        os.makedirs(proj, exist_ok=True)
        with open(os.path.join(proj, "s.jsonl"), "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

    def test_exhausted_row_survives_without_traffic(self):
        """โควตาเต็ม = ใช้ไม่ได้ = ไม่มี traffic ใหม่ — แถว 100% ต้องไม่หายเพราะเหตุนั้นเอง"""
        reset = self.now + timedelta(days=2)
        self.write([hit_record(self.now - timedelta(days=3), reset)])
        rows = engine.bucket_rows(self.acc, TABLE)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["group"], "Qwen Cloud")
        self.assertEqual(row["weekPct"], 100.0)
        self.assertIsNone(row["pct"])
        self.assertEqual(row["pctSource"], "official")
        self.assertEqual(row["resetAt"], iso_z(reset))
        self.assertEqual(row["tokens"], 0)
        self.assertIsNone(row["cost"])

    def test_expired_hit_without_traffic_yields_nothing(self):
        """hit ที่รีเซ็ตผ่านไปแล้วไม่ใช่หลักฐานว่ายังเต็ม — อย่าเสกถังขึ้นมา"""
        self.write([hit_record(self.now - timedelta(days=3),
                               self.now - timedelta(hours=1))])
        self.assertEqual(engine.bucket_rows(self.acc, TABLE), [])

    def test_data_fetched_at_is_hit_time_not_scan_time(self):
        """dataFetchedAt คือ "เห็นคำประกาศเมื่อไหร่" ไม่ใช่ "สแกนรอบล่าสุดเมื่อไหร่" """
        seen = self.now - timedelta(days=3)
        self.write([hit_record(seen, self.now + timedelta(days=2))])
        row = engine.bucket_rows(self.acc, TABLE)[0]
        self.assertEqual(row["dataFetchedAt"], iso_z(seen))

    def anchor(self, used=4.8, at_hours_ago=3, reset_in_days=6):
        return {"usedPct": used,
                "at": self.now - timedelta(hours=at_hours_ago),
                "resetAt": self.now + timedelta(days=reset_in_days)}

    def test_dashboard_anchor_shows_as_lower_bound(self):
        """จุดยึดจากแดชบอร์ด: % ที่ใช้ไปมีแต่เพิ่ม จึงเป็น lower bound แท้ๆ"""
        rows = engine.bucket_rows(self.acc, TABLE, self.anchor())
        self.assertEqual(len(rows), 1, "มี anchor ก็ต้องมีถัง แม้ไม่มี traffic")
        row = rows[0]
        self.assertEqual(row["weekPct"], 4.8)
        self.assertEqual(row["weekConfidence"], "lower_bound")
        self.assertIsNone(row["pctSource"], "anchor ไม่ใช่ตัวเลขทางการ")
        self.assertEqual(row["dataFetchedAt"], iso_z(self.now - timedelta(hours=3)))
        self.assertEqual(row["resetAt"], iso_z(self.now + timedelta(days=6)))

    def test_expired_anchor_is_ignored(self):
        """หน้าต่างรีเซ็ตไปแล้ว ค่าจดเก่าไม่ใช่ lower bound ของหน้าต่างใหม่"""
        stale = self.anchor(reset_in_days=-1)
        self.assertEqual(engine.bucket_rows(self.acc, TABLE, stale), [])

    def test_active_hit_beats_anchor(self):
        """429 สดคือคำประกาศจากผู้ให้บริการ — ชนะค่าจดจากแดชบอร์ดเสมอ"""
        reset = self.now + timedelta(days=2)
        self.write([hit_record(self.now - timedelta(hours=1), reset)])
        rows = engine.bucket_rows(self.acc, TABLE, self.anchor())
        self.assertEqual(rows[0]["weekPct"], 100.0)
        self.assertEqual(rows[0]["weekConfidence"], "valid")
        self.assertEqual(rows[0]["pctSource"], "official")

    def test_hit_applies_to_bucket_with_traffic(self):
        reset = self.now + timedelta(days=2)
        self.write([
            usage_record(self.now - timedelta(hours=1), "deepseek-v4-flash-0731"),
            hit_record(self.now - timedelta(minutes=30), reset),
        ])
        rows = engine.bucket_rows(self.acc, TABLE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["weekPct"], 100.0)
        self.assertGreater(rows[0]["weekTokens"], 0)


if __name__ == "__main__":
    unittest.main()
