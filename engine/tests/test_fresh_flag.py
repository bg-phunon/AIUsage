"""ปุ่มรีเฟรชของแอป (`--fresh`) ข้ามแคช % ของ Claude/Codex แต่ไม่ถามซ้ำในรอบเดียว"""

import importlib.util
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import clilive

ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ai-usage.60s.py")
spec = importlib.util.spec_from_file_location("engine_main_fresh", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class SplitTest(unittest.TestCase):
    def test_flag_is_removed(self):
        self.assertEqual(engine.split_fresh_flag(["--fresh", "--snapshot"]), (["--snapshot"], True))
        self.assertEqual(engine.split_fresh_flag(["--snapshot"]), (["--snapshot"], False))


class ClaudeCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "claude-live.json")
        self.calls = []
        self.now = [1000.0]

    def tearDown(self):
        clilive.FRESH_SINCE = None
        self.tmp.cleanup()

    def fetch(self, d):
        self.calls.append(d)
        return {"limits": []}

    def clock(self):
        return self.now[0]

    def test_fresh_refetches_a_recent_answer_once(self):
        clilive.warm(["a"], fetch=self.fetch, path=self.path, clock=self.clock)
        self.now[0] += 30
        clilive.live("a", fetch=self.fetch, path=self.path, clock=self.clock)
        self.assertEqual(len(self.calls), 1)          # ปกติ: ยังอยู่ในแคช 3 นาที
        clilive.FRESH_SINCE = self.now[0]
        self.now[0] += 1
        clilive.warm(["a"], fetch=self.fetch, path=self.path, clock=self.clock)
        clilive.live("a", fetch=self.fetch, path=self.path, clock=self.clock)
        self.assertEqual(len(self.calls), 2)          # กดรีเฟรช: ถามใหม่ครั้งเดียว


class CodexCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "codex-live.json")
        self.calls = 0
        engine._codex_forced = False

    def tearDown(self):
        clilive.FRESH_SINCE = None
        engine._codex_forced = False
        self.tmp.cleanup()

    def fetch(self):
        self.calls += 1
        return None if self.calls > 1 else {"rateLimits": {}}

    def test_fresh_asks_once_even_when_it_fails(self):
        clock = lambda: 1000.0
        engine.codex_live(fetch=self.fetch, path=self.path, clock=clock)
        clilive.FRESH_SINCE = 1001.0
        late = lambda: 1002.0
        first = engine.codex_live(fetch=self.fetch, path=self.path, clock=late)
        engine.codex_live(fetch=self.fetch, path=self.path, clock=late)
        self.assertEqual(self.calls, 2)               # ถามซ้ำแค่ครั้งเดียว
        self.assertIsNotNone(first)                   # ถามไม่สำเร็จยังได้ของเก่า


if __name__ == "__main__":
    unittest.main()
