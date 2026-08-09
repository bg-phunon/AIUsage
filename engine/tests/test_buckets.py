import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import buckets


def write_settings(dirpath, name, base_url, models):
    keys = ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL")
    env = {"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": "SECRET-MUST-NOT-LEAK"}
    env.update(dict(zip(keys, models)))
    with open(os.path.join(dirpath, name), "w", encoding="utf-8") as f:
        json.dump({"env": env}, f)


class BucketTableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        write_settings(d, "qwenc.settings.json", "https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic",
                       ["qwen3.8-max", "qwen3.8-max", "deepseek-v4-flash-0731", "deepseek-v4-flash-0731"])
        write_settings(d, "glm.settings.json", "https://api.z.ai/api/anthropic",
                       ["glm-5.2", "glm-5.2[1m]", "glm-5.2[1m]", "glm-4.7"])
        write_settings(d, "spark.settings.json", "http://192.168.1.67:4000",
                       ["qwen36-35b-code"] * 3 + ["qwen36-35b-fast"])
        self.table = buckets.load_bucket_table(d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_models_share_or_split_by_endpoint(self):
        self.assertEqual(buckets.bucket_for_model("qwen3.8-max", self.table).key,
                         buckets.bucket_for_model("deepseek-v4-flash-0731", self.table).key)
        paid = buckets.bucket_for_model("qwen3.8-max", self.table)
        lan = buckets.bucket_for_model("qwen36-35b-code", self.table)
        self.assertNotEqual(paid.key, lan.key)
        self.assertFalse(paid.local)
        self.assertTrue(lan.local)

    def test_glm_and_fallbacks(self):
        self.assertEqual(buckets.bucket_for_model("GLM-5.2", self.table).name, "GLM")
        self.assertEqual(buckets.bucket_for_model("claude-opus-5", self.table), buckets.ANTHROPIC)
        self.assertEqual(buckets.bucket_for_model("new-model", self.table), buckets.UNKNOWN)
        self.assertEqual(buckets.bucket_for_model(None, self.table), buckets.UNKNOWN)
        self.assertNotIn("SECRET-MUST-NOT-LEAK", repr(self.table))


class LocalHostTest(unittest.TestCase):
    def test_private_hosts(self):
        for host in ("localhost", "127.0.0.1", "192.168.1.1", "10.0.0.4", "172.16.5.1"):
            self.assertTrue(buckets.is_local_host(host))

    def test_public_hosts(self):
        self.assertFalse(buckets.is_local_host("api.anthropic.com"))


if __name__ == "__main__":
    unittest.main()
