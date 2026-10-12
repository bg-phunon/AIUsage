import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import buckets, ccs

CONFIG = """# CCS Unified Configuration
version: 14
accounts:
  work:
    created: "2026-05-12T05:01:13.871Z"
    context_mode: isolated
  mooz:
    last_used: null

profiles:
  glm:
    type: api
    settings: ~/.ccs/glm.settings.json
  far:
    type: api
    settings: "%s"   # ไฟล์อยู่นอก ccs dir
cliproxy:
  providers:
    - gemini
  variants: {}
"""


def write_settings(path, base_url, models, **extra):
    keys = ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL")
    env = {"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": "SECRET-MUST-NOT-LEAK"}
    env.update(dict(zip(keys, models)))
    env.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"env": env}, f)


class CcsDirTest(unittest.TestCase):
    def test_precedence_matches_ccs(self):
        self.assertEqual(ccs.ccs_dir({"CCS_DIR": "/a", "CCS_HOME": "/b"}), "/a")
        self.assertEqual(ccs.ccs_dir({"CCS_HOME": "/b"}), "/b/.ccs")
        self.assertEqual(ccs.ccs_dir({}), os.path.join(os.path.expanduser("~"), ".ccs"))


class CcsConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "ccs")
        self.elsewhere = os.path.join(self.tmp.name, "elsewhere.json")
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, "config.yaml"), "w", encoding="utf-8") as f:
            f.write(CONFIG % self.elsewhere)

    def tearDown(self):
        self.tmp.cleanup()

    def test_accounts_and_profiles(self):
        cfg = ccs.read_config(self.dir)
        self.assertEqual(cfg["accounts"], ["work", "mooz"])
        self.assertEqual(cfg["profiles"]["glm"],
                         os.path.join(os.path.expanduser("~"), ".ccs", "glm.settings.json"))
        self.assertEqual(cfg["profiles"]["far"], self.elsewhere)
        self.assertEqual(set(cfg["profiles"]), {"glm", "far"})

    def test_missing_config_is_empty(self):
        self.assertEqual(ccs.read_config(self.tmp.name), {"accounts": [], "profiles": {}})

    def test_profile_outside_ccs_dir_and_orphan_file_both_count(self):
        write_settings(self.elsewhere, "https://api.z.ai/api/anthropic", ["glm-9"] * 4)
        # ไฟล์ที่ไม่อยู่ใน config แล้ว (โปรไฟล์ถูกลบ) — log เก่ายังต้องเข้าถังถูก
        write_settings(os.path.join(self.dir, "old.settings.json"),
                       "https://api.moonshot.ai/anthropic", ["kimi-k9"] * 4)
        table = buckets.load_bucket_table(self.dir)
        self.assertEqual(table["glm-9"].key, "far")
        self.assertEqual(table["kimi-k9"].name, "Kimi")
        self.assertNotIn("SECRET-MUST-NOT-LEAK", repr(table))


class ModelMatchingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        write_settings(os.path.join(d, "bp.settings.json"),
                       "https://ark.ap-southeast.bytepluses.com/api/coding", ["glm-5.3-flash"] * 4)
        write_settings(os.path.join(d, "glm.settings.json"), "https://api.z.ai/api/anthropic",
                       ["glm-5.2", "glm-5.9[1m]", "glm-5.9[1m]", "glm-4.7"])
        self.instance = os.path.join(d, "instances", "spark")
        os.makedirs(self.instance)
        write_settings(os.path.join(d, "spark.settings.json"), "http://192.168.1.67:4000",
                       ["spark-code"] * 4, CLAUDE_CONFIG_DIR=self.instance)
        self.table = buckets.load_bucket_table(d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dashes_for_dots(self):
        bucket = buckets.bucket_for_model("glm-5-3-flash", self.table)
        self.assertEqual((bucket.key, bucket.name), ("bp", "BytePlus"))

    def test_context_suffix_stripped(self):
        self.assertEqual(buckets.bucket_for_model("glm-5.9", self.table).key, "glm")

    def test_pinned_instance_owns_unknown_models(self):
        self.assertEqual(buckets.bucket_for_model("qwen3.8-27b", self.table, self.instance).key,
                         "spark")
        # นอก instance นั้นยังไม่เดา และ Claude ใน instance เดียวกันยังเป็นของ Anthropic
        self.assertEqual(buckets.bucket_for_model("qwen3.8-27b", self.table), buckets.UNKNOWN)
        self.assertEqual(buckets.bucket_for_model("qwen3.8-27b", self.table, self.tmp.name),
                         buckets.UNKNOWN)
        self.assertEqual(buckets.bucket_for_model("claude-opus-5", self.table, self.instance),
                         buckets.ANTHROPIC)


if __name__ == "__main__":
    unittest.main()
