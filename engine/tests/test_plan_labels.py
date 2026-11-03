"""ชื่อแผนบน badge — แปลจาก identifier ดิบของผู้ให้บริการเป็นชื่อที่ผู้ใช้รู้จัก

Claude: Anthropic เปลี่ยนชื่อแผน 2026-10-30 (Max 20x → Ultra, Max 5x → Max)
แต่ tier ใน oauthAccount ยังเป็นชื่อเก่า จึงต้องแปลฝั่งแสดงผล

Codex: แผน prolite ไม่มีหน้าต่าง 5 ชม. แต่ server ยังส่ง planType "pro"
จึงแยก Pro Lite จากรูปหน้าต่าง ไม่ใช่ชื่อที่ server เรียก
"""

import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_plan_labels", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def codex_cs(*minutes):
    """cs อย่างย่อ — หน้าต่างตามความยาวที่ให้ (นาที) ช่องละใบ"""
    slots = ("primary", "secondary")
    return {"windows": {slots[i]: {"win": {"window_minutes": m}, "ts": None, "seen": []}
                        for i, m in enumerate(minutes)}}


class ClaudePlanLabelTest(unittest.TestCase):
    def test_max_20x_is_now_ultra(self):
        self.assertEqual(engine.plan_label("claude_max", "default_claude_max_20x"),
                         "Ultra")

    def test_max_5x_is_now_just_max(self):
        self.assertEqual(engine.plan_label("claude_max", "default_claude_max_5x"),
                         "Max")

    def test_future_ultra_identifier(self):
        # วันที่ server เปลี่ยน identifier ตามชื่อใหม่ ต้องไม่หลุดไปเป็นชื่อดิบ
        self.assertEqual(engine.plan_label("claude_ultra", "default_claude_ultra"),
                         "Ultra")

    def test_team_codename_still_falls_back_to_org_type(self):
        self.assertEqual(engine.plan_label("claude_team", "default_raven"), "Team")

    def test_pro_and_free_unchanged(self):
        self.assertEqual(engine.plan_label("claude_pro", None), "Pro")
        self.assertEqual(engine.plan_label("claude_free", None), "Free")

    def test_nothing_known_is_none(self):
        self.assertIsNone(engine.plan_label(None, None))
        self.assertIsNone(engine.plan_label("", ""))


class MusePlanLabelTest(unittest.TestCase):
    def test_known_tiers(self):
        self.assertEqual(engine.muse_plan_label("power"), "Power")
        self.assertEqual(engine.muse_plan_label(" High "), "High")
        self.assertEqual(engine.muse_plan_label("everyday"), "Everyday")

    def test_missing_name_is_none_not_everyday(self):
        self.assertIsNone(engine.muse_plan_label(None))
        self.assertIsNone(engine.muse_plan_label(""))
        self.assertIsNone(engine.muse_plan_label(3))


class CodexPlanLabelTest(unittest.TestCase):
    def test_pro_with_only_a_weekly_window_is_pro_lite(self):
        # เคสจริง 2026-11-03: planType "pro" แต่ primary คือสัปดาห์ secondary null
        self.assertEqual(engine.codex_plan_label("pro", codex_cs(10080)), "Pro Lite")

    def test_pro_with_a_short_window_is_pro(self):
        self.assertEqual(engine.codex_plan_label("pro", codex_cs(300, 10080)), "Pro")

    def test_pro_without_windows_keeps_the_servers_word(self):
        self.assertEqual(engine.codex_plan_label("pro", {"windows": {}}), "Pro")
        self.assertEqual(engine.codex_plan_label("pro", None), "Pro")

    def test_literal_prolite_spellings(self):
        for raw in ("prolite", "pro_lite", "Pro-Lite"):
            self.assertEqual(engine.codex_plan_label(raw, codex_cs(300)), "Pro Lite")

    def test_other_tiers(self):
        self.assertEqual(engine.codex_plan_label("plus", None), "Plus")
        self.assertEqual(engine.codex_plan_label("team", None), "Team")
        self.assertEqual(engine.codex_plan_label("free", None), "Free")

    def test_missing_plan_type_is_none(self):
        self.assertIsNone(engine.codex_plan_label(None, codex_cs(300)))
        self.assertIsNone(engine.codex_plan_label("", codex_cs(300)))
        self.assertIsNone(engine.codex_plan_label(7, codex_cs(300)))

    def test_live_plan_prefers_the_codex_bucket(self):
        live = {"result": {"rateLimits": {"planType": "plus"},
                           "rateLimitsByLimitId": {"codex": {"planType": "pro"}}}}
        self.assertEqual(engine.codex_live_plan(live), "pro")
        self.assertEqual(engine.codex_live_plan(
            {"result": {"rateLimits": {"planType": "plus"}}}), "plus")
        self.assertIsNone(engine.codex_live_plan(None))
        self.assertIsNone(engine.codex_live_plan({"result": {}}))


if __name__ == "__main__":
    unittest.main()
