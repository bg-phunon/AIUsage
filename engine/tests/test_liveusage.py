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


class FakeKeychain:
    """Keychain จำลอง — จดทุกครั้งที่ถูกเขียน ไว้จับการเขียนทับ"""

    def __init__(self, blob):
        self.blob = json.loads(json.dumps(blob))
        self.writes = []

    def read(self, service):
        return json.loads(json.dumps(self.blob))

    def write(self, service, account, blob):
        self.blob = json.loads(json.dumps(blob))
        self.writes.append(self.blob)
        return True


class RaceInjectingKeychain(FakeKeychain):
    """จำลอง "อีกฝั่งเขียนแทรก" — ทันทีหลังเขียนครั้งที่ swap_on_write พอดี
    ของบน Keychain เปลี่ยนเป็นของคนอื่น (สิ่งที่เราอ่านรอบถัดไปจะได้เห็น)"""

    def __init__(self, blob, swap_on_write, swapped_blob):
        super().__init__(blob)
        self.swap_on_write = swap_on_write
        self.swapped_blob = json.loads(json.dumps(swapped_blob))

    def write(self, service, account, blob):
        self.blob = json.loads(json.dumps(blob))
        self.writes.append(self.blob)
        if len(self.writes) == self.swap_on_write:
            self.blob = json.loads(json.dumps(self.swapped_blob))
        return True


class ConcurrentRefreshTest(unittest.TestCase):
    """Claude Code กับ engine ต่ออายุ token ก้อนเดียวกัน — ห้ามกลบของกันเอง

    เคสจริง 2026-08-17: engine อ่าน blob ที่มี R1 (หมดอายุ) แล้วระหว่างนั้น
    Claude Code ต่ออายุได้ R2 เขียนลง Keychain — engine เอา R1 เขียนกลับทับ
    R1 ถูก server ยกเลิกไปแล้วตอนหมุน = บัญชีหลุด ต้อง login ใหม่
    """

    NOW = 1_800_000_000.0

    def setUp(self):
        self.kc = FakeKeychain({})
        self.refresh_calls = []
        self.marks = []
        patches = {
            "_read_credentials": lambda svc: self.kc.read(svc),
            "_write_credentials": lambda svc, acct, blob: self.kc.write(svc, acct, blob),
            "_keychain_account": lambda svc: "phunonkoysawat",
            "_read_backoff": lambda: {},
            "_mark_backoff": lambda svc, step: self.marks.append(step),
            "_clear_backoff": lambda svc, steps=None: None,
            "_oauth_refresh": self._fake_oauth_refresh,
        }
        self.saved = {name: getattr(liveusage, name) for name in patches}
        for name, fn in patches.items():
            setattr(liveusage, name, fn)
        self.saved_time = liveusage.time.time
        liveusage.time.time = lambda: self.NOW

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(liveusage, name, fn)
        liveusage.time.time = self.saved_time

    def _fake_oauth_refresh(self, refresh_token, timeout=10.0):
        self.refresh_calls.append(refresh_token)
        if refresh_token != "R2":
            return None  # server ยกเลิก R1 ไปแล้วตอนหมุนเป็น R2
        return {"access_token": "A3", "refresh_token": "R3", "expires_in": 3600}

    @staticmethod
    def _blob(access, refresh, expires_ms):
        return {"claudeAiOauth": {"accessToken": access, "refreshToken": refresh,
                                  "expiresAt": expires_ms, "scopes": ["user:inference"]}}

    def test_does_not_clobber_credentials_refreshed_by_claude_code(self):
        """blob ที่ engine ถืออยู่เก่าแล้ว — Keychain มีของใหม่กว่า ห้ามเขียนทับ"""
        stale = self._blob("A1", "R1", int((self.NOW - 300) * 1000))
        self.kc.blob = self._blob("A2", "R2", int((self.NOW + 3600) * 1000))

        liveusage._refreshed_token("svc", stale)

        self.assertEqual(self.kc.blob["claudeAiOauth"]["refreshToken"], "R2",
                         "เขียน R1 ที่ถูกยกเลิกแล้วทับ R2 = บัญชีหลุด")
        self.assertNotIn("R1", self.refresh_calls,
                         "ห้ามยิง refresh ด้วย token ที่ถูกยกเลิกไปแล้ว")

    def test_uses_the_token_claude_code_already_refreshed(self):
        """มีคนต่ออายุให้แล้ว ก็ใช้ของเขา ไม่ต้องหมุนซ้ำให้ของเขาตาย"""
        stale = self._blob("A1", "R1", int((self.NOW - 300) * 1000))
        self.kc.blob = self._blob("A2", "R2", int((self.NOW + 3600) * 1000))

        self.assertEqual(liveusage._refreshed_token("svc", stale), "A2")
        self.assertEqual(self.refresh_calls, [], "ไม่ต้องเรียก endpoint เลย")

    def test_refreshes_from_the_freshest_blob_on_disk(self):
        """ไม่มีใครแตะ — ต่ออายุตามปกติ และหมุนจากของที่อ่านสดที่สุด"""
        stale = self._blob("A1", "R1", int((self.NOW - 300) * 1000))
        self.kc.blob = self._blob("A2", "R2", int((self.NOW - 100) * 1000))

        self.assertEqual(liveusage._refreshed_token("svc", stale), "A3")
        self.assertEqual(self.refresh_calls, ["R2"])
        self.assertEqual(self.kc.blob["claudeAiOauth"]["refreshToken"], "R3")
        self.assertEqual(self.kc.blob["claudeAiOauth"]["scopes"], ["user:inference"])

    def test_failed_write_after_rotation_leaves_a_breadcrumb(self):
        """หมุนแล้วเก็บไม่ได้ = บัญชีหลุด ต้องมีร่องรอยให้ไล่ ไม่ใช่เงียบ"""
        self.kc.blob = self._blob("A2", "R2", int((self.NOW - 100) * 1000))
        rehearsed = []

        def write(svc, acct, blob):
            rehearsed.append(blob)
            return len(rehearsed) == 1  # ซ้อมผ่าน รอบจริงพัง

        liveusage._write_credentials = write
        liveusage._refreshed_token("svc", self.kc.blob)
        self.assertIn("write-after-refresh", self.marks)


class WriteRaceTest(unittest.TestCase):
    """verify-after-write — ถ้ามีใครเขียนแทรกจังหวะที่เราเขียน ต้องรู้ก่อนหมุนต่อ

    rehearse-race: หลังซ้อมเขียน อ่านกลับเจอของที่ใหม่กว่า → มีคนหมุนเองแล้ว
                   อย่าไปหมุนซ้ำ (หมุนซ้ำ = ยกเลิก refresh token ที่เขาเพิ่งเก็บ)
    publish-race: หมุนแล้วเขียนรอบจริงแต่โดนทับทันที → ต้องมี breadcrumb ไว้ไล่
    """

    NOW = 1_800_000_000.0

    def setUp(self):
        self.kc = FakeKeychain({})
        self.refresh_calls = []
        self.marks = []
        patches = {
            "_read_credentials": lambda svc: self.kc.read(svc),
            "_write_credentials": lambda svc, acct, blob: self.kc.write(svc, acct, blob),
            "_keychain_account": lambda svc: "phunonkoysawat",
            "_read_backoff": lambda: {},
            "_mark_backoff": lambda svc, step: self.marks.append(step),
            "_clear_backoff": lambda svc, steps=None: None,
            "_oauth_refresh": self._fake_oauth_refresh,
        }
        self.saved = {name: getattr(liveusage, name) for name in patches}
        for name, fn in patches.items():
            setattr(liveusage, name, fn)
        self.saved_time = liveusage.time.time
        liveusage.time.time = lambda: self.NOW

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(liveusage, name, fn)
        liveusage.time.time = self.saved_time

    def _fake_oauth_refresh(self, refresh_token, timeout=10.0):
        self.refresh_calls.append(refresh_token)
        return {"access_token": "A2", "refresh_token": "R2", "expires_in": 3600}

    @staticmethod
    def _blob(access, refresh, expires_ms):
        return {"claudeAiOauth": {"accessToken": access, "refreshToken": refresh,
                                  "expiresAt": expires_ms, "scopes": ["user:inference"]}}

    def test_writer_landing_right_after_rehearsal_blocks_rotation(self):
        """ซ้อมเขียนเสร็จ อ่านกลับเจอของคนอื่น — มีคนหมุนเองแล้ว ห้ามไปหมุนซ้ำ"""
        ours = self._blob("A1", "R1", int((self.NOW - 300) * 1000))
        theirs = self._blob("A2", "R2", int((self.NOW + 3600) * 1000))
        self.kc = RaceInjectingKeychain(ours, swap_on_write=1, swapped_blob=theirs)

        self.assertIsNone(liveusage._refreshed_token("svc", ours))

        self.assertEqual(self.refresh_calls, [],
                         "ห้ามยิง refresh ตัวที่อาจถูกหมุนไปแล้ว")
        self.assertIn("rehearsal-race", self.marks)
        self.assertEqual(self.kc.blob["claudeAiOauth"]["refreshToken"], "R2",
                         "ของคนอื่นบน Keychain ต้องอยู่ครบ เราไม่แตะเพิ่ม")

    def test_rotation_overwritten_before_verify_leaves_breadcrumb(self):
        """หมุนแล้วเขียนรอบจริง แต่โดนคนอื่นทับก่อนเราตรวจ — ต้องมีร่องรอย"""
        ours = self._blob("A1", "R1", int((self.NOW - 300) * 1000))
        theirs = self._blob("A9", "R9", int((self.NOW + 3600) * 1000))
        self.kc = RaceInjectingKeychain(ours, swap_on_write=2, swapped_blob=theirs)

        token = liveusage._refreshed_token("svc", ours)

        self.assertEqual(token, "A2", "token หมุนมาแล้วใช้ได้รอบนี้ ยังควรคืน")
        self.assertEqual(self.refresh_calls, ["R1"])
        self.assertIn("publish-race", self.marks)
        self.assertEqual(self.kc.blob["claudeAiOauth"]["refreshToken"], "R9",
                         "ของคนอื่นบน Keychain ต้องไม่โดนทับซ้ำ")

    def test_verify_read_failure_counts_as_reread_failure(self):
        """อ่านกลับเพื่อตรวจพลาด (เช่น เด้ง dialog) — นับเป็นขั้นอ่าน ไม่ใช่ race"""
        ours = self._blob("A1", "R1", int((self.NOW - 300) * 1000))
        self.kc = FakeKeychain(ours)
        state = {"reads": 0}

        def flaky_read(service):
            state["reads"] += 1
            return None if state["reads"] == 2 else json.loads(json.dumps(self.kc.blob))

        liveusage._read_credentials = flaky_read
        self.assertIsNone(liveusage._refreshed_token("svc", ours))

        self.assertEqual(self.refresh_calls, [], "ยังไม่ถึงขั้นหมุน")
        self.assertIn("keychain-reread", self.marks)


class RereadBreadcrumbTest(unittest.TestCase):
    """keychain-reread ต้องโดนล้างเหมือนขั้นอ่านอื่น

    อ่านสดพลาดชั่วคราวครั้งเดียว (เช่น macOS เด้ง dialog สิทธิ์) ไม่ควรกดปิด
    การรีเฟรช 15 นาที ทั้งที่รอบถัดไปอ่านผ่าน — ต้อง self-heal แบบอ่านขั้นอื่น
    """

    NOW = 1_800_000_000.0

    def setUp(self):
        self.store = {}
        self.blob = {}
        self.saved = {}
        self.saved_time = liveusage.time.time
        liveusage.time.time = lambda: self.NOW

    def tearDown(self):
        liveusage.time.time = self.saved_time
        for name, fn in self.saved.items():
            setattr(liveusage, name, fn)

    def _set_expiry(self, offset_seconds):
        self.blob = {"claudeAiOauth": {
            "accessToken": "A1", "refreshToken": "R1",
            "expiresAt": int((self.NOW + offset_seconds) * 1000)}}

    def test_keychain_reread_is_a_read_stage_step(self):
        self.assertIn("keychain-reread", liveusage._READ_STAGE_STEPS)

    def test_reread_failure_cleared_by_next_successful_read(self):
        def mark(service, step):
            self.store[service] = {"ts": 0, "step": step}

        def clear(service, steps=None):
            entry = self.store.get(service)
            if entry is not None and (steps is None or entry.get("step") in steps):
                self.store.pop(service, None)

        self.saved.update({
            "_read_credentials": liveusage._read_credentials,
            "_mark_backoff": liveusage._mark_backoff,
            "_clear_backoff": liveusage._clear_backoff,
            "_refreshed_token": liveusage._refreshed_token,
        })
        liveusage._read_credentials = lambda svc: self.blob
        liveusage._mark_backoff = mark
        liveusage._clear_backoff = clear
        liveusage._refreshed_token = lambda svc, blob: mark(svc, "keychain-reread") or None

        svc = liveusage.keychain_service("~/.claude")

        # round 1: เก่าเกิน grace → พยายามหมุน แต่ติดขั้นอ่านสด → breadcrumb
        self._set_expiry(-(liveusage.REFRESH_GRACE_SECONDS + 1))
        self.assertIsNone(liveusage._read_token("~/.claude"))
        self.assertEqual(self.store[svc]["step"], "keychain-reread")

        # round 2: อ่านผ่าน (token สด) → ขั้นอ่านถูกกวาด รวมทั้ง keychain-reread
        self._set_expiry(+3600)
        self.assertEqual(liveusage._read_token("~/.claude"), "A1")
        self.assertNotIn(svc, self.store, "keychain-reread ต้องโดนล้างด้วย")


class RefreshGraceTest(unittest.TestCase):
    """อย่าไปหมุน token ของบัญชีที่ยังมีเจ้าของดูแล — ยิ่งหมุนน้อย ยิ่งชนยาก"""

    NOW = 1_800_000_000.0

    def setUp(self):
        self.refreshed = []
        self.blob = {}
        patches = {
            "_read_credentials": lambda svc: self.blob,
            "_mark_backoff": lambda svc, step: None,
            "_clear_backoff": lambda svc, steps=None: None,
            "_refreshed_token": lambda svc, blob: self.refreshed.append(svc) or "NEW",
        }
        self.saved = {name: getattr(liveusage, name) for name in patches}
        for name, fn in patches.items():
            setattr(liveusage, name, fn)
        self.saved_time = liveusage.time.time
        liveusage.time.time = lambda: self.NOW

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(liveusage, name, fn)
        liveusage.time.time = self.saved_time

    def _set_expiry(self, offset_seconds):
        self.blob = {"claudeAiOauth": {
            "accessToken": "A1", "refreshToken": "R1",
            "expiresAt": int((self.NOW + offset_seconds) * 1000)}}

    def test_valid_token_is_used_as_is(self):
        self._set_expiry(+3600)
        self.assertEqual(liveusage._read_token("~/.claude"), "A1")
        self.assertEqual(self.refreshed, [])

    def test_just_expired_waits_for_the_owner(self):
        """เพิ่งหมดอายุ — Claude Code กำลังจะต่อให้ อย่าไปแย่งหมุน"""
        self._set_expiry(-60)
        self.assertEqual(liveusage._read_token("~/.claude"), "A1")
        self.assertEqual(self.refreshed, [], "ยังไม่ถึงคิวเรา")

    def test_long_expired_account_is_refreshed_by_us(self):
        """ค้างมานาน = ไม่มีใครดูแล เราต่อเอง (นี่คือเหตุผลของฟีเจอร์)"""
        self._set_expiry(-(liveusage.REFRESH_GRACE_SECONDS + 1))
        self.assertEqual(liveusage._read_token("~/.claude"), "NEW")
        self.assertEqual(len(self.refreshed), 1)


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
