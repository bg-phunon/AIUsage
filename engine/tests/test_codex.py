"""Codex: rate_limits ที่ไม่มีหน้าต่าง ห้ามลบเลขที่รู้อยู่แล้ว

เคสจริง 2026-08-21: record ที่ 15:10:37Z บอก weekly 100% (รีเซ็ต 27 ส.ค.)
แล้ว 15:15:09Z มี record ของ limit_id "premium" ที่ primary/secondary เป็น
null ทั้งคู่ — โค้ดเดิมหยิบก้อนใหม่สุดโดยไม่ดูว่ามีหน้าต่างไหม เลขจึงหายจากจอ
ทั้งที่โควตายังเต็มและยังไม่ถึงเวลารีเซ็ต (6237 record มีแค่ 6 ก้อนที่ว่างแบบนี้)
"""

import builtins
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_codex", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

# อยู่ในอดีตเสมอ ไม่ว่าจะรันวันไหน — week_cut จึงไม่มีวันไปตัดไฟล์ที่เพิ่งเขียน
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def iso_z(dt):
    return dt.isoformat().replace("+00:00", "Z")


def window(pct, minutes, resets_at=None, resets_in=None):
    win = {"used_percent": pct, "window_minutes": minutes}
    if resets_at is not None:
        win["resets_at"] = resets_at.timestamp() if isinstance(resets_at, datetime) else resets_at
    if resets_in is not None:
        win["resets_in_seconds"] = resets_in
    return win


def limits(primary=None, secondary=None, limit_id="codex"):
    return {"limit_id": limit_id, "limit_name": None,
            "primary": primary, "secondary": secondary,
            "credits": {"has_credits": False, "unlimited": False, "balance": "0"},
            "individual_limit": None, "spend_control_reached": None,
            "plan_type": "plus", "rate_limit_reached_type": None}


def record(ts, rate_limits=None, tokens=0):
    """token_count หนึ่งบรรทัดตามรูปจริงของ rollout log"""
    return {"timestamp": iso_z(ts), "type": "event_msg",
            "payload": {"type": "token_count",
                        "info": {"last_token_usage": {"total_tokens": tokens},
                                 "total_token_usage": {"total_tokens": tokens},
                                 "model_context_window": 258400},
                        "rate_limits": rate_limits}}


class CodexDir:
    """โฟลเดอร์ .codex ชั่วคราวที่มี rollout หนึ่งไฟล์"""

    def __init__(self, records):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "sessions", "2026", "08", "21")
        os.makedirs(path)
        with open(os.path.join(path, "rollout-test.jsonl"), "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

    def __enter__(self):
        return self.tmp.name

    def __exit__(self, *exc):
        self.tmp.cleanup()


class _CountingFile:
    """ห่อไฟล์จริงไว้เพื่อนับไบต์ที่ถูกอ่าน — ที่เหลือส่งต่อให้ของเดิมหมด"""

    def __init__(self, fh, counter):
        self._fh = fh
        self._counter = counter

    def read(self, *a, **kw):
        chunk = self._fh.read(*a, **kw)
        self._counter.total += len(chunk)
        return chunk

    def __getattr__(self, name):
        return getattr(self._fh, name)

    def __iter__(self):
        # โค้ดเดิมไล่บรรทัดด้วย for line in fh ไม่ได้เรียก read() เลย
        # ถ้าไม่นับตรงนี้ด้วย เทสต์จะผ่านทั้งที่ยังสแกนทั้งไฟล์อยู่
        for line in self._fh:
            self._counter.total += len(
                line if isinstance(line, bytes) else line.encode("utf-8", "ignore"))
            yield line

    def __enter__(self):
        self._fh.__enter__()
        return self

    def __exit__(self, *exc):
        return self._fh.__exit__(*exc)


class _CountingOpen:
    """นับไบต์ที่อ่านจริงในบล็อก — หลักฐานว่าไม่ได้สแกนไฟล์ทั้งก้อน"""

    def __init__(self):
        self.total = 0

    def __enter__(self):
        self._saved = builtins.open
        builtins.open = lambda *a, **kw: _CountingFile(self._saved(*a, **kw), self)
        return self

    def __exit__(self, *exc):
        builtins.open = self._saved
        return False


class StatsRetentionTest(unittest.TestCase):
    """หน้าต่างที่รู้แล้วต้องรอด — ก้อนที่ไม่มีหน้าต่างไม่ใช่คำประกาศว่า "ไม่มีลิมิต" """

    def setUp(self):
        self.saved_now = engine.now_utc
        engine.now_utc = lambda: NOW

    def tearDown(self):
        engine.now_utc = self.saved_now

    def stats(self, records):
        with CodexDir(records) as path:
            return engine.codex_stats(path)

    def test_record_without_windows_does_not_erase_known_percent(self):
        """limit_id อื่นที่ไม่มีหน้าต่างเลย โผล่มาทีหลัง — ของเดิมต้องไม่หาย"""
        cs = self.stats([
            record(NOW - timedelta(days=2), limits(
                primary=window(100.0, 10080, resets_at=NOW + timedelta(days=4)))),
            record(NOW - timedelta(days=1), limits(limit_id="premium")),
        ])
        kept = cs["windows"]["primary"]["win"]
        self.assertEqual(kept["used_percent"], 100.0,
                         "ก้อนว่างของ limit_id อื่นไปลบหน้าต่างที่รู้ค่าแล้ว")

    def test_newer_window_with_a_value_still_wins(self):
        """ของใหม่ที่มีค่าจริงต้องทับของเก่าตามปกติ — ไม่ใช่ค้างอันแรกที่เจอ"""
        cs = self.stats([
            record(NOW - timedelta(days=2), limits(primary=window(65.0, 10080))),
            record(NOW - timedelta(days=1), limits(primary=window(100.0, 10080))),
        ])
        self.assertEqual(cs["windows"]["primary"]["win"]["used_percent"], 100.0)

    def test_missing_secondary_does_not_erase_a_known_secondary(self):
        """Codex เลิกส่ง secondary ตอนไหนก็ได้ — เก็บของเดิมไว้รายหน้าต่าง"""
        cs = self.stats([
            record(NOW - timedelta(days=2), limits(primary=window(30.0, 300),
                                                   secondary=window(5.0, 10080))),
            record(NOW - timedelta(days=1), limits(primary=window(40.0, 300))),
        ])
        self.assertEqual(cs["windows"]["primary"]["win"]["used_percent"], 40.0)
        self.assertEqual(cs["windows"]["secondary"]["win"]["used_percent"], 5.0)

    def test_last_activity_comes_from_records_that_used_tokens(self):
        """เวลาที่ใช้งานล่าสุด — ไว้ตัดสินว่าหน้าต่างที่หมุนไปแล้วเป็นศูนย์จริงไหม"""
        cs = self.stats([
            record(NOW - timedelta(days=3), limits(primary=window(10.0, 10080)), tokens=500),
            record(NOW - timedelta(days=1), limits(primary=window(20.0, 10080)), tokens=0),
        ])
        self.assertEqual(cs["lastActivity"], NOW - timedelta(days=3))


class WindowFromLimitTest(unittest.TestCase):
    """เวลารีเซ็ตมาได้สามแบบ — ต้องอ่านออกทุกแบบ ไม่งั้นเลขไม่มีวันหมดอายุ"""

    TS = NOW - timedelta(hours=2)

    def test_absolute_resets_at_is_the_reset_time(self):
        """รูปแบบปัจจุบันของ Codex คือ epoch สัมบูรณ์ ไม่ใช่วินาทีที่เหลือ"""
        end = NOW + timedelta(days=4)
        win = engine.window_from_limit(window(100.0, 10080, resets_at=end), self.TS)
        self.assertEqual(win["end"], end)
        self.assertEqual(win["pct"], 100.0)

    def test_relative_resets_in_seconds_still_works(self):
        """รูปเก่ายังมีอยู่ในบางไฟล์ — นับจากเวลาของ record"""
        win = engine.window_from_limit(window(30.0, 300, resets_in=3600), self.TS)
        self.assertEqual(win["end"], self.TS + timedelta(seconds=3600))

    def test_without_reset_info_the_window_length_is_the_upper_bound(self):
        """ไม่มีเวลารีเซ็ต — หน้าต่างยาว W นาทีที่เห็นตอน ts วิ่งต่อได้ไม่เกิน ts+W"""
        win = engine.window_from_limit(window(30.0, 300), self.TS)
        self.assertEqual(win["end"], self.TS + timedelta(minutes=300))

    def test_window_length_is_reported_for_row_routing(self):
        self.assertEqual(engine.window_from_limit(window(1.0, 10080), self.TS)["minutes"], 10080)

    def test_no_percent_means_no_window(self):
        self.assertIsNone(engine.window_from_limit({"window_minutes": 300}, self.TS))
        self.assertIsNone(engine.window_from_limit(None, self.TS))


class CodexFieldsTest(unittest.TestCase):
    """จัดแถวตามความยาวหน้าต่างจริง ไม่ใช่ตำแหน่ง primary/secondary

    Codex ย้าย weekly มาไว้ที่ primary แล้ว (secondary หายไป) — ถ้ายังยึดตำแหน่ง
    เลขสัปดาห์จะไปโผล่ในแถว "5h" ของ popover ซึ่งเป็นคนละเรื่องกัน
    """

    @staticmethod
    def stats(windows, last_activity=None, tokens=0):
        return {"tokens": tokens, "windows": windows, "lastActivity": last_activity}

    def test_weekly_window_lands_in_the_week_row(self):
        cs = self.stats({"primary": {"win": window(100.0, 10080,
                                                   resets_at=NOW + timedelta(days=4)),
                                     "ts": NOW - timedelta(hours=2)}})
        out = engine.codex_fields(cs, NOW)
        self.assertEqual(out["weekPct"], 100.0, "เลขสัปดาห์ต้องอยู่แถวสัปดาห์")
        self.assertIsNone(out["pct"], "แถว 5h ไม่มีข้อมูล — ห้ามยืมเลขสัปดาห์มาโชว์")
        self.assertEqual(out["resetAt"], NOW + timedelta(days=4))

    def test_short_window_lands_in_the_five_hour_row(self):
        cs = self.stats({"primary": {"win": window(30.0, 300,
                                                   resets_at=NOW + timedelta(hours=2)),
                                     "ts": NOW - timedelta(hours=1)},
                         "secondary": {"win": window(5.0, 10080,
                                                     resets_at=NOW + timedelta(days=3)),
                                       "ts": NOW - timedelta(hours=1)}})
        out = engine.codex_fields(cs, NOW)
        self.assertEqual(out["pct"], 30.0)
        self.assertEqual(out["weekPct"], 5.0)
        self.assertEqual(out["resetAt"], NOW + timedelta(hours=2),
                         "เวลารีเซ็ตเกาะแถวที่มีเลขจริง")

    def test_running_window_is_reported_as_valid(self):
        cs = self.stats({"primary": {"win": window(100.0, 10080,
                                                   resets_at=NOW + timedelta(days=4)),
                                     "ts": NOW - timedelta(hours=2)}})
        self.assertEqual(engine.codex_fields(cs, NOW)["weekConfidence"], "valid")

    def test_rolled_over_window_with_no_use_since_is_a_real_zero(self):
        """หน้าต่างหมุนไปแล้วและไม่มีใครใช้ต่อ = ศูนย์จริง ไม่ใช่ค้างเลขเก่า"""
        cs = self.stats({"primary": {"win": window(100.0, 10080,
                                                   resets_at=NOW - timedelta(hours=1)),
                                     "ts": NOW - timedelta(days=2)}},
                        last_activity=NOW - timedelta(days=2))
        out = engine.codex_fields(cs, NOW)
        self.assertEqual(out["weekPct"], 0.0)
        self.assertEqual(out["weekConfidence"], "zero")

    def test_rolled_over_window_with_use_since_is_unknown(self):
        """ใช้ต่อหลังรีเซ็ตแต่ไม่มีตัวเลขใหม่ — ตอบไม่ได้ ห้ามเดาเป็น 0 หรือ 100"""
        cs = self.stats({"primary": {"win": window(100.0, 10080,
                                                   resets_at=NOW - timedelta(hours=2)),
                                     "ts": NOW - timedelta(days=2)}},
                        last_activity=NOW - timedelta(minutes=30))
        out = engine.codex_fields(cs, NOW)
        self.assertIsNone(out["weekPct"])
        self.assertEqual(out["weekConfidence"], "unsure")

    def test_no_windows_at_all_reports_nothing(self):
        out = engine.codex_fields(self.stats({}), NOW)
        self.assertIsNone(out["pct"])
        self.assertIsNone(out["weekPct"])
        self.assertIsNone(out["resetAt"])
        self.assertIsNone(out["weekResetAt"])

    def test_week_row_keeps_its_own_reset_time(self):
        """สองแถวมีเวลารีเซ็ตคนละอัน — ช่องเดียวใส่ได้แค่ของ 5h แถว 7d จึงว่าง

        เคสจริง 2026-08-31: log มี resets_at ของสัปดาห์อยู่ (6 ก.ย.) แต่ codex_fields
        ทิ้งไป เพราะ resetAt ถูกจองให้แถว 5h ที่มีเลขแล้ว
        """
        five_h = NOW + timedelta(hours=5)
        seven_d = NOW + timedelta(days=6)
        cs = self.stats({"primary": {"win": window(0.0, 300, resets_at=five_h),
                                     "ts": NOW - timedelta(minutes=1)},
                         "secondary": {"win": window(14.0, 10080, resets_at=seven_d),
                                       "ts": NOW - timedelta(minutes=1)}})
        out = engine.codex_fields(cs, NOW)
        self.assertEqual(out["resetAt"], five_h)
        self.assertEqual(out["weekResetAt"], seven_d,
                         "เวลารีเซ็ตของสัปดาห์มีอยู่ใน log แต่หายไปก่อนถึงจอ")

    def test_week_reset_follows_the_same_confidence_rules_as_its_percent(self):
        """หน้าต่างที่หมุนไปแล้วยังไม่มีเลขใหม่ — เวลารีเซ็ตเก่าก็ห้ามค้างเหมือนกัน"""
        cs = self.stats({"primary": {"win": window(100.0, 10080,
                                                   resets_at=NOW - timedelta(hours=2)),
                                     "ts": NOW - timedelta(days=2)}},
                        last_activity=NOW - timedelta(minutes=30))
        out = engine.codex_fields(cs, NOW)
        self.assertIsNone(out["weekPct"])
        self.assertEqual(out["weekResetAt"], NOW - timedelta(hours=2),
                         "ยังบอกได้ว่าหน้าต่างเดิมจบเมื่อไหร่ — UI เป็นคนตัดเวลาที่ผ่านไปแล้วทิ้ง")


class RegressionOfTheDisappearingNumberTest(unittest.TestCase):
    """เล่นซ้ำลำดับจริงของ 2026-08-21 ทั้งเส้น — จาก log ถึงฟิลด์ที่ UI อ่าน"""

    def setUp(self):
        self.saved_now = engine.now_utc
        engine.now_utc = lambda: NOW

    def tearDown(self):
        engine.now_utc = self.saved_now

    def test_weekly_hundred_percent_survives_the_premium_record(self):
        reset = NOW + timedelta(days=3, hours=16)
        with CodexDir([
            record(NOW - timedelta(days=2, minutes=5),
                   limits(primary=window(100.0, 10080, resets_at=reset)), tokens=1200),
            record(NOW - timedelta(days=2), limits(limit_id="premium")),
        ]) as path:
            out = engine.codex_fields(engine.codex_stats(path), NOW)
        self.assertEqual(out["weekPct"], 100.0,
                         "โควตาเต็มแล้วเลขหายจากจอ ทั้งที่ยังไม่ถึงเวลารีเซ็ต")
        self.assertEqual(out["weekConfidence"], "valid")
        self.assertEqual(out["resetAt"], reset)


class ReverseLineReaderTest(unittest.TestCase):
    """อ่านบรรทัดจากท้ายไฟล์ — ต้องได้บรรทัดเดิมครบ แค่กลับลำดับ"""

    def lines(self, text, chunk_size):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return list(engine.iter_lines_reverse(path, chunk_size=chunk_size))

    def test_yields_lines_newest_first(self):
        self.assertEqual(self.lines("a\nb\nc\n", 1 << 20), ["c", "b", "a"])

    def test_last_line_without_newline_is_not_dropped(self):
        """rollout ที่กำลังถูกเขียนอยู่มักไม่มี \\n ปิดท้าย — บรรทัดสดสุดอยู่ตรงนั้น"""
        self.assertEqual(self.lines("a\nb\nc", 1 << 20), ["c", "b", "a"])

    def test_lines_split_across_chunk_boundaries_stay_whole(self):
        """ชิ้นแรกของแต่ละ chunk ถูกตัดกลางบรรทัด ต้องต่อกับ chunk ก่อนหน้า"""
        text = "".join("line-%04d\n" % i for i in range(500))
        self.assertEqual(self.lines(text, 7),
                         ["line-%04d" % i for i in reversed(range(500))])

    def test_multibyte_characters_split_across_chunks_survive(self):
        """ตัวอักษรไทยกินหลายไบต์ — ห้ามตัดกลางตัวแล้วได้ขยะ"""
        text = "".join("บรรทัด-%03d\n" % i for i in range(200))
        self.assertEqual(self.lines(text, 5),
                         ["บรรทัด-%03d" % i for i in reversed(range(200))])

    def test_empty_file_yields_nothing(self):
        self.assertEqual(self.lines("", 1 << 20), [])

    def test_blank_lines_are_skipped(self):
        self.assertEqual(self.lines("a\n\n\nb\n", 1 << 20), ["b", "a"])


class ReadBudgetTest(unittest.TestCase):
    """ไฟล์ session ที่เปิดค้างไว้เป็นเดือนโตถึงระดับกิกะไบต์ — ห้ามสแกนทั้งก้อน

    เคสจริง 2026-09-10: rollout ของ session วันที่ 15 ส.ค. ยังถูกเขียนต่อจนโต
    2.4 GB เอนจินอ่านทั้งไฟล์ทุก 60 วินาที ปลายทางคือชน timeout 45 วินาทีของแอป
    แล้วแถบ Codex หายไปทั้งแถว rollout เรียงตามเวลาอยู่แล้ว พอไล่จากท้ายมาเจอ
    record ที่เก่ากว่าหน้าต่างสัปดาห์ก็หยุดได้ทันที ที่เหลือข้างหน้าเก่ากว่านั้นหมด
    """

    def setUp(self):
        self.saved_now = engine.now_utc
        engine.now_utc = lambda: NOW

    def tearDown(self):
        engine.now_utc = self.saved_now

    @staticmethod
    def _bulk(count, age_days):
        """record ถ่วงน้ำหนักให้ไฟล์ใหญ่พอที่ chunk เดียวจะอ่านไม่หมด"""
        return [record(NOW - timedelta(days=age_days, minutes=i),
                       limits(primary=window(1.0, 10080)), tokens=7)
                for i in range(count)]

    def test_records_older_than_the_week_are_never_read(self):
        old = self._bulk(12000, age_days=30)
        fresh = [record(NOW - timedelta(days=1),
                        limits(primary=window(42.0, 10080,
                                              resets_at=NOW + timedelta(days=3))),
                        tokens=900)]
        with CodexDir(old + fresh) as path:
            target = os.path.join(path, "sessions", "2026", "08", "21", "rollout-test.jsonl")
            size = os.path.getsize(target)
            read = _CountingOpen()
            with read:
                cs = engine.codex_stats(path)

        self.assertGreater(size, 4 << 20, "ไฟล์ทดสอบเล็กเกินกว่าจะพิสูจน์อะไรได้")
        self.assertLess(read.total, size // 2,
                        "ยังอ่านทั้งไฟล์อยู่ — ไฟล์ระดับกิกะไบต์จะไปชน timeout ของแอป")
        self.assertEqual(cs["windows"]["primary"]["win"]["used_percent"], 42.0)

    def test_tokens_outside_the_week_do_not_leak_into_the_total(self):
        """หยุดที่ขอบสัปดาห์แล้วยอด token ต้องเป็นของในหน้าต่างล้วน"""
        with CodexDir(self._bulk(20, age_days=30)
                      + [record(NOW - timedelta(days=1), limits(), tokens=900)]) as path:
            cs = engine.codex_stats(path)
        self.assertEqual(cs["tokens"], 900)
        self.assertEqual(cs["lastActivity"], NOW - timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
