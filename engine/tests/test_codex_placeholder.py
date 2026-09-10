"""หน้าต่างที่ "เหลืออีก 5 ชั่วโมง" ทุกครั้งที่ถาม ไม่ใช่หน้าต่างจริง

เคสจริง 2026-09-10: หลังผู้ใช้เปลี่ยนแผน Codex ออก limit_id ใหม่ชื่อ
`codex_bengalfox` (GPT-5.3-Codex-Spark) แล้วรายงาน used_percent 0.0 ค้างอยู่
อย่างนั้น 129 record ตลอด 5 ชั่วโมงครึ่งที่ใช้ไป 17 ล้าน token

ตัวแยกที่ชัดที่สุดไม่ใช่ตัวเลข % แต่เป็นเวลารีเซ็ต:

    codex (ถังจริง)   resets_at คงที่  → เหลืออีก 290.5 → 289.6 → 288.9 นาที
    codex_bengalfox   resets_at ไหลขึ้น → เหลืออีก 299.8 → 299.4 → 299.8 นาที

ถังจริงนับถอยหลังจนหมดแล้วหมุนใหม่ ถังปลอมตอบว่า "อีก 5 ชั่วโมง" ตลอดกาล
การเอา 0% ของมันไปวาดเป็นแถบทึบคือการบอกผู้ใช้ว่า "ยังไม่ได้ใช้เลย" ทั้งที่
ความจริงคือ "ไม่มีใครนับให้"
"""

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_placeholder", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def observations(start, count, step_minutes, window_minutes, sliding):
    """(ts, end) หลายจุด — sliding=True คือ end ขยับตาม ts เสมอ"""
    out = []
    fixed_end = start + timedelta(minutes=window_minutes)
    for i in range(count):
        ts = start + timedelta(minutes=i * step_minutes)
        end = ts + timedelta(minutes=window_minutes) if sliding else fixed_end
        out.append((ts, end))
    return out


class NeverElapsesTest(unittest.TestCase):
    def test_a_window_that_counts_down_is_real(self):
        obs = observations(NOW, count=20, step_minutes=15, window_minutes=300, sliding=False)
        self.assertFalse(engine.window_never_elapses(obs, 300))

    def test_a_window_that_always_says_five_hours_left_is_not(self):
        obs = observations(NOW, count=20, step_minutes=15, window_minutes=300, sliding=True)
        self.assertTrue(engine.window_never_elapses(obs, 300))

    def test_too_short_an_observation_is_not_enough_to_judge(self):
        """เพิ่งเห็นถังนี้ไม่กี่นาที ยังบอกไม่ได้ว่ามันเดินหรือไม่เดิน — ห้ามด่วนสรุป"""
        obs = observations(NOW, count=3, step_minutes=2, window_minutes=300, sliding=True)
        self.assertFalse(engine.window_never_elapses(obs, 300))

    def test_one_observation_is_never_enough(self):
        self.assertFalse(engine.window_never_elapses([(NOW, NOW + timedelta(minutes=300))], 300))

    def test_without_a_window_length_there_is_nothing_to_compare(self):
        obs = observations(NOW, count=20, step_minutes=15, window_minutes=300, sliding=True)
        self.assertFalse(engine.window_never_elapses(obs, None))

    def test_a_window_seen_only_near_its_start_is_not_condemned(self):
        """หน้าต่างจริงที่เพิ่งหมุนใหม่ก็ 'เหลือเกือบเต็ม' เหมือนกัน — ต้องดูให้นานพอ"""
        obs = observations(NOW, count=6, step_minutes=2, window_minutes=300, sliding=False)
        self.assertFalse(engine.window_never_elapses(obs, 300))

    def test_a_weekly_placeholder_is_caught_without_waiting_days(self):
        """หน้าต่าง 7 วันที่ปลอม ต้องจับได้จากการเฝ้าดูไม่กี่ชั่วโมง

        กฎที่ขอเห็นครึ่งหนึ่งของหน้าต่างก่อนแปลว่าต้องรอ 3 วันครึ่ง ระหว่างนั้น
        แถบ 7d ก็โกหกว่า 0% ไปเรื่อยๆ
        """
        obs = observations(NOW, count=16, step_minutes=20, window_minutes=10080, sliding=True)
        self.assertTrue(engine.window_never_elapses(obs, 10080))

    def test_a_real_weekly_window_is_not_mistaken_for_one(self):
        obs = observations(NOW, count=16, step_minutes=20, window_minutes=10080, sliding=False)
        self.assertFalse(engine.window_never_elapses(obs, 10080))

    def test_a_window_that_rolled_over_mid_observation_is_still_real(self):
        """เห็นคร่อมจังหวะหมุน — เหลือเวลากระโดดกลับขึ้นไปเต็ม ห้ามอ่านว่าปลอม"""
        obs = []
        for i in range(40):
            ts = NOW + timedelta(minutes=i * 10)
            end = NOW + timedelta(minutes=300 if i * 10 < 300 else 600)
            obs.append((ts, end))
        self.assertFalse(engine.window_never_elapses(obs, 300))


class FieldsTest(unittest.TestCase):
    """ปลายทางที่ UI อ่าน — ต้องเป็น "ไม่รู้" ไม่ใช่ 0%"""

    @staticmethod
    def entry(win, ts, seen):
        return {"win": win, "ts": ts, "seen": seen}

    def sliding_stats(self):
        obs = observations(NOW - timedelta(hours=6), count=20, step_minutes=20,
                           window_minutes=300, sliding=True)
        last_ts, last_end = obs[-1]
        win = {"used_percent": 0.0, "window_minutes": 300,
               "resets_at": last_end.timestamp()}
        return {"tokens": 5_000_000, "lastActivity": last_ts,
                "windows": {"primary": self.entry(win, last_ts, obs)}}

    def test_a_placeholder_window_reports_no_percent_at_all(self):
        out = engine.codex_fields(self.sliding_stats(), NOW)
        self.assertIsNone(out["pct"], "0% ของช่องเปล่าอ่านเป็น 'ยังไม่ได้ใช้' ซึ่งไม่จริง")
        self.assertEqual(out["confidence"], "unsure")

    def test_a_placeholder_window_reports_no_reset_time_either(self):
        """นาฬิกาที่ไม่มีวันเดินถึงศูนย์ ไม่ควรขึ้นจอ"""
        self.assertIsNone(engine.codex_fields(self.sliding_stats(), NOW)["resetAt"])

    def test_a_real_window_is_untouched(self):
        obs = observations(NOW - timedelta(hours=4), count=20, step_minutes=12,
                           window_minutes=300, sliding=False)
        end = obs[0][0] + timedelta(minutes=300)
        win = {"used_percent": 62.0, "window_minutes": 300, "resets_at": end.timestamp()}
        cs = {"tokens": 1, "lastActivity": obs[-1][0],
              "windows": {"primary": self.entry(win, obs[-1][0], obs)}}
        out = engine.codex_fields(cs, NOW)
        self.assertEqual(out["pct"], 62.0)
        self.assertEqual(out["confidence"], "valid")

    def test_windows_without_history_still_work(self):
        """codex_fields ถูกเรียกจากเทสต์เก่าและจากโค้ดที่ไม่มี seen — ห้ามพัง"""
        win = {"used_percent": 30.0, "window_minutes": 300,
               "resets_at": (NOW + timedelta(hours=2)).timestamp()}
        cs = {"tokens": 0, "lastActivity": None,
              "windows": {"primary": {"win": win, "ts": NOW - timedelta(minutes=5)}}}
        self.assertEqual(engine.codex_fields(cs, NOW)["pct"], 30.0)


if __name__ == "__main__":
    unittest.main()
