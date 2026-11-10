"""ใบรีเซ็ตลิมิตของ Claude จากไฟล์ — `unusedLimitResetStatusCache` ใน .claude.json

CLI 2.1.322 ถาม server ด้วย `?cedar_ember=1` เอง แล้วจดผลลง global config:
{accountUuid, holdsUnusedReset, checkedAt, validUntil} (ms) · validUntil คือ
min(checkedAt + 3 วัน, วันหมดอายุของใบที่ยังใช้ได้) จึงบอกได้แค่ "มีอย่างน้อยหนึ่งใบ"
ไม่รู้จำนวนและไม่รู้วันหมดอายุจริง · `false` อาจแปลว่า "ไม่มีสิทธิ์รู้" (eligible
false ก็เขียน false) จึงห้ามอ่านเป็นศูนย์
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import utilization as u

NOW = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
ACCOUNT = "acct-uuid-1"


def ms(dt):
    return int(dt.timestamp() * 1000)


class HintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "acct")
        os.makedirs(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, cache, account=ACCOUNT):
        data = {"oauthAccount": {"accountUuid": account}}
        if cache is not None:
            data["unusedLimitResetStatusCache"] = cache
        with open(os.path.join(self.dir, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def cache(self, holds=True, checked=NOW - timedelta(hours=1),
              valid=NOW + timedelta(days=2), account=ACCOUNT):
        return {"accountUuid": account, "holdsUnusedReset": holds,
                "checkedAt": ms(checked), "validUntil": ms(valid)}

    def hint(self):
        return u.read_unused_reset_hint(self.dir, NOW)

    def test_holding_a_reset_means_at_least_one(self):
        self.write(self.cache())
        h = self.hint()
        self.assertEqual(h["count"], 1)
        self.assertTrue(h["atLeast"])
        self.assertEqual(h["expiring"], [])
        self.assertIsNone(h["nextAvailableAt"])

    def test_false_is_not_zero(self):
        # eligible:false ก็เขียน false — ไม่มีสิทธิ์รู้ ≠ ไม่เหลือใบ
        self.write(self.cache(holds=False))
        self.assertIsNone(self.hint())

    def test_past_valid_until_is_unknown(self):
        self.write(self.cache(checked=NOW - timedelta(days=4), valid=NOW - timedelta(days=1)))
        self.assertIsNone(self.hint())

    def test_another_account_does_not_count(self):
        # สลับบัญชีใน config dir เดียวกัน — แคชของคนเก่าไม่ใช่ของเรา
        self.write(self.cache(account="someone-else"))
        self.assertIsNone(self.hint())

    def test_missing_cache_or_file(self):
        self.assertIsNone(self.hint())
        self.write(None)
        self.assertIsNone(self.hint())

    def test_garbage_is_ignored(self):
        self.write({"accountUuid": ACCOUNT, "holdsUnusedReset": "yes",
                    "checkedAt": "x", "validUntil": None})
        self.assertIsNone(self.hint())

    def test_checked_in_the_future_is_ignored(self):
        self.write(self.cache(checked=NOW + timedelta(hours=1)))
        self.assertIsNone(self.hint())

    def test_reads_the_ccs_sibling_file_too(self):
        # บัญชี default: HOME/.claude.json อยู่นอก ~/.claude
        data = {"oauthAccount": {"accountUuid": ACCOUNT},
                "unusedLimitResetStatusCache": self.cache()}
        with open(self.dir.rstrip("/") + ".json", "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertEqual(self.hint()["count"], 1)


if __name__ == "__main__":
    unittest.main()
