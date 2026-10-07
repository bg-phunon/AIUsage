"""Xiaomi MiMo Token Plan — % รายเดือนจากสูตร credit ที่ MiMo ประกาศเอง

ต่างจาก Alibaba ที่ไม่ประกาศสูตร: MiMo บอกอัตรา credit ต่อ token แยกตามโมเดล
และชนิด token (cache hit / cache miss / output) พร้อมยอด credit ต่อแผน และตัวคูณ
0.8 ช่วงกลางคืน 00:00–08:00 เวลาปักกิ่ง (UTC 16:00–24:00)
ที่มา: https://mimo.mi.com/docs/en-US/price/token-plan (ตรวจ 2026-10-07)
"""

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import mimo  # noqa: E402
from aiusage.buckets import Bucket, _name_for_host  # noqa: E402

DAY = datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc)      # 14:00 ปักกิ่ง
NIGHT = datetime(2026, 10, 7, 17, 0, tzinfo=timezone.utc)   # 01:00 ปักกิ่ง


class HostTest(unittest.TestCase):
    def test_token_plan_host_is_a_plan(self):
        self.assertTrue(mimo.is_plan_host("token-plan-cn.xiaomimimo.com"))
        self.assertTrue(mimo.is_plan_host("token-plan-sgp.xiaomimimo.com"))

    def test_pay_as_you_go_is_not_a_plan(self):
        self.assertFalse(mimo.is_plan_host("api.xiaomimimo.com"))
        self.assertFalse(mimo.is_plan_host("dashscope.aliyuncs.com"))
        self.assertFalse(mimo.is_plan_host(""))

    def test_bucket_gets_a_readable_name(self):
        self.assertEqual(_name_for_host("token-plan-cn.xiaomimimo.com", "x"), "Xiaomi MiMo")


class CreditsTest(unittest.TestCase):
    def test_pro_rates_per_token_type(self):
        usage = {"input_tokens": 10, "cache_read_input_tokens": 100, "output_tokens": 1}
        # 10×300 + 100×2.5 + 1×600
        self.assertEqual(mimo.credits("mimo-v2.6-pro", usage, DAY), 3850)

    def test_cache_write_counts_as_cache_miss(self):
        usage = {"cache_creation_input_tokens": 10}
        self.assertEqual(mimo.credits("mimo-v2.6-pro", usage, DAY), 3000)

    def test_flash_is_cheaper(self):
        usage = {"input_tokens": 1, "cache_read_input_tokens": 1, "output_tokens": 1}
        self.assertEqual(mimo.credits("mimo-v2.6-flash", usage, DAY), 302)

    def test_night_is_point_eight(self):
        usage = {"output_tokens": 10}
        self.assertEqual(mimo.credits("mimo-v2.6-pro", usage, NIGHT), 4800)

    def test_night_window_edges(self):
        u = {"output_tokens": 1}
        at = lambda h, m=0: datetime(2026, 10, 7, h, m, tzinfo=timezone.utc)
        self.assertEqual(mimo.credits("mimo-v2.5", u, at(15, 59)), 200)
        self.assertEqual(mimo.credits("mimo-v2.5", u, at(16, 0)), 160)
        self.assertEqual(mimo.credits("mimo-v2.5", u, at(23, 59)), 160)
        self.assertEqual(mimo.credits("mimo-v2.5", u, at(0, 0)), 200)

    def test_model_name_variants(self):
        u = {"output_tokens": 1}
        self.assertEqual(mimo.credits("MiMo-V2.6-Pro[1m]", u, DAY), 600)
        self.assertEqual(mimo.credits(" mimo-v2.5-pro ", u, DAY), 600)

    def test_unknown_model_is_none_not_zero(self):
        self.assertIsNone(mimo.credits("mimo-v9-ultra", {"output_tokens": 1}, DAY))


class PlanConfigTest(unittest.TestCase):
    NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

    def test_reads_plan_and_cycle(self):
        p = mimo.parse_plans({"mimo": {"plan": "Pro", "resetAt": "2026-10-20T00:00:00Z"}},
                             self.NOW)
        self.assertEqual(p["mimo"]["budget"], 38_000_000_000)
        self.assertEqual(p["mimo"]["resetAt"], datetime(2026, 10, 20, tzinfo=timezone.utc))
        self.assertEqual(p["mimo"]["start"], datetime(2026, 9, 20, tzinfo=timezone.utc))

    def test_past_reset_rolls_forward_by_months(self):
        """แผนต่ออายุเอง — วันรีเซ็ตที่ผ่านไปแล้วต้องเลื่อนไปรอบถัดไป ไม่ใช่หายไป"""
        p = mimo.parse_plans({"mimo": {"plan": "lite", "resetAt": "2026-08-31T00:00:00Z"}},
                             self.NOW)
        self.assertEqual(p["mimo"]["resetAt"], datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.assertEqual(p["mimo"]["start"], datetime(2026, 9, 30, tzinfo=timezone.utc),
                         "เดือนที่สั้นกว่าต้องหนีบวันไว้ที่วันสุดท้ายของเดือน")

    def test_far_future_reset_rolls_back(self):
        p = mimo.parse_plans({"m": {"plan": "pro", "resetAt": "2027-01-20T00:00:00Z"}},
                             self.NOW)
        self.assertEqual(p["m"]["resetAt"], datetime(2026, 10, 20, tzinfo=timezone.utc))

    def test_all_tiers(self):
        for name, budget in (("lite", 4.1e9), ("standard", 11e9), ("pro", 38e9), ("max", 82e9)):
            p = mimo.parse_plans({"k": {"plan": name, "resetAt": "2026-11-01T00:00:00Z"}},
                                 self.NOW)
            self.assertEqual(p["k"]["budget"], budget)

    def test_garbage_is_skipped(self):
        raw = {"a": {"plan": "gold", "resetAt": "2026-11-01T00:00:00Z"},
               "b": {"plan": "pro"}, "c": None, "d": {"plan": "pro", "resetAt": "x"}}
        self.assertEqual(mimo.parse_plans(raw, self.NOW), {})
        self.assertEqual(mimo.parse_plans(None, self.NOW), {})


class WindowTest(unittest.TestCase):
    PLAN = {"budget": 4_100_000_000,
            "start": datetime(2026, 10, 1, tzinfo=timezone.utc),
            "resetAt": datetime(2026, 11, 1, tzinfo=timezone.utc)}

    def test_pct_from_credits(self):
        w = mimo.month_window(self.PLAN, credits_used=410_000_000, unknown_calls=0)
        self.assertEqual(w["label"], "1mo")
        self.assertAlmostEqual(w["pct"], 10.0)
        self.assertEqual(w["confidence"], "estimated")
        self.assertEqual(w["resetAt"], "2026-11-01T00:00:00Z")

    def test_unknown_model_makes_it_a_floor(self):
        w = mimo.month_window(self.PLAN, credits_used=410_000_000, unknown_calls=3)
        self.assertEqual(w["confidence"], "lower_bound")

    def test_capped_at_100(self):
        w = mimo.month_window(self.PLAN, credits_used=9e9, unknown_calls=0)
        self.assertEqual(w["pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
