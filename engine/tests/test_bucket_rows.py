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
        self.write([usage_record(self.now - timedelta(hours=1), "deepseek-v4-flash-0731")])
        rows = engine.bucket_rows(self.acc, TABLE, self.anchor())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["weekPct"], 4.8)
        self.assertEqual(row["weekConfidence"], "lower_bound")
        self.assertIsNone(row["pctSource"], "anchor ไม่ใช่ตัวเลขทางการ")
        self.assertEqual(row["dataFetchedAt"], iso_z(self.now - timedelta(hours=3)))
        self.assertEqual(row["resetAt"], iso_z(self.now + timedelta(days=6)))

    def test_anchor_does_not_conjure_buckets(self):
        """bucket_rows รันทุกบัญชี — anchor ที่เสกถังได้จะงอก Qwen ซ้ำทุกบัญชี
        ทั้งที่แผนมีใบเดียว (เคยเกิดจริง: 4.8% โผล่ 4 แถว)"""
        self.assertEqual(engine.bucket_rows(self.acc, TABLE, self.anchor()), [])

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



ALBB = Bucket("albb", "Alibaba Cloud", "token-plan.ap-southeast-1.maas.aliyuncs.com", False)
QWENC = Bucket("qwenc", "Qwen Cloud", "token-plan.ap-southeast-1.maas.aliyuncs.com", False)
TWO_PLANS = {"deepseek-v4-flash-0731": QWENC, "qwen3-coder-plus": ALBB}


class TwoTokenPlansTest(BucketRowsQwenHitTest):
    """สองบัญชี token-plan — 429 ของใบหนึ่งห้ามทำให้อีกใบขึ้น 100%"""

    def write_files(self, files):
        proj = os.path.join(self.tmp.name, "projects", "p")
        os.makedirs(proj, exist_ok=True)
        for name, records in files.items():
            with open(os.path.join(proj, name), "w", encoding="utf-8") as fh:
                for rec in records:
                    fh.write(json.dumps(rec) + "\n")

    def by_group(self, rows):
        return {r["group"]: r for r in rows}

    def test_hit_goes_to_the_session_model_bucket(self):
        reset = self.now + timedelta(days=2)
        self.write_files({
            "a.jsonl": [usage_record(self.now - timedelta(hours=2), "qwen3-coder-plus"),
                        hit_record(self.now - timedelta(hours=1), reset)],
            "q.jsonl": [usage_record(self.now - timedelta(hours=1), "deepseek-v4-flash-0731")],
        })
        rows = self.by_group(engine.bucket_rows(self.acc, TWO_PLANS))
        self.assertEqual(rows["Alibaba Cloud"]["weekPct"], 100.0)
        self.assertIsNone(rows["Qwen Cloud"]["weekPct"])

    def test_hit_before_first_model_uses_next_model(self):
        reset = self.now + timedelta(days=2)
        self.write_files({"a.jsonl": [
            hit_record(self.now - timedelta(hours=2), reset),
            usage_record(self.now - timedelta(hours=1), "deepseek-v4-flash-0731"),
        ]})
        rows = self.by_group(engine.bucket_rows(self.acc, TWO_PLANS))
        self.assertEqual(rows["Qwen Cloud"]["weekPct"], 100.0)
        self.assertNotIn("Alibaba Cloud", rows)

    def test_orphan_hit_is_not_guessed_when_two_plans(self):
        """ไม่รู้ว่าของใคร + มีสองใบ = อย่าประกาศว่าใบไหนเต็ม"""
        reset = self.now + timedelta(days=2)
        self.write_files({"a.jsonl": [hit_record(self.now - timedelta(hours=1), reset)]})
        self.assertEqual(engine.bucket_rows(self.acc, TWO_PLANS), [])

    def test_anchor_without_profile_is_ignored_when_two_plans(self):
        self.write_files({"a.jsonl": [
            usage_record(self.now - timedelta(hours=1), "qwen3-coder-plus"),
            usage_record(self.now - timedelta(minutes=50), "deepseek-v4-flash-0731"),
        ]})
        rows = self.by_group(engine.bucket_rows(self.acc, TWO_PLANS, self.anchor()))
        self.assertIsNone(rows["Qwen Cloud"]["weekPct"])
        self.assertIsNone(rows["Alibaba Cloud"]["weekPct"])

    def test_anchor_with_profile_hits_only_that_bucket(self):
        self.write_files({"a.jsonl": [
            usage_record(self.now - timedelta(hours=1), "qwen3-coder-plus"),
            usage_record(self.now - timedelta(minutes=50), "deepseek-v4-flash-0731"),
        ]})
        anchor = dict(self.anchor(), profile="qwenc")
        rows = self.by_group(engine.bucket_rows(self.acc, TWO_PLANS, anchor))
        self.assertEqual(rows["Qwen Cloud"]["weekPct"], 4.8)
        self.assertIsNone(rows["Alibaba Cloud"]["weekPct"])

    # เทสต์ของคลาสแม่ใช้ TABLE ถังเดียว — ไม่ต้องรันซ้ำที่นี่
    test_exhausted_row_survives_without_traffic = None
    test_expired_hit_without_traffic_yields_nothing = None
    test_data_fetched_at_is_hit_time_not_scan_time = None
    test_dashboard_anchor_shows_as_lower_bound = None
    test_anchor_does_not_conjure_buckets = None
    test_expired_anchor_is_ignored = None
    test_active_hit_beats_anchor = None
    test_hit_applies_to_bucket_with_traffic = None


class MonthlyPlanTest(TwoTokenPlansTest):
    """แผน Alibaba Cloud นับรายเดือน — ไปอยู่ modelWindows ป้าย 1mo ไม่ปนกับ 5h/7d"""

    def month_anchor(self, used=0.03, reset_in_days=30):
        return {"albb": {"points": [{"usedPct": used, "at": self.now - timedelta(hours=1)}],
                         "resetAt": self.now + timedelta(days=reset_in_days)}}

    def traffic(self):
        self.write_files({"a.jsonl": [
            usage_record(self.now - timedelta(minutes=30), "qwen3-coder-plus")]})

    def test_month_anchor_is_lower_bound_window(self):
        self.traffic()
        row = engine.bucket_rows(self.acc, TWO_PLANS, None, self.month_anchor())[0]
        self.assertIsNone(row["pct"])
        self.assertIsNone(row["weekPct"])
        [mw] = row["modelWindows"]
        self.assertEqual((mw["label"], mw["pct"], mw["confidence"]), ("1mo", 0.03, "lower_bound"))
        self.assertEqual(mw["resetAt"], iso_z(self.now + timedelta(days=30)))

    def test_month_anchor_only_hits_its_profile(self):
        self.write_files({"a.jsonl": [
            usage_record(self.now - timedelta(minutes=30), "deepseek-v4-flash-0731")]})
        row = engine.bucket_rows(self.acc, TWO_PLANS, None, self.month_anchor())[0]
        self.assertEqual(row["modelWindows"], [])

    def test_expired_month_anchor_is_ignored(self):
        self.traffic()
        row = engine.bucket_rows(self.acc, TWO_PLANS, None, self.month_anchor(reset_in_days=-1))[0]
        self.assertEqual(row["modelWindows"], [])

    def test_month_429_beats_anchor(self):
        reset = self.now + timedelta(days=10)
        self.write_files({"a.jsonl": [
            usage_record(self.now - timedelta(hours=1), "qwen3-coder-plus"),
            hit_record(self.now - timedelta(minutes=10), reset, window="1-month")]})
        row = engine.bucket_rows(self.acc, TWO_PLANS, None, self.month_anchor())[0]
        [mw] = row["modelWindows"]
        self.assertEqual((mw["pct"], mw["confidence"]), (100.0, "valid"))
        self.assertEqual(row["pctSource"], "official")

    def test_parse_plan_anchors_skips_garbage(self):
        parsed = engine.parse_plan_anchors({
            "albb": {"usedPct": 1.5, "at": "2026-09-27T13:35:18Z", "resetAt": "2026-10-27T16:00:00Z"},
            "bad": {"usedPct": "x"}, "worse": 3})
        self.assertEqual(list(parsed), ["albb"])
        self.assertEqual(len(parsed["albb"]["points"]), 1, "แบบเก่าก้อนเดียว = จุดเดียว")
        self.assertEqual(engine.parse_plan_anchors(None), {})

    def test_points_are_sorted(self):
        parsed = engine.parse_plan_anchors({"albb": {"resetAt": "2026-10-27T16:00:00Z", "points": [
            {"usedPct": 1.31, "at": "2026-09-28T07:23:00Z"},
            {"usedPct": 0.03, "at": "2026-09-27T13:35:18Z"}, "junk"]}})
        self.assertEqual([p["usedPct"] for p in parsed["albb"]["points"]], [0.03, 1.31])

    def two_points(self):
        t1, t2 = self.now - timedelta(hours=10), self.now - timedelta(hours=2)
        return t1, t2, {"albb": {"resetAt": self.now + timedelta(days=20), "points": [
            {"usedPct": 1.0, "at": t1}, {"usedPct": 3.0, "at": t2}]}}

    def test_two_points_give_estimate_from_tokens_since_last(self):
        """2% ต่อ 1000 token ระหว่างจุด → อีก 500 token หลังจุดล่าสุด = 3% + 1%"""
        self.traffic()
        t1, t2, anchors = self.two_points()
        series = {"albb": [(t1 + timedelta(hours=1), 1000), (t2 + timedelta(minutes=5), 500)]}
        row = engine.bucket_rows(self.acc, TWO_PLANS, None, anchors, series)[0]
        [mw] = row["modelWindows"]
        self.assertEqual((mw["pct"], mw["confidence"]), (4.0, "estimated"))
        self.assertEqual(row["dataFetchedAt"], iso_z(t2))

    def test_no_tokens_between_points_falls_back_to_lower_bound(self):
        self.traffic()
        _, _, anchors = self.two_points()
        row = engine.bucket_rows(self.acc, TWO_PLANS, None, anchors, {"albb": []})[0]
        [mw] = row["modelWindows"]
        self.assertEqual((mw["pct"], mw["confidence"]), (3.0, "lower_bound"))

    def test_estimate_is_capped_at_100(self):
        t1, t2, anchors = self.two_points()
        series = [(t1 + timedelta(hours=1), 10), (t2 + timedelta(minutes=5), 10_000)]
        self.assertEqual(engine.estimate_plan_pct(anchors["albb"]["points"], series, self.now), 100.0)

    test_hit_goes_to_the_session_model_bucket = None
    test_hit_before_first_model_uses_next_model = None
    test_orphan_hit_is_not_guessed_when_two_plans = None
    test_anchor_without_profile_is_ignored_when_two_plans = None
    test_anchor_with_profile_hits_only_that_bucket = None

if __name__ == "__main__":
    unittest.main()
