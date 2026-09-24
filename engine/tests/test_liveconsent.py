"""live usage ต้องเป็น opt-in — แอปที่แจกออกไปห้ามแตะ Keychain ของใครก่อนได้รับอนุญาต

`liveusage.py` อ่าน OAuth token ของ Claude Code จาก Keychain ยิง api.anthropic.com
แล้วเขียน token ที่ rotate แล้วกลับลง Keychain item เดิม บนเครื่องเจ้าของโปรเจกต์
เรื่องนี้ผ่านการอนุมัติมาแล้ว แต่พอแจกผ่าน Homebrew มันจะไปทำแบบเดียวกันกับบัญชี
ของคนที่ไม่เคยถูกถาม และถ้าเขียนกลับพลาด refresh token ที่ถูก rotate จะหาย =
บัญชีหลุด ค่าเริ่มต้นจึงต้องเป็นปิด

ข้อยกเว้นเดียวคือคนที่ใช้อยู่ก่อนหน้านี้ — config ของเขาไม่มีคีย์นี้ ถือว่าเคย
อนุญาตไปแล้ว ห้ามปิดของเขาเงียบๆ
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_consent", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class ConfigDefaultTest(unittest.TestCase):
    def test_a_fresh_install_starts_with_live_usage_off(self):
        self.assertIs(engine.default_config()["liveUsage"], False)


class MigrationTest(unittest.TestCase):
    """คนที่ใช้อยู่แล้วต้องไม่สะดุด แต่คนที่ตั้งใจปิดต้องไม่ถูกเปิดกลับ"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")
        self.saved = engine.CFG_PATH
        engine.CFG_PATH = self.path

    def tearDown(self):
        engine.CFG_PATH = self.saved
        self.tmp.cleanup()

    def write(self, cfg):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_existing_config_without_the_key_keeps_live_usage_on(self):
        self.write({"claude": [], "codex": [], "manual": []})
        self.assertIs(engine.load_config()["liveUsage"], True)
        self.assertIs(self.read()["liveUsage"], True, "ต้องเขียนกลับ ไม่ใช่เดาใหม่ทุกรอบ")

    def test_an_explicit_false_is_never_flipped_back_on(self):
        self.write({"claude": [], "codex": [], "manual": [], "liveUsage": False})
        self.assertIs(engine.load_config()["liveUsage"], False)

    def test_an_explicit_true_stays_on(self):
        self.write({"claude": [], "codex": [], "manual": [], "liveUsage": True})
        self.assertIs(engine.load_config()["liveUsage"], True)


class GateTest(unittest.TestCase):
    """ปิดแล้วต้องไม่มีการเรียกอะไรที่แตะ Keychain หรือเน็ตเลย"""

    def setUp(self):
        self.calls = []
        self.saved = (engine._liveu.fetch_utilization,
                      engine._liveu.cached_live_utilization,
                      engine._util.read_utilization,
                      engine._clilive.live)
        engine._liveu.fetch_utilization = lambda d, **k: self.calls.append("fetch")
        engine._liveu.cached_live_utilization = lambda d, **k: self.calls.append("livecache")
        engine._util.read_utilization = lambda d: None
        # ห้ามสปอว์น CLI จริงในเทสต์ — ช้าและผลขึ้นกับบัญชีของเครื่องที่รัน
        engine._clilive.live = lambda d, **k: self.calls.append("cli")

    def tearDown(self):
        (engine._liveu.fetch_utilization,
         engine._liveu.cached_live_utilization,
         engine._util.read_utilization,
         engine._clilive.live) = self.saved

    def test_disabled_never_reaches_the_keychain_or_the_network(self):
        engine.account_utilization("/tmp/whatever", live_enabled=False)
        self.assertEqual(self.calls, [],
                         "ปิดอยู่แต่ยังเรียก live — นี่คือการแตะ credential โดยไม่ได้ขอ")

    def test_disabled_never_spawns_the_cli_either(self):
        """สปอว์น CLI ไม่ได้แตะ credential ของเรา แต่ก็ยังเป็นการออกเน็ตแทนผู้ใช้"""
        engine.account_limit_resets("/tmp/whatever", live_enabled=False)
        self.assertEqual(self.calls, [])

    def test_enabled_asks_the_cli_before_the_endpoint(self):
        """CLI ถือ auth ของมันเอง — ถามได้คำตอบก็ไม่ต้องแตะ Keychain เลย"""
        engine.account_utilization("/tmp/whatever", live_enabled=True)
        self.assertEqual(self.calls[0], "cli")

    def test_the_endpoint_is_still_there_when_the_cli_has_nothing(self):
        engine.account_utilization("/tmp/whatever", live_enabled=True)
        self.assertIn("fetch", self.calls)

    def test_local_claude_cache_is_still_read_when_disabled(self):
        """ปิด live ไม่ได้แปลว่าเลิกแสดง % — แคชของ Claude Code เองไม่ใช้ credential"""
        seen = []
        engine._util.read_utilization = lambda d: seen.append(d)
        engine.account_utilization("/tmp/whatever", live_enabled=False)
        self.assertEqual(seen, ["/tmp/whatever"])


class FlagTest(unittest.TestCase):
    """สวิตช์ในแอปส่งมาทาง argv ไม่ใช่การเขียน config.json

    เอนจินเขียน config.json เองอยู่แล้วตอนเจอบัญชีใหม่ ถ้าแอปเขียนไฟล์เดียวกัน
    ด้วย จะมีจังหวะที่ฝั่งหนึ่งทับอีกฝั่งจนหาย — กับสวิตช์ความยินยอม การหายแปลว่า
    มันเงียบๆ กลับไปแตะ Keychain ได้เอง
    """

    def test_flag_is_lifted_out_so_it_never_looks_like_a_snapshot_path(self):
        argv, override = engine.split_live_usage_flag(["--snapshot", "--live-usage=1"])
        self.assertEqual(argv, ["--snapshot"], "ไม่งั้น --live-usage=1 จะกลายเป็นชื่อไฟล์ปลายทาง")
        self.assertIs(override, True)

    def test_flag_can_turn_it_off(self):
        self.assertIs(engine.split_live_usage_flag(["--live-usage=0"])[1], False)

    def test_no_flag_means_no_opinion(self):
        argv, override = engine.split_live_usage_flag(["--snapshot", "/tmp/x.json"])
        self.assertEqual(argv, ["--snapshot", "/tmp/x.json"])
        self.assertIsNone(override)

    def test_the_flag_beats_the_config_file(self):
        self.assertIs(engine.effective_live_usage({"liveUsage": False}, True), True)
        self.assertIs(engine.effective_live_usage({"liveUsage": True}, False), False)

    def test_without_a_flag_the_config_decides(self):
        self.assertIs(engine.effective_live_usage({"liveUsage": True}, None), True)
        self.assertIs(engine.effective_live_usage({"liveUsage": False}, None), False)

    def test_a_config_with_no_opinion_at_all_stays_off(self):
        """กันพลาด — ถ้า migration ไม่ทำงาน ค่าที่ปลอดภัยกว่าคือปิด"""
        self.assertIs(engine.effective_live_usage({}, None), False)


if __name__ == "__main__":
    unittest.main()
