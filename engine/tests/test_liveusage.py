import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import liveusage  # noqa: E402
from aiusage.utilization import windows_from_limits  # noqa: E402


class KeychainServiceTest(unittest.TestCase):
    """suffix ต้องตรงกับ entry จริงใน Keychain — ตรวจกับเครื่องจริงมาแล้ว 2026-08-11"""

    def test_default_dir_has_no_suffix(self):
        home = os.path.expanduser("~")
        self.assertEqual(liveusage.keychain_service(os.path.join(home, ".claude")),
                         "Claude Code-credentials")
        self.assertEqual(liveusage.keychain_service("~/.claude"),
                         "Claude Code-credentials")

    def test_ccs_instances_match_observed_entries(self):
        observed = {
            "/Users/phunonkoysawat/.ccs/instances/mooz": "f2583e4d",
            "/Users/phunonkoysawat/.ccs/instances/spark": "589da1cf",
            "/Users/phunonkoysawat/.ccs/instances/work": "0edf7440",
        }
        for path, suffix in observed.items():
            self.assertEqual(liveusage.keychain_service(path),
                             "Claude Code-credentials-" + suffix)

    def test_trailing_slash_is_normalized(self):
        a = liveusage.keychain_service("/Users/phunonkoysawat/.ccs/instances/mooz")
        b = liveusage.keychain_service("/Users/phunonkoysawat/.ccs/instances/mooz/")
        self.assertEqual(a, b)


class WindowsFromLimitsTest(unittest.TestCase):
    """รูป limits เดียวกันทั้งแคชและ endpoint สด — parser ต้องใช้ร่วมได้"""

    def test_parses_live_style_payload(self):
        limits = [
            {"kind": "five_hour", "percent": 16, "resets_at": "2026-08-11T15:00:00Z",
             "severity": "normal", "is_active": False},
            {"kind": "seven_day", "percent": 42.5, "resets_at": "2026-08-14T00:00:00Z",
             "severity": "warning", "is_active": True,
             "scope": {"model": {"display_name": "Opus"}}},
        ]
        windows = windows_from_limits(limits)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].kind, "five_hour")
        self.assertEqual(windows[1].percent, 42.5)
        self.assertEqual(windows[1].scope, "Opus")
        self.assertTrue(windows[1].is_active)

    def test_garbage_rows_are_skipped(self):
        limits = [None, "x", {"kind": "five_hour"},  # ไม่มี resets_at
                  {"kind": "seven_day", "percent": 1, "resets_at": "2026-08-14T00:00:00Z"}]
        windows = windows_from_limits(limits)
        self.assertEqual([w.kind for w in windows], ["seven_day"])

    def test_none_and_empty_are_empty(self):
        self.assertEqual(windows_from_limits(None), [])
        self.assertEqual(windows_from_limits([]), [])


class MergedCredentialsTest(unittest.TestCase):
    """รวม token ใหม่เข้า blob เดิม — field แปลกหน้าต้องรอดครบทุกตัว"""

    BLOB = {"claudeAiOauth": {"accessToken": "old", "refreshToken": "r1",
                              "expiresAt": 1000, "scopes": ["user:inference"],
                              "subscriptionType": "team"},
            "somethingElse": {"keep": True}}

    def test_rotated_refresh_token_replaces_old(self):
        out = liveusage.merged_credentials(
            self.BLOB, {"access_token": "new", "refresh_token": "r2",
                        "expires_in": 3600}, now_ms=1_000_000)
        oauth = out["claudeAiOauth"]
        self.assertEqual(oauth["accessToken"], "new")
        self.assertEqual(oauth["refreshToken"], "r2")
        self.assertEqual(oauth["expiresAt"], 1_000_000 + 3600 * 1000 - 60_000)
        self.assertEqual(oauth["scopes"], ["user:inference"])
        self.assertEqual(oauth["subscriptionType"], "team")
        self.assertEqual(out["somethingElse"], {"keep": True})

    def test_missing_rotation_keeps_old_refresh_token(self):
        out = liveusage.merged_credentials(
            self.BLOB, {"access_token": "new"}, now_ms=0)
        self.assertEqual(out["claudeAiOauth"]["refreshToken"], "r1")
        self.assertEqual(out["claudeAiOauth"]["expiresAt"], 1000,
                         "ไม่มี expires_in ก็อย่าเดา — คงค่าเดิม")

    def test_original_blob_is_not_mutated(self):
        before = json.loads(json.dumps(self.BLOB))
        liveusage.merged_credentials(self.BLOB, {"access_token": "new"}, now_ms=0)
        self.assertEqual(self.BLOB, before)


class LiveCacheTest(unittest.TestCase):
    """ผลสดครั้งล่าสุดรอดข้ามรอบ — กันเลขกะพริบหายตอน live พลาดหนึ่งรอบ"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "live-cache.json")
        self.dir = "/Users/phunonkoysawat/.ccs/instances/mooz"
        self.svc = liveusage.keychain_service(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    LIMITS = [{"kind": "session", "percent": 14, "resets_at": "2026-08-13T09:00:00Z"}]

    def test_roundtrip(self):
        liveusage._store_live(self.svc, self.LIMITS, 1_700_000_000_000, path=self.path)
        util = liveusage.cached_live_utilization(self.dir, path=self.path)
        self.assertIsNotNone(util)
        self.assertEqual(util.windows[0].percent, 14)
        self.assertEqual(int(util.fetched_at.timestamp() * 1000), 1_700_000_000_000)

    def test_missing_or_garbage_is_none(self):
        self.assertIsNone(liveusage.cached_live_utilization(self.dir, path=self.path))
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("not json")
        self.assertIsNone(liveusage.cached_live_utilization(self.dir, path=self.path))

    def test_store_never_contains_token_like_keys(self):
        liveusage._store_live(self.svc, self.LIMITS, 1, path=self.path)
        text = open(self.path, encoding="utf-8").read().lower()
        for word in ("token", "secret", "authorization"):
            self.assertNotIn(word, text)


class RefreshBackoffTest(unittest.TestCase):
    def test_first_attempt_is_allowed(self):
        self.assertTrue(liveusage.should_attempt_refresh({}, "svc", now=100.0))

    def test_recent_failure_blocks_retry(self):
        backoff = {"svc": 100.0}
        self.assertFalse(liveusage.should_attempt_refresh(backoff, "svc", now=100.0 + 60))
        self.assertTrue(liveusage.should_attempt_refresh(
            backoff, "svc", now=100.0 + liveusage.BACKOFF_SECONDS))

    def test_other_services_are_independent(self):
        self.assertTrue(liveusage.should_attempt_refresh({"a": 100.0}, "b", now=101.0))


if __name__ == "__main__":
    unittest.main()
