"""Muse: นับ token จาก model_completed ใน session.jsonl — ไม่มีโควตา/% ให้อ่าน

ยอดที่นับคือ input+output ต่อ call เท่านั้น: cached/cache_read เป็นส่วนย่อยของ
input และ reasoning อยู่ใน output (บวกแยกแล้วเบิ้ล) · goal_usage_attribution คือ
ยอดชุดเดียวกันที่แยกตามเจ้าของ ต้องข้าม ไม่งั้นนับซ้ำ · event เดียวกันที่โผล่
ทั้ง log แม่และ subagent ตัดซ้ำด้วย envelope id
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import muselogs


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
DAY = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)


def completed(rid, ts, usage, model="muse-spark-1.3-contributor"):
    return {
        "id": rid, "payload_type": "runtime.session",
        "recorded_at": int(ts.timestamp() * 1e6),
        "payload": {"kind": "run",
                    "event": {"kind": "model_completed", "model": model,
                              "usage": usage}},
    }


def attribution(ts, usage):
    # ยอดชุดเดียวกับ model_completed แต่แยกตามเจ้าของ — ต้องไม่ถูกนับ
    return {
        "id": "attr-1", "payload_type": "runtime.session",
        "recorded_at": int(ts.timestamp() * 1e6),
        "payload": {"kind": "run", "event": {
            "kind": "goal_usage_attribution", "usage_family": "provider",
            "record": {"quantity": dict(usage, unit="tokens", reported=True)}}},
    }


def write_log(path, records, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec if isinstance(rec, str) else json.dumps(rec))
            fh.write("\n")
    # เพิ่งเขียน = mtime ใหม่กว่า cut เสมอ ไม่ว่าจะรันวันไหน
    ts = mtime.timestamp() if mtime is not None else datetime.now(timezone.utc).timestamp()
    os.utime(path, (ts, ts))


class MuseStatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "sessions")

    def tearDown(self):
        self.tmp.cleanup()

    def log(self, *parts):
        return os.path.join(self.dir, *parts, "session.jsonl")

    def test_today_and_week_windows(self):
        write_log(self.log("2026", "09", "30", "aaa"), [
            completed("r1", NOW - timedelta(hours=1),
                      {"input_tokens": 1000, "output_tokens": 100,
                       "cached_tokens": 900, "cache_read_tokens": 900,
                       "reasoning_tokens": 10}),
            completed("r2", NOW - timedelta(days=3),
                      {"input_tokens": 2000, "output_tokens": 200}),
            completed("r3", NOW - timedelta(days=8),
                      {"input_tokens": 9999, "output_tokens": 9999}),
        ])
        st = muselogs.muse_stats(self.dir, NOW, day_start=DAY)
        self.assertEqual(st["today"], {"tokens": 1100, "calls": 1})
        self.assertEqual(st["week"], {"tokens": 3300, "calls": 2})
        self.assertEqual(st["model"], "muse-spark-1.3-contributor")

    def test_attribution_and_duplicates_ignored(self):
        usage = {"input_tokens": 500, "output_tokens": 50}
        write_log(self.log("2026", "09", "30", "aaa"), [
            completed("r1", NOW - timedelta(hours=1), usage),
            attribution(NOW - timedelta(hours=1), usage),
            "this is not json\n",
            {"id": "r2", "payload_type": "runtime.session",
             "recorded_at": int((NOW - timedelta(hours=2)).timestamp() * 1e6),
             "payload": {"kind": "run", "event": {"kind": "started"}}},
        ])
        # event เดียวกันใน log ของ subagent — นับครั้งเดียว
        write_log(os.path.join(self.dir, "2026", "09", "30", "aaa",
                               "subagent", "bbb", "session.jsonl"), [
            completed("r1", NOW - timedelta(hours=1), usage),
        ])
        st = muselogs.muse_stats(self.dir, NOW, day_start=DAY)
        self.assertEqual(st["week"], {"tokens": 550, "calls": 1})

    def test_missing_dir_is_empty_not_error(self):
        st = muselogs.muse_stats(os.path.join(self.tmp.name, "nope"), NOW,
                                 day_start=DAY)
        self.assertEqual(st["today"], {"tokens": 0, "calls": 0})
        self.assertEqual(st["week"], {"tokens": 0, "calls": 0})
        self.assertIsNone(st["model"])
        self.assertEqual(st["models"], [])

    def test_latest_model_wins(self):
        write_log(self.log("2026", "09", "30", "aaa"), [
            completed("r1", NOW - timedelta(hours=2),
                      {"input_tokens": 1, "output_tokens": 1}, model="old-model"),
            completed("r2", NOW - timedelta(hours=1),
                      {"input_tokens": 1, "output_tokens": 1}, model="new-model"),
        ])
        st = muselogs.muse_stats(self.dir, NOW, day_start=DAY)
        self.assertEqual(st["model"], "new-model")
        self.assertEqual(st["models"], ["new-model", "old-model"])

    def test_series_is_sorted_and_deduped(self):
        # mtime ปักไว้ที่ NOW — ไม่งั้นตัวกรอง mtime จะตัดไฟล์ทิ้งเพราะ since
        # ของ fixture อยู่หลังเวลาจริง (เคสเดียวกับ test_stale_files_skipped)
        write_log(self.log("2026", "09", "30", "aaa"), [
            completed("r1", NOW - timedelta(hours=1),
                      {"input_tokens": 1000, "output_tokens": 100}),
            completed("r2", NOW - timedelta(hours=3),
                      {"input_tokens": 2000, "output_tokens": 200}),
        ], mtime=NOW)
        write_log(os.path.join(self.dir, "2026", "09", "30", "aaa",
                               "subagent", "bbb", "session.jsonl"), [
            completed("r1", NOW - timedelta(hours=1),
                      {"input_tokens": 1000, "output_tokens": 100}),
        ], mtime=NOW)
        series = muselogs.muse_series(self.dir, NOW - timedelta(hours=2))
        self.assertEqual(series, [(NOW - timedelta(hours=1), 1100)])
        full = muselogs.muse_series(self.dir, NOW - timedelta(days=1))
        self.assertEqual([t for _, t in full], [2200, 1100])

    def test_stale_files_skipped(self):
        path = self.log("2026", "09", "20", "old")
        write_log(path, [completed("r1", NOW - timedelta(days=10),
                                   {"input_tokens": 5, "output_tokens": 5})])
        old = (NOW - timedelta(days=10)).timestamp()
        os.utime(path, (old, old))
        st = muselogs.muse_stats(self.dir, NOW, day_start=DAY)
        self.assertEqual(st["week"], {"tokens": 0, "calls": 0})


if __name__ == "__main__":
    unittest.main()
