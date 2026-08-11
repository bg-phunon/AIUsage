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


if __name__ == "__main__":
    unittest.main()
