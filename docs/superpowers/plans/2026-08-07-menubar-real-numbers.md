# AI Usage menu bar — แผนลงมือ เฟส 1: ตัวเลขจริง

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** แอป menu bar ที่เปิดขึ้นมาแล้วแสดง % โควตาจริงของ Claude ทุกบัญชีและ Codex พร้อมบอกอายุข้อมูลอย่างซื่อสัตย์

**Architecture:** Python engine เดิมสแกน transcript แล้วอ่าน `cachedUsageUtilization` ที่ Claude Code เขียนไว้ (เป็น % ทางการจาก Anthropic ไม่ต้องคำนวณเอง) รวมเป็น `snapshot.json` → แอป Swift เรียก engine เองทุก 60 วิผ่าน `Process` (ไม่ใช้ launchd) แล้วเรนเดอร์ลง `NSStatusItem` + popover ข้อมูลถูกจัดกลุ่มตาม **(บัญชี × ถังโควตา)** โดยถังกำหนดจาก endpoint ใน `~/.ccs/*.settings.json` ไม่ใช่ชื่อโมเดล

**Tech Stack:** Python 3.14 (stdlib เท่านั้น ไม่มี pytest — ใช้ `unittest`) · Swift 5 / SwiftUI / AppKit · XcodeGen + xcodebuild · macOS 14+

## Global Constraints

ทุก task อยู่ภายใต้ข้อบังคับเหล่านี้ ไม่ต้องเขียนซ้ำในแต่ละ task

- **ห้ามเปิด App Sandbox** — `ENABLE_APP_SANDBOX: NO` ต้องคงไว้ ถ้าเปิด `NSHomeDirectory()` จะชี้ไป container แล้วอ่าน snapshot ไม่เจอ
- **deployment target macOS 14.0** ตาม `project.yml`
- **ห้ามแก้ตรรกะการนับใน `ai-usage.60s.py`** — ฟังก์ชัน `claude_entries` / `summarize` / `current_block` / `total_tokens` ทดสอบกับข้อมูลจริงแล้ว เพิ่มของใหม่รอบๆ ได้ แต่ห้ามแก้ข้างใน
- **ห้ามอ่าน เขียน log หรือส่งต่อค่า `ANTHROPIC_AUTH_TOKEN` / `oauth_creds` / `.credentials.json`** อ่านได้เฉพาะ `ANTHROPIC_BASE_URL` และช่องชื่อโมเดล
- **ไม่ใช้ launchd** — แอปเรียก engine เอง ลบ `com.aiusage.snapshot.plist` ทิ้ง
- **ไม่ใช้ WidgetKit** — เป็น menu bar app อย่างเดียว
- **แถบ menu bar ไม่เกิน 10 ตัวอักษรต่อบรรทัด**
- **หลักการ "ไม่แกล้งทำเป็นรู้"** — ถ้าไม่รู้เพดานหรือข้อมูลเก่า ห้ามแสดงแถบทึบ
- ข้อความที่ผู้ใช้เห็นเป็น**ภาษาไทย** ตามของเดิมในโปรเจกต์
- ทุก task จบด้วย commit

**อ้างอิงสเปก:** `docs/superpowers/specs/2026-08-06-ai-usage-menubar-design.md`

**อยู่นอกขอบเขตแผนนี้** (ไปแผน 2–3): Qwen Cloud dashboard API · โหมดแสดงเงินของ GLM · หน้า settings · โลโก้ provider · การแจ้งเตือนใกล้ชนลิมิต

---

### Task 1: ตั้ง git และจัดโฟลเดอร์ให้ตรงกับ project.yml

ตอนนี้โฟลเดอร์ยังไม่ใช่ git repo และไฟล์ Swift วางแบนที่ราก แต่ `project.yml` หาใน `App/` `Shared/` `Widget/` → `xcodegen generate` พังแน่นอน task นี้ทำให้ build ผ่านได้เป็นครั้งแรก และตัด target WidgetKit ที่สเปกเลิกใช้แล้วออก

**Files:**
- Create: `.gitignore`
- Create: `App/AIUsageApp.swift` (ย้ายจาก `AIUsageApp.swift`)
- Create: `Shared/UsageSnapshot.swift` (ย้ายจาก `UsageSnapshot.swift`)
- Delete: `AIUsageWidget.swift`, `com.aiusage.snapshot.plist`, `__pycache__/`
- Modify: `project.yml`

**Interfaces:**
- Consumes: ไม่มี (task แรก)
- Produces: โครงโฟลเดอร์ `App/` `Shared/` และ `project.yml` ที่มี target เดียวชื่อ `AIUsage` — ทุก task ที่เพิ่มไฟล์ Swift ต้องวางใน 2 โฟลเดอร์นี้

- [ ] **Step 1: ตั้ง git repo และ .gitignore**

```bash
cd /Users/phunonkoysawat/Documents/Develop/projects/AIUsageWidget
git init
```

สร้าง `.gitignore`:

```gitignore
build/
AIUsage.xcodeproj/
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 2: ย้ายไฟล์ Swift เข้าโฟลเดอร์ และลบของที่เลิกใช้**

```bash
mkdir -p App Shared
git mv AIUsageApp.swift App/AIUsageApp.swift 2>/dev/null || mv AIUsageApp.swift App/
git mv UsageSnapshot.swift Shared/UsageSnapshot.swift 2>/dev/null || mv UsageSnapshot.swift Shared/
rm -f AIUsageWidget.swift com.aiusage.snapshot.plist
rm -rf __pycache__
```

`AIUsageWidget.swift` มีแต่ view ขนาด small/medium/large ของ WidgetKit ซึ่งใช้กับ popover ไม่ได้ — ลบทิ้ง ไม่ต้องเก็บ

- [ ] **Step 3: แก้ project.yml ตัด target widget ออก**

แทนที่ทั้งไฟล์ `project.yml` ด้วย:

```yaml
name: AIUsage
options:
  bundleIdPrefix: com.local
  deploymentTarget:
    macOS: "14.0"
  createIntermediateGroups: true

settings:
  base:
    SWIFT_VERSION: "5.0"
    CODE_SIGN_STYLE: Automatic
    ENABLE_HARDENED_RUNTIME: NO
    ENABLE_APP_SANDBOX: NO
    MARKETING_VERSION: "1.0"
    CURRENT_PROJECT_VERSION: "1"

targets:
  AIUsage:
    type: application
    platform: macOS
    sources:
      - App
      - Shared
      - path: engine
        buildPhase: resources
      - path: ai-usage.60s.py
        buildPhase: resources
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.local.aiusage
        PRODUCT_NAME: AIUsage
        GENERATE_INFOPLIST_FILE: YES
        INFOPLIST_KEY_CFBundleDisplayName: AI Usage
        INFOPLIST_KEY_LSUIElement: YES
        INFOPLIST_KEY_NSHumanReadableCopyright: ""
        COMBINE_HIDPI_IMAGES: YES

  AIUsageTests:
    type: bundle.unit-test
    platform: macOS
    sources:
      - Tests
    dependencies:
      - target: AIUsage
```

สามอย่างที่เปลี่ยน: ตัด target `AIUsageWidget` ทิ้ง · เพิ่ม `INFOPLIST_KEY_LSUIElement: YES` (menu bar app ต้องไม่มีไอคอนใน Dock) · ใส่ engine เข้า resources ของ bundle เพื่อให้แอปเรียก Python ที่มากับตัวเองได้ ไม่ต้องพึ่ง path ข้างนอก

- [ ] **Step 4: สร้างโฟลเดอร์ที่ project.yml อ้างถึงแต่ยังว่าง**

`engine/` กับ `Tests/` ต้องมีอยู่จริงตอน `xcodegen generate` ไม่งั้นมันเตือน สร้าง placeholder ที่จะถูกแทนใน task ถัดไป:

```bash
mkdir -p engine Tests
touch engine/.gitkeep Tests/.gitkeep
```

- [ ] **Step 5: ตรวจว่า xcodegen ผ่าน**

```bash
command -v xcodegen >/dev/null || brew install xcodegen
xcodegen generate
```

Expected: `Created project at AIUsage.xcodeproj` ไม่มี error เรื่อง source path ไม่เจอ

- [ ] **Step 6: ตรวจว่า build ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -5
```

Expected: `** BUILD SUCCEEDED **`

ถ้าพังเพราะ `AIUsageApp.swift` อ้างถึง type ที่อยู่ในไฟล์ที่ลบไป ให้แก้ `App/AIUsageApp.swift` ให้เหลือแค่โครงว่างที่ compile ผ่าน — task 9 จะเขียนทับทั้งไฟล์อยู่แล้ว:

```swift
import SwiftUI

@main
struct AIUsageApp: App {
    var body: some Scene {
        Settings { EmptyView() }
    }
}
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: init repo, restructure for menu bar app, drop WidgetKit target"
```

---

### Task 2: แผนที่ model → ถังโควตา จาก ccs settings

ถังโควตาถูกกำหนดโดย **endpoint** ไม่ใช่ชื่อโมเดล — แผน Qwen Cloud ก้อนเดียวให้ทั้ง `qwen3.8-max` และ `deepseek-v4-flash-0731` ส่วน `qwen36-35b` (spark) วิ่งบน LAN ไม่มีโควตาเลย กฎ prefix ตามชื่อยี่ห้อจะแยก deepseek ออกไปผิดถัง และรวม qwen สองตัวที่คนละถังเข้าด้วยกัน

**Files:**
- Create: `engine/aiusage/__init__.py`
- Create: `engine/aiusage/buckets.py`
- Test: `engine/tests/test_buckets.py`

**Interfaces:**
- Consumes: ไม่มี
- Produces:
  - `Bucket` — NamedTuple: `key: str`, `name: str`, `host: str`, `local: bool`
  - `ANTHROPIC = Bucket("anthropic", "Claude", "api.anthropic.com", False)`
  - `UNKNOWN = Bucket("unknown", "ยังไม่รู้จัก", "", False)`
  - `is_local_host(host: str) -> bool`
  - `load_bucket_table(ccs_dir: str | None = None) -> dict[str, Bucket]` — คีย์เป็นชื่อโมเดล lowercase
  - `bucket_for_model(model: str | None, table: dict[str, Bucket]) -> Bucket`

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `engine/tests/test_buckets.py`:

```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import buckets  # noqa: E402


def write_settings(dirpath, name, base_url, models):
    keys = ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL")
    env = {"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": "SECRET-MUST-NOT-LEAK"}
    for k, m in zip(keys, models):
        env[k] = m
    with open(os.path.join(dirpath, name), "w", encoding="utf-8") as f:
        json.dump({"env": env}, f)


class BucketTableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        write_settings(d, "qwenc.settings.json",
                       "https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic",
                       ["qwen3.8-max", "qwen3.8-max",
                        "deepseek-v4-flash-0731", "deepseek-v4-flash-0731"])
        write_settings(d, "glm.settings.json", "https://api.z.ai/api/anthropic",
                       ["glm-5.2", "glm-5.2[1m]", "glm-5.2[1m]", "glm-4.7"])
        write_settings(d, "spark.settings.json", "http://192.168.1.67:4000",
                       ["qwen36-35b-code"] * 3 + ["qwen36-35b-fast"])
        self.table = buckets.load_bucket_table(d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_deepseek_belongs_to_the_qwen_cloud_bucket(self):
        """deepseek คือช่อง Sonnet ของแผน Qwen Cloud ไม่ใช่บัญชี DeepSeek แยก"""
        b = buckets.bucket_for_model("deepseek-v4-flash-0731", self.table)
        self.assertEqual(b.key, "qwenc")
        self.assertEqual(b.name, "Qwen Cloud")

    def test_qwen_flagship_and_deepseek_share_one_bucket(self):
        a = buckets.bucket_for_model("qwen3.8-max", self.table)
        b = buckets.bucket_for_model("deepseek-v4-flash-0731", self.table)
        self.assertEqual(a.key, b.key)

    def test_two_qwen_models_land_in_different_buckets(self):
        """qwen36-35b (LAN ฟรี) ต้องไม่ปนกับ qwen3.8-max (มีเพดาน)"""
        paid = buckets.bucket_for_model("qwen3.8-max", self.table)
        lan = buckets.bucket_for_model("qwen36-35b-code", self.table)
        self.assertNotEqual(paid.key, lan.key)
        self.assertFalse(paid.local)
        self.assertTrue(lan.local)

    def test_glm_models_map_to_glm(self):
        for m in ("glm-5.2", "glm-5.2[1m]", "glm-4.7"):
            self.assertEqual(buckets.bucket_for_model(m, self.table).name, "GLM")

    def test_claude_models_fall_back_to_anthropic(self):
        b = buckets.bucket_for_model("claude-opus-5", self.table)
        self.assertEqual(b, buckets.ANTHROPIC)

    def test_unrecognised_model_is_not_dropped_silently(self):
        b = buckets.bucket_for_model("something-new-9000", self.table)
        self.assertEqual(b, buckets.UNKNOWN)

    def test_none_model_is_unknown(self):
        self.assertEqual(buckets.bucket_for_model(None, self.table), buckets.UNKNOWN)

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(buckets.bucket_for_model("GLM-5.2", self.table).name, "GLM")

    def test_auth_token_never_appears_in_the_table(self):
        blob = repr(self.table)
        self.assertNotIn("SECRET-MUST-NOT-LEAK", blob)


class LocalHostTest(unittest.TestCase):
    def test_private_and_loopback_hosts_are_local(self):
        for h in ("localhost", "127.0.0.1", "192.168.1.67", "10.0.0.4", "172.16.5.1"):
            self.assertTrue(buckets.is_local_host(h), h)

    def test_public_hosts_are_not_local(self):
        for h in ("api.anthropic.com", "api.z.ai",
                  "token-plan.ap-southeast-1.maas.aliyuncs.com"):
            self.assertFalse(buckets.is_local_host(h), h)


class MissingDirTest(unittest.TestCase):
    def test_missing_ccs_dir_yields_empty_table_not_crash(self):
        self.assertEqual(buckets.load_bucket_table("/nonexistent/path/xyz"), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
cd /Users/phunonkoysawat/Documents/Develop/projects/AIUsageWidget
python3 -m unittest discover -s engine/tests -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'aiusage'`

- [ ] **Step 3: เขียน implementation**

สร้าง `engine/aiusage/__init__.py` (ไฟล์ว่าง):

```python
```

สร้าง `engine/aiusage/buckets.py`:

```python
"""แผนที่ชื่อโมเดล → ถังโควตา สร้างจาก ~/.ccs/*.settings.json

ถังโควตากำหนดโดย endpoint ไม่ใช่ยี่ห้อโมเดล เพราะแผนเดียวให้หลายยี่ห้อได้
(qwenc ให้ทั้ง qwen3.8-max และ deepseek-v4-flash-0731 ในโควตาก้อนเดียว)
และยี่ห้อเดียวอาจอยู่คนละถัง (qwen36-35b บน LAN ฟรี vs qwen3.8-max ที่มีเพดาน)

อ่านเฉพาะ ANTHROPIC_BASE_URL กับช่องชื่อโมเดล — ห้ามแตะ ANTHROPIC_AUTH_TOKEN
"""

import glob
import ipaddress
import json
import os
from typing import Dict, NamedTuple, Optional
from urllib.parse import urlparse


class Bucket(NamedTuple):
    key: str      # ไอดีคงที่ ใช้จับคู่ข้ามรอบ เช่น "qwenc"
    name: str     # ชื่อที่ผู้ใช้เห็น เช่น "Qwen Cloud"
    host: str     # โฮสต์ของ endpoint
    local: bool   # True = รันในเครือข่ายตัวเอง ไม่มีโควตาให้นับ


ANTHROPIC = Bucket("anthropic", "Claude", "api.anthropic.com", False)
UNKNOWN = Bucket("unknown", "ยังไม่รู้จัก", "", False)

MODEL_ENV_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)

# โฮสต์ที่รู้จัก → ชื่อที่ผู้ใช้เห็น เทียบแบบลงท้าย
HOST_NAMES = (
    ("anthropic.com", "Claude"),
    ("z.ai", "GLM"),
    ("bigmodel.cn", "GLM"),
    ("maas.aliyuncs.com", "Qwen Cloud"),
    ("dashscope.aliyuncs.com", "Qwen Cloud"),
    ("openai.com", "OpenAI"),
    ("moonshot.cn", "Kimi"),
    ("deepseek.com", "DeepSeek"),
)


def is_local_host(host: str) -> bool:
    """โฮสต์นี้อยู่ในเครือข่ายตัวเองไหม — ถ้าใช่แปลว่าไม่มีโควตาให้นับ"""
    if not host:
        return False
    bare = host.split(":")[0]
    if bare in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        return ipaddress.ip_address(bare).is_private
    except ValueError:
        return False


def _name_for_host(host: str, fallback: str) -> str:
    bare = host.split(":")[0]
    for suffix, name in HOST_NAMES:
        if bare == suffix or bare.endswith("." + suffix):
            return name
    return fallback


def load_bucket_table(ccs_dir: Optional[str] = None) -> Dict[str, Bucket]:
    """อ่านทุก *.settings.json แล้วคืน dict ชื่อโมเดล (lowercase) → Bucket"""
    if ccs_dir is None:
        ccs_dir = os.path.join(os.path.expanduser("~"), ".ccs")
    table: Dict[str, Bucket] = {}
    for path in sorted(glob.glob(os.path.join(ccs_dir, "*.settings.json"))):
        key = os.path.basename(path)[: -len(".settings.json")]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                env = (json.load(fh) or {}).get("env") or {}
        except (OSError, ValueError):
            continue
        base = env.get("ANTHROPIC_BASE_URL") or ""
        host = urlparse(base).hostname or ""
        bucket = Bucket(
            key=key,
            name=_name_for_host(host, key),
            host=host,
            local=is_local_host(host),
        )
        for env_key in MODEL_ENV_KEYS:
            model = env.get(env_key)
            if isinstance(model, str) and model.strip():
                table[model.strip().lower()] = bucket
    return table


def bucket_for_model(model: Optional[str], table: Dict[str, Bucket]) -> Bucket:
    """โมเดลนี้กินโควตาถังไหน

    ลำดับ: ตารางจาก ccs → ถ้าขึ้นต้น claude- ถือว่าเป็น Anthropic โดยตรง
    → ไม่งั้นตกถัง UNKNOWN (ต้องเห็นบนจอ ห้ามทิ้งเงียบ)
    """
    if not isinstance(model, str) or not model.strip():
        return UNKNOWN
    key = model.strip().lower()
    if key in table:
        return table[key]
    if key.startswith("claude-"):
        return ANTHROPIC
    return UNKNOWN
```

- [ ] **Step 4: รัน test ให้ผ่าน**

```bash
python3 -m unittest discover -s engine/tests -v
```

Expected: PASS ทั้ง 12 test

- [ ] **Step 5: ตรวจกับข้อมูลจริงบนเครื่อง**

```bash
python3 -c "
import sys; sys.path.insert(0, 'engine')
from aiusage import buckets
t = buckets.load_bucket_table()
for m, b in sorted(t.items()):
    print(f'{m:<28} → {b.name:<12} local={b.local}')
"
```

Expected: เห็น `deepseek-v4-flash-0731 → Qwen Cloud`, `qwen36-35b-code → spark local=True`, `glm-5.2 → GLM` และ**ไม่มี token โผล่**

- [ ] **Step 6: Commit**

```bash
git add engine/aiusage engine/tests
git commit -m "feat(engine): map models to quota buckets by endpoint, not brand"
```

---

### Task 3: อ่าน cachedUsageUtilization — % ทางการจาก Anthropic

Claude Code เก็บ % ที่ Anthropic ส่งมาไว้ใน `.claude.json` อยู่แล้ว ไม่ต้องปรับเทียบ ไม่ต้องแปลง token แต่มันไม่ refresh ระหว่างเซสชัน (วัดแล้ว: บัญชี `mooz` เก่า 40 ชม.) จึงต้องมีตรรกะบอกว่าตัวเลขที่แคชไว้**ยังเชื่อได้แค่ไหน** โดยเทียบกับเวลาที่มี traffic ล่าสุด

**Files:**
- Create: `engine/aiusage/utilization.py`
- Test: `engine/tests/test_utilization.py`

**Interfaces:**
- Consumes: ไม่มี
- Produces:
  - `Window` — NamedTuple: `kind: str`, `percent: float`, `resets_at: datetime`, `severity: str`, `scope: str | None`, `is_active: bool`
  - `Utilization` — NamedTuple: `fetched_at: datetime`, `windows: list[Window]`
  - `read_utilization(config_dir: str) -> Utilization | None`
  - `window_confidence(window, fetched_at, last_activity, now) -> str` คืนค่าหนึ่งใน `CONFIRMED_ZERO` / `VALID` / `LOWER_BOUND` / `UNSURE`
  - ค่าคงที่ `CONFIRMED_ZERO = "zero"`, `VALID = "valid"`, `LOWER_BOUND = "lower_bound"`, `UNSURE = "unsure"`

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `engine/tests/test_utilization.py`:

```python
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aiusage import utilization as u  # noqa: E402

T0 = datetime(2026, 8, 7, 6, 38, 6, tzinfo=timezone.utc)

SAMPLE = {
    "oauthAccount": {"organizationRateLimitTier": "default_claude_max_20x"},
    "cachedUsageUtilization": {
        "fetchedAtMs": int(T0.timestamp() * 1000),
        "utilization": {
            "five_hour": {"utilization": 5, "resets_at": "2026-08-07T07:10:00.238547+00:00"},
            "seven_day": {"utilization": 96, "resets_at": "2026-08-08T20:00:00.238567+00:00"},
            "limits": [
                {"kind": "session", "percent": 5, "severity": "normal",
                 "resets_at": "2026-08-07T07:10:00.238547+00:00",
                 "scope": None, "is_active": False},
                {"kind": "weekly_all", "percent": 96, "severity": "critical",
                 "resets_at": "2026-08-08T20:00:00.238567+00:00",
                 "scope": None, "is_active": False},
                {"kind": "weekly_scoped", "percent": 100, "severity": "critical",
                 "resets_at": "2026-08-08T20:00:00.238771+00:00",
                 "scope": {"model": {"id": None, "display_name": "Fable"}},
                 "is_active": True},
            ],
        },
    },
}


class ReadUtilizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "acct")
        os.makedirs(self.dir)
        with open(os.path.join(self.dir, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump(SAMPLE, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_fetched_at(self):
        self.assertEqual(u.read_utilization(self.dir).fetched_at, T0)

    def test_reads_all_three_windows(self):
        kinds = [w.kind for w in u.read_utilization(self.dir).windows]
        self.assertEqual(kinds, ["session", "weekly_all", "weekly_scoped"])

    def test_reads_percent_and_severity(self):
        w = u.read_utilization(self.dir).windows[1]
        self.assertEqual(w.percent, 96)
        self.assertEqual(w.severity, "critical")

    def test_scoped_window_keeps_model_name(self):
        w = u.read_utilization(self.dir).windows[2]
        self.assertEqual(w.scope, "Fable")
        self.assertTrue(w.is_active)

    def test_resets_at_is_timezone_aware(self):
        w = u.read_utilization(self.dir).windows[0]
        self.assertIsNotNone(w.resets_at.tzinfo)

    def test_sibling_json_path_also_works(self):
        """ccs บางบัญชีเก็บเป็น <dir>.json แทน <dir>/.claude.json"""
        alt = os.path.join(self.tmp.name, "other")
        with open(alt + ".json", "w", encoding="utf-8") as f:
            json.dump(SAMPLE, f)
        self.assertIsNotNone(u.read_utilization(alt))

    def test_missing_key_returns_none_not_crash(self):
        bare = os.path.join(self.tmp.name, "bare")
        os.makedirs(bare)
        with open(os.path.join(bare, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {}}, f)
        self.assertIsNone(u.read_utilization(bare))

    def test_missing_file_returns_none(self):
        self.assertIsNone(u.read_utilization("/nonexistent/zzz"))

    def test_corrupt_json_returns_none(self):
        bad = os.path.join(self.tmp.name, "bad")
        os.makedirs(bad)
        with open(os.path.join(bad, ".claude.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertIsNone(u.read_utilization(bad))


class ConfidenceTest(unittest.TestCase):
    def setUp(self):
        self.win = u.Window(
            kind="session", percent=42.0,
            resets_at=datetime(2026, 8, 7, 7, 10, tzinfo=timezone.utc),
            severity="normal", scope=None, is_active=False,
        )

    def test_no_traffic_and_window_rolled_means_certainly_zero(self):
        """mooz เงียบมา 40 ชม. → บล็อก 5 ชม. รีเซ็ตไปแล้วแน่นอน"""
        now = self.win.resets_at + timedelta(hours=40)
        self.assertEqual(
            u.window_confidence(self.win, T0, last_activity=None, now=now),
            u.CONFIRMED_ZERO)

    def test_traffic_before_reset_only_still_means_zero(self):
        now = self.win.resets_at + timedelta(hours=2)
        active = self.win.resets_at - timedelta(minutes=5)
        self.assertEqual(
            u.window_confidence(self.win, T0, last_activity=active, now=now),
            u.CONFIRMED_ZERO)

    def test_traffic_after_reset_means_unsure(self):
        now = self.win.resets_at + timedelta(hours=2)
        active = self.win.resets_at + timedelta(minutes=30)
        self.assertEqual(
            u.window_confidence(self.win, T0, last_activity=active, now=now),
            u.UNSURE)

    def test_no_traffic_and_window_open_means_cached_value_still_valid(self):
        now = T0 + timedelta(minutes=7)
        self.assertEqual(
            u.window_confidence(self.win, T0, last_activity=None, now=now),
            u.VALID)

    def test_traffic_since_fetch_makes_it_a_lower_bound(self):
        now = T0 + timedelta(minutes=20)
        active = T0 + timedelta(minutes=10)
        self.assertEqual(
            u.window_confidence(self.win, T0, last_activity=active, now=now),
            u.LOWER_BOUND)

    def test_traffic_before_fetch_does_not_count(self):
        now = T0 + timedelta(minutes=20)
        active = T0 - timedelta(minutes=10)
        self.assertEqual(
            u.window_confidence(self.win, T0, last_activity=active, now=now),
            u.VALID)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
python3 -m unittest discover -s engine/tests -v
```

Expected: FAIL — `ImportError: cannot import name 'utilization'`

- [ ] **Step 3: เขียน implementation**

สร้าง `engine/aiusage/utilization.py`:

```python
"""อ่าน cachedUsageUtilization ที่ Claude Code เขียนไว้ใน .claude.json

นี่คือ % ทางการจาก Anthropic ไม่ต้องปรับเทียบ ไม่ต้องแปลง token
แต่มันไม่ refresh ระหว่างเซสชัน (วัดแล้ว: refresh ตอนเปิด /usage หรือเริ่มเซสชันใหม่)
window_confidence() จึงมีไว้บอกว่าค่าที่แคชไว้ยังเชื่อได้แค่ไหน
"""

import json
import os
from datetime import datetime, timezone
from typing import List, NamedTuple, Optional

CONFIRMED_ZERO = "zero"        # หน้าต่างรีเซ็ตแล้วและไม่มีใครใช้ต่อ → 0% แน่นอน
VALID = "valid"                # ยังอยู่ในหน้าต่างเดิม ไม่มี traffic เพิ่ม → ค่าเดิมถูกต้อง
LOWER_BOUND = "lower_bound"    # มี traffic หลังแคช → ของจริงสูงกว่านี้
UNSURE = "unsure"              # หน้าต่างรีเซ็ตแล้วและมี traffic ต่อ → ไม่รู้เลย


class Window(NamedTuple):
    kind: str                  # session | weekly_all | weekly_scoped
    percent: float
    resets_at: datetime
    severity: str              # normal | warning | critical
    scope: Optional[str]       # ชื่อโมเดล ถ้าเป็นลิมิตเฉพาะโมเดล
    is_active: bool            # ตัวนี้กำลังบล็อกอยู่จริงไหม


class Utilization(NamedTuple):
    fetched_at: datetime
    windows: List[Window]


def _parse_ts(raw) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _config_paths(config_dir: str):
    """บัญชี default ใช้ <dir>/.claude.json · ccs บางบัญชีใช้ <dir>.json"""
    stripped = config_dir.rstrip("/")
    return (os.path.join(config_dir, ".claude.json"), stripped + ".json")


def read_utilization(config_dir: str) -> Optional[Utilization]:
    """คืน Utilization ถ้าบัญชีนี้มีข้อมูล ไม่มีก็คืน None (ไม่ throw)"""
    for path in _config_paths(config_dir):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        cached = (data or {}).get("cachedUsageUtilization")
        if not isinstance(cached, dict):
            continue
        fetched_ms = cached.get("fetchedAtMs")
        if not isinstance(fetched_ms, (int, float)):
            continue
        fetched_at = datetime.fromtimestamp(fetched_ms / 1000, timezone.utc)
        raw_limits = ((cached.get("utilization") or {}).get("limits")) or []
        windows = []
        for lim in raw_limits:
            if not isinstance(lim, dict):
                continue
            resets = _parse_ts(lim.get("resets_at"))
            if resets is None:
                continue
            scope_obj = (lim.get("scope") or {}).get("model") or {}
            windows.append(Window(
                kind=str(lim.get("kind") or "unknown"),
                percent=float(lim.get("percent") or 0),
                resets_at=resets,
                severity=str(lim.get("severity") or "normal"),
                scope=scope_obj.get("display_name") or None,
                is_active=bool(lim.get("is_active")),
            ))
        if not windows:
            continue
        return Utilization(fetched_at=fetched_at, windows=windows)
    return None


def window_confidence(window: Window, fetched_at: datetime,
                      last_activity: Optional[datetime],
                      now: datetime) -> str:
    """ค่าที่แคชไว้ยังเชื่อได้แค่ไหน

    แคชบอกความจริง ณ เวลา fetched_at · transcript บอกว่าหลังจากนั้นมีอะไรเกิดขึ้น
    สองอย่างรวมกันได้ข้อสรุปที่แน่นอนกว่าอย่างใดอย่างหนึ่งเดี่ยวๆ
    """
    if now >= window.resets_at:
        # หน้าต่างหมุนไปแล้ว ค่าที่แคชไว้เป็นของหน้าต่างเก่า
        if last_activity is None or last_activity < window.resets_at:
            return CONFIRMED_ZERO
        return UNSURE
    if last_activity is not None and last_activity > fetched_at:
        return LOWER_BOUND
    return VALID
```

- [ ] **Step 4: รัน test ให้ผ่าน**

```bash
python3 -m unittest discover -s engine/tests -v
```

Expected: PASS ทั้งหมด (15 จาก task นี้ + 12 จาก task 2)

- [ ] **Step 5: ตรวจกับข้อมูลจริง**

```bash
python3 -c "
import sys, os; sys.path.insert(0, 'engine')
from datetime import datetime, timezone
from aiusage import utilization as u
for name, d in [('default', os.path.expanduser('~/.claude')),
                ('mooz', os.path.expanduser('~/.ccs/instances/mooz'))]:
    x = u.read_utilization(d)
    if not x: print(f'{name}: ไม่มีข้อมูล'); continue
    age = (datetime.now(timezone.utc) - x.fetched_at).total_seconds()/60
    print(f'{name}: อายุ {age:.0f} นาที')
    for w in x.windows:
        print(f'   {w.kind:<14} {w.percent:>5.0f}%  {w.severity:<8} scope={w.scope} active={w.is_active}')
"
```

Expected: `default` แสดง session/weekly_all/weekly_scoped พร้อม Fable 100% · `mooz` แสดงอายุระดับพันนาที

- [ ] **Step 6: Commit**

```bash
git add engine/aiusage/utilization.py engine/tests/test_utilization.py
git commit -m "feat(engine): read Anthropic's official utilization cache with staleness reasoning"
```

---

### Task 4: ต่อ utilization เข้า snapshot และเลิกทิ้งบัญชีที่พังเงียบๆ

ตอนนี้ `collect()` ใช้ `except Exception: continue` — บัญชีที่พังจะหายจากรายการโดยไม่มีใครรู้ ซึ่งแย่กว่าการแสดงว่าพัง task นี้เปลี่ยนให้เป็นแถวที่บอกสาเหตุ และเอา % จริงจาก task 3 มาแทนการเดาจาก token

**Files:**
- Modify: `ai-usage.60s.py` — ฟังก์ชัน `claude_account_stats()`, `collect()`, `write_snapshot()`
- Test: `engine/tests/test_collect_contract.py`

**Interfaces:**
- Consumes: `aiusage.utilization.read_utilization`, `window_confidence`, ค่าคงที่ confidence ทั้งสี่
- Produces: ฟิลด์ใหม่ในแต่ละ item ของ `snapshot.json`
  - `pctSource: "official" | null` — `"official"` เมื่อมาจาก `cachedUsageUtilization`
  - `confidence: "zero" | "valid" | "lower_bound" | "unsure" | null`
  - `dataFetchedAt: str | null` — ISO8601 ของ `fetchedAtMs`
  - `severity: "normal" | "warning" | "critical" | null`
  - `activeLimit: str | null` — ชื่อโมเดลของลิมิตที่กำลังบล็อก
  - `error: str | null` — ข้อความสั้นเมื่อบัญชีนั้นอ่านไม่สำเร็จ

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `engine/tests/test_collect_contract.py`:

```python
"""ทดสอบสัญญาของ snapshot.json — ฟิลด์ที่ฝั่ง Swift พึ่งพา

รัน engine จริงกับข้อมูลจริงบนเครื่อง แล้วตรวจว่าโครงสร้างถูกต้อง
ไม่ตรวจค่าตัวเลข เพราะมันเปลี่ยนตลอด
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SCRIPT = os.path.abspath(os.path.join(ROOT, "ai-usage.60s.py"))


class SnapshotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run([sys.executable, SCRIPT, "--json"],
                             capture_output=True, text=True, timeout=120)
        cls.data = json.loads(out.stdout)

    def test_has_generated_and_items(self):
        self.assertIn("generated", self.data)
        self.assertIsInstance(self.data["items"], list)

    def test_every_item_declares_all_contract_fields(self):
        required = ("group", "label", "pct", "pctSource", "confidence",
                    "dataFetchedAt", "severity", "activeLimit", "error")
        for item in self.data["items"]:
            for field in required:
                self.assertIn(field, item, f"{item.get('label')} ขาดฟิลด์ {field}")

    def test_at_least_one_claude_account_has_official_pct(self):
        official = [i for i in self.data["items"] if i.get("pctSource") == "official"]
        self.assertTrue(official, "ไม่มีบัญชีไหนได้ % ทางการเลย")

    def test_official_items_carry_a_fetch_timestamp(self):
        for i in self.data["items"]:
            if i.get("pctSource") == "official":
                self.assertIsNotNone(i["dataFetchedAt"], i["label"])

    def test_confidence_values_are_from_the_known_set(self):
        allowed = {"zero", "valid", "lower_bound", "unsure", None}
        for i in self.data["items"]:
            self.assertIn(i.get("confidence"), allowed, i.get("label"))

    def test_error_rows_still_carry_a_label(self):
        for i in self.data["items"]:
            if i.get("error"):
                self.assertTrue(i.get("label"), "แถว error ต้องบอกว่าเป็นบัญชีไหน")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
python3 -m unittest engine.tests.test_collect_contract -v 2>&1 | tail -20
```

หรือถ้า discover ง่ายกว่า:

```bash
python3 -m unittest discover -s engine/tests -p "test_collect_contract.py" -v
```

Expected: FAIL — `ขาดฟิลด์ pctSource`

- [ ] **Step 3: ให้ engine หา engine/ เจอ และดึง utilization เข้ามา**

ใน `ai-usage.60s.py` เพิ่มหลังบล็อก import เดิม (ก่อนบรรทัดที่นิยาม `BLOCK_HOURS`):

```python
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine"))
from aiusage import utilization as _util  # noqa: E402
from aiusage import buckets as _buckets  # noqa: E402
```

แก้ `claude_account_stats()` เพิ่ม 2 คีย์ลงใน dict `out` (ห้ามแตะบรรทัดอื่นในฟังก์ชัน):

```python
        "utilization": _util.read_utilization(acc["dir"]),
        "lastActivity": entries[-1][0] if entries else None,
```

- [ ] **Step 4: แทนที่ลูป Claude ใน collect() ทั้งบล็อก**

หาบล็อกที่ขึ้นต้นด้วย `for acc in cfg.get("claude", []):` แล้วแทนทั้งบล็อกจนถึงก่อน `for c in cfg.get("codex", []):` ด้วย:

```python
    now = now_utc()
    for acc in cfg.get("claude", []):
        if not acc.get("enabled", True):
            continue
        try:
            st = claude_account_stats(acc)
        except Exception as e:  # noqa: BLE001 — บัญชีที่พังต้องเห็นบนจอ ไม่ใช่หายไปเฉยๆ
            items.append({
                "group": "Claude Code", "label": acc["label"], "window": "5 ชม.",
                "pct": None, "pctEstimated": False, "pctSource": None,
                "confidence": None, "dataFetchedAt": None, "severity": None,
                "activeLimit": None, "error": ("%s: %s" % (type(e).__name__, e))[:120],
                "tokens": 0, "cost": 0.0, "calls": 0, "resetAt": None,
                "weekTokens": 0, "weekCost": 0.0, "weekPct": None,
                "profile": acc.get("profile"), "plan": None,
            })
            continue

        blk, wk = st["block"], st["week"]
        util = st.get("utilization")
        pct = week_pct = None
        pct_source = confidence = fetched_at = severity = active_limit = None
        reset_at = blk["end"] if blk else None

        if util:
            fetched_at = util.fetched_at.isoformat().replace("+00:00", "Z")
            last_act = st.get("lastActivity")
            session = next((w for w in util.windows if w.kind == "session"), None)
            weekly = max((w for w in util.windows if w.kind.startswith("weekly")),
                         key=lambda w: w.percent, default=None)
            active = next((w for w in util.windows if w.is_active), None)
            if active is not None:
                severity = active.severity
                active_limit = active.scope or active.kind
            elif weekly is not None:
                severity = weekly.severity
            if session is not None:
                confidence = _util.window_confidence(session, util.fetched_at, last_act, now)
                pct = 0.0 if confidence == _util.CONFIRMED_ZERO else session.percent
                if confidence == _util.UNSURE:
                    pct = None
                pct_source = "official" if pct is not None else None
                reset_at = session.resets_at
            if weekly is not None:
                wc = _util.window_confidence(weekly, util.fetched_at, last_act, now)
                week_pct = 0.0 if wc == _util.CONFIRMED_ZERO else weekly.percent
                if wc == _util.UNSURE:
                    week_pct = None

        items.append({
            "group": "Claude Code",
            "label": acc["label"],
            "window": "5 ชม.",
            "pct": round(pct, 1) if pct is not None else None,
            "pctEstimated": False,
            "pctSource": pct_source,
            "confidence": confidence,
            "dataFetchedAt": fetched_at,
            "severity": severity,
            "activeLimit": active_limit,
            "error": None,
            "tokens": blk["tokens"] if blk else 0,
            "cost": round(blk["cost"], 2) if blk else 0.0,
            "calls": blk["calls"] if blk else 0,
            "resetAt": reset_at.isoformat().replace("+00:00", "Z") if reset_at else None,
            "weekTokens": wk["tokens"],
            "weekCost": round(wk["cost"], 2),
            "weekPct": round(week_pct, 1) if week_pct is not None else None,
            "profile": acc.get("profile"),
            "plan": st.get("plan"),
        })
```

`budget5h` / `budget5hAuto` หายไปจากแถว Claude โดยตั้งใจ — % ทางการแทนที่การปรับเทียบทั้งหมดแล้ว ฟังก์ชัน `calibrate_budget5h()` ยังอยู่ในไฟล์เพราะแผน 2 จะเอาไปใช้กับ GLM

- [ ] **Step 5: เติมฟิลด์ใหม่ให้แถวที่ไม่ใช่ Claude**

แถว Codex และแถวอื่นต้องมีฟิลด์ครบชุดเดียวกัน ไม่งั้นฝั่ง Swift ต้องเขียนโค้ดสองแบบ เพิ่มฟังก์ชันช่วยก่อน `def collect():`

```python
CONTRACT_DEFAULTS = {
    "pctSource": None, "confidence": None, "dataFetchedAt": None,
    "severity": None, "activeLimit": None, "error": None,
}


def with_contract(item):
    """เติมฟิลด์ตามสัญญาที่ยังไม่มี ให้ทุกแถวมีรูปร่างเดียวกัน"""
    for k, v in CONTRACT_DEFAULTS.items():
        item.setdefault(k, v)
    return item
```

แล้วที่ท้าย `collect()` ก่อน `return` ให้ครอบทุก item:

```python
    items = [with_contract(i) for i in items]
```

- [ ] **Step 6: ห้ามเขียนทับ snapshot ด้วยผลลัพธ์ว่าง**

แทนที่ `write_snapshot()` ทั้งฟังก์ชัน:

```python
def write_snapshot(path=None):
    target = path or SNAPSHOT_PATH
    data = collect()
    if not data["items"]:
        old = read_json(target, None)
        if old and old.get("items"):
            # รอบนี้ไม่ได้อะไรเลย แต่ของเดิมมีข้อมูล — เก็บของเดิมไว้ดีกว่าลบทิ้ง
            return old
    write_json(target, data)
    return data
```

- [ ] **Step 7: รัน test ให้ผ่าน**

```bash
python3 -m unittest discover -s engine/tests -v
```

Expected: PASS ทั้งหมด

- [ ] **Step 8: ดูผลจริง**

```bash
python3 ai-usage.60s.py --json | python3 -c "
import sys, json
for i in json.load(sys.stdin)['items']:
    print(f\"{i['label']:<12} pct={str(i['pct']):>6} week={str(i['weekPct']):>6} \"
          f\"src={i['pctSource']} conf={i['confidence']} sev={i['severity']} \"
          f\"active={i['activeLimit']} err={i['error']}\")
"
```

Expected: `default` ได้ `pct` และ `weekPct` เป็นตัวเลขจริง `src=official` และ `active=Fable` · `mooz` ได้ `conf=zero` `pct=0.0`

- [ ] **Step 9: Commit**

```bash
git add ai-usage.60s.py engine/tests/test_collect_contract.py
git commit -m "feat(engine): use official utilization for pct, surface broken accounts as rows"
```

---

### Task 5: แยกแถวตาม (บัญชี × ถัง)

บัญชี `default` มี 3 ถังปนกันอยู่ในโฟลเดอร์เดียว (Anthropic · z.ai · Qwen Cloud) เพราะ ccs สลับแค่ endpoint แต่เขียน transcript ที่เดิม แถวเดียวต่อบัญชีจึงรวมโควตาที่คนละที่บังคับเข้าด้วยกัน

**Files:**
- Modify: `ai-usage.60s.py` — เพิ่ม `bucket_rows()` และเรียกใน `collect()`
- Test: `engine/tests/test_bucket_rows.py`

**Interfaces:**
- Consumes: `aiusage.buckets.load_bucket_table`, `bucket_for_model`, `ANTHROPIC`; ฟังก์ชันเดิม `claude_entries`, `summarize`, `current_block`
- Produces: `bucket_rows(acc, table) -> list[dict]` — แถวเพิ่มเติมสำหรับถังที่ไม่ใช่ Anthropic ใช้ `group` = ชื่อถัง และ `label` = ชื่อบัญชี

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `engine/tests/test_bucket_rows.py`:

```python
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "ai-usage.60s.py")


class BucketRowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run([sys.executable, SCRIPT, "--json"],
                             capture_output=True, text=True, timeout=180)
        cls.items = json.loads(out.stdout)["items"]

    def test_non_anthropic_traffic_gets_its_own_row(self):
        """default ยิง glm-5.2 และ qwen/deepseek — ต้องไม่รวมอยู่ในแถว Claude"""
        groups = {i["group"] for i in self.items}
        self.assertTrue(
            {"GLM", "Qwen Cloud"} & groups,
            f"ไม่เห็นถังที่ไม่ใช่ Anthropic เลย เห็นแต่ {groups}")

    def test_bucket_rows_are_keyed_by_account_and_bucket(self):
        ids = [(i["group"], i["label"]) for i in self.items]
        self.assertEqual(len(ids), len(set(ids)), f"มีแถวซ้ำ: {ids}")

    def test_local_buckets_have_no_percentage(self):
        """spark วิ่งบน LAN ไม่มีโควตา จะโชว์ % ไม่ได้"""
        for i in self.items:
            if i.get("local"):
                self.assertIsNone(i["pct"], i["label"])

    def test_bucket_rows_satisfy_the_same_contract(self):
        required = ("group", "label", "pct", "pctSource", "confidence",
                    "dataFetchedAt", "severity", "activeLimit", "error")
        for i in self.items:
            for f in required:
                self.assertIn(f, i, f"{i.get('group')}/{i.get('label')} ขาด {f}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
python3 -m unittest discover -s engine/tests -p "test_bucket_rows.py" -v
```

Expected: FAIL — `ไม่เห็นถังที่ไม่ใช่ Anthropic เลย`

- [ ] **Step 3: เขียน bucket_rows()**

เพิ่มใน `ai-usage.60s.py` ก่อน `def collect():`

```python
def bucket_rows(acc, table):
    """แยก traffic ของบัญชีนี้ตามถังโควตา คืนเฉพาะถังที่ไม่ใช่ Anthropic

    ถัง Anthropic ถูกจัดการโดยลูปหลักของ collect() ซึ่งมี % ทางการอยู่แล้ว
    ที่เหลือยังไม่มีแหล่ง % จริง จึงแสดง token ดิบกับเวลารีเซ็ตตรงๆ
    """
    since = now_utc() - timedelta(days=WEEK_DAYS)
    entries = claude_entries(acc["dir"], since)
    grouped = {}
    for row in entries:
        b = _buckets.bucket_for_model(row[2], table)
        if b.key == _buckets.ANTHROPIC.key:
            continue
        grouped.setdefault(b, []).append(row)

    out = []
    for b, rows in sorted(grouped.items(), key=lambda kv: kv[0].name):
        wk = summarize(rows)
        blk = current_block(rows)
        s = summarize(blk["entries"]) if blk else None
        out.append(with_contract({
            "group": b.name,
            "label": acc["label"],
            "window": "5 ชม.",
            "local": b.local,
            "pct": None,          # ยังไม่มีแหล่ง % จริงของถังพวกนี้ — แผน 2
            "pctEstimated": False,
            "tokens": s["tokens"] if s else 0,
            "cost": round(s["cost"], 2) if s else 0.0,
            "calls": s["calls"] if s else 0,
            "resetAt": blk["end"].isoformat().replace("+00:00", "Z") if blk else None,
            "weekTokens": wk["tokens"],
            "weekCost": round(wk["cost"], 2),
            "weekPct": None,
            "profile": acc.get("profile"),
            "plan": None,
        }))
    return out
```

- [ ] **Step 4: เรียกใน collect()**

ใน `collect()` เพิ่มก่อนบรรทัด `for acc in cfg.get("claude", []):`

```python
    bucket_table = _buckets.load_bucket_table()
```

แล้วในลูป Claude หลังจาก `items.append({...})` ของกรณีสำเร็จ (ไม่ใช่กรณี error) เพิ่ม:

```python
        try:
            items.extend(bucket_rows(acc, bucket_table))
        except Exception:  # noqa: BLE001 — ถังเสริมพังต้องไม่ทำให้แถวหลักหาย
            pass
```

- [ ] **Step 5: ให้ทุกแถวมีคีย์ local**

เพิ่ม `"local": False` เข้าไปใน `CONTRACT_DEFAULTS` ที่สร้างไว้ใน task 4:

```python
CONTRACT_DEFAULTS = {
    "pctSource": None, "confidence": None, "dataFetchedAt": None,
    "severity": None, "activeLimit": None, "error": None, "local": False,
}
```

และเพิ่ม `"local"` เข้าไปในทูเพิล `required` ของ test ทั้งสองไฟล์ (`test_collect_contract.py` และ `test_bucket_rows.py`)

- [ ] **Step 6: รัน test ให้ผ่าน**

```bash
python3 -m unittest discover -s engine/tests -v
```

Expected: PASS ทั้งหมด

- [ ] **Step 7: ดูผลจริง**

```bash
python3 ai-usage.60s.py --json | python3 -c "
import sys, json
for i in json.load(sys.stdin)['items']:
    print(f\"{i['group']:<14} {i['label']:<10} pct={str(i['pct']):>6} tok={i['tokens']:>10,} local={i.get('local')}\")
"
```

Expected: เห็นแถว `GLM / default` และ `Qwen Cloud / default` แยกจาก `Claude Code / default`

- [ ] **Step 8: Commit**

```bash
git add ai-usage.60s.py engine/tests/
git commit -m "feat(engine): split rows by (account x quota bucket)"
```

---

### Task 6: สองสัญญาณ — engine ยังรันไหม กับ ตัวเลขถูกไหม

แยกเป็นฟังก์ชันบริสุทธิ์ก่อนแตะ UI เพราะนี่คือสิ่งที่กันไม่ให้แอปโกหก และมันมี**สองคำถามที่ต่างกัน**ซึ่งง่ายมากที่จะเผลอรวมเป็นอันเดียว

วัดจริงแล้ว: ระหว่างใช้ Claude Code หนักต่อเนื่อง 29 นาที `fetchedAtMs` ไม่ขยับเลย (ข้อมูลแก่จาก 3 เป็น 32 นาที) **อายุจึงเป็นสัญญาณที่ผิดสำหรับคุณภาพตัวเลข** — ค่าอายุ 40 ชม. ที่ไม่มีใครใช้ต่อคือถูกเป๊ะ ส่วนค่าอายุ 5 นาทีที่ยิงไป 200 request หลังจากนั้นคือผิดไปแล้ว

| สัญญาณ | มาจาก | ตอบคำถาม |
|---|---|---|
| `Freshness` | `snapshot.generated` — เราสแกนเมื่อไหร่ | engine ยังทำงานอยู่ไหม |
| `Certainty` | `item.confidence` — fetchedAt เทียบ traffic | ตัวเลขนี้ถูกไหม |

**Files:**
- Create: `Shared/Freshness.swift`
- Test: `Tests/FreshnessTests.swift`
- Delete: `Tests/.gitkeep`

**Interfaces:**
- Consumes: ไม่มี
- Produces:
  - `enum Freshness { case fresh, stale, dead }`
  - `func freshness(snapshotAge: TimeInterval?, wokeRecently: Bool) -> Freshness`
  - `enum Certainty { case exact, atLeast, unknown }`
  - `func certainty(confidence: String?) -> Certainty`
  - `func ageText(_ seconds: TimeInterval) -> String` — คืน `"18m"` / `"2h"` / `"3d"`
  - ค่าคงที่ `freshLimit: TimeInterval = 180`, `staleLimit: TimeInterval = 1800`, `wakeGrace: TimeInterval = 90`

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `Tests/FreshnessTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class FreshnessTests: XCTestCase {

    func testFreshWithinThreeMinutes() {
        XCTAssertEqual(freshness(snapshotAge: 0, wokeRecently: false), .fresh)
        XCTAssertEqual(freshness(snapshotAge: 179, wokeRecently: false), .fresh)
    }

    func testStaleBetweenThreeAndThirtyMinutes() {
        XCTAssertEqual(freshness(snapshotAge: 181, wokeRecently: false), .stale)
        XCTAssertEqual(freshness(snapshotAge: 1799, wokeRecently: false), .stale)
    }

    func testDeadPastThirtyMinutes() {
        XCTAssertEqual(freshness(snapshotAge: 1801, wokeRecently: false), .dead)
        XCTAssertEqual(freshness(snapshotAge: 40 * 3600, wokeRecently: false), .dead)
    }

    func testMissingAgeIsDead() {
        XCTAssertEqual(freshness(snapshotAge: nil, wokeRecently: false), .dead)
    }

    /// ปิดฝาข้ามคืน ตื่นมา snapshot อายุ 8 ชม. แต่จะถูกต้องเองใน 60 วิ
    /// ถ้าไม่ผ่อนผัน ผู้ใช้จะเจอ "ตาย" ทุกเช้าจนเลิกเชื่อสถานะนี้
    func testRecentWakeSuppressesStaleness() {
        XCTAssertEqual(freshness(snapshotAge: 8 * 3600, wokeRecently: true), .fresh)
    }

    func testWakeGraceDoesNotHideMissingData() {
        XCTAssertEqual(freshness(snapshotAge: nil, wokeRecently: true), .dead)
    }

    // MARK: - Certainty

    func testValidAndZeroAreExact() {
        XCTAssertEqual(certainty(confidence: "valid"), .exact)
        XCTAssertEqual(certainty(confidence: "zero"), .exact)
    }

    /// สถานะปกติระหว่างทำงาน ไม่ใช่กรณีขอบ — วัดแล้วเป็นแบบนี้ตลอด 29 นาที
    func testLowerBoundMeansAtLeast() {
        XCTAssertEqual(certainty(confidence: "lower_bound"), .atLeast)
    }

    func testUnsureAndMissingAreUnknown() {
        XCTAssertEqual(certainty(confidence: "unsure"), .unknown)
        XCTAssertEqual(certainty(confidence: nil), .unknown)
        XCTAssertEqual(certainty(confidence: "something-new"), .unknown)
    }

    /// อายุห้ามมีผลกับ certainty — ค่าอายุ 40 ชม. ที่เงียบสนิทคือถูกเป๊ะ
    func testCertaintyIgnoresAgeEntirely() {
        XCTAssertEqual(certainty(confidence: "valid"), .exact)
        XCTAssertEqual(certainty(confidence: "zero"), .exact)
    }

    func testAgeTextUsesCompactUnits() {
        XCTAssertEqual(ageText(45), "45s")
        XCTAssertEqual(ageText(18 * 60), "18m")
        XCTAssertEqual(ageText(2 * 3600), "2h")
        XCTAssertEqual(ageText(40 * 3600), "1d")
        XCTAssertEqual(ageText(3 * 86400), "3d")
    }

    func testAgeTextStaysWithinFourCharacters() {
        for seconds in [0.0, 59, 60, 3599, 3600, 86_399, 86_400, 900_000] {
            XCTAssertLessThanOrEqual(ageText(seconds).count, 4, "\(seconds)")
        }
    }
}
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
rm -f Tests/.gitkeep
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: FAIL — `cannot find 'freshness' in scope`

- [ ] **Step 3: เขียน implementation**

สร้าง `Shared/Freshness.swift`:

```swift
import Foundation

/// เกณฑ์อายุ *snapshot* — engine ยิงทุก 60 วิ 3 นาทีจึงเผื่อพลาดได้ 2 รอบก่อนเตือน
let freshLimit: TimeInterval = 180
let staleLimit: TimeInterval = 1800
/// หลังเครื่องตื่น snapshot จะถูกต้องเองภายในรอบถัดไป อย่าเพิ่งตกใจ
let wakeGrace: TimeInterval = 90

/// engine ยังทำงานอยู่ไหม — วัดจาก snapshot.generated ซึ่งอัปเดตทุก 60 วิจริง
enum Freshness {
    case fresh   // engine รันอยู่
    case stale   // พลาดไปหลายรอบ ควรบอกอายุ
    case dead    // หยุดไปแล้ว ห้ามแสดงตัวเลข
}

/// ตัวเลขนี้ถูกไหม — คนละคำถามกับ Freshness
///
/// ห้ามใช้อายุตัดสิน: `cachedUsageUtilization` ไม่ refresh ระหว่างเซสชัน (วัดแล้ว
/// ใช้งานหนัก 29 นาที fetchedAtMs ไม่ขยับเลย) ค่าอายุ 40 ชม. ที่เงียบสนิทคือถูกเป๊ะ
/// ส่วนค่าอายุ 5 นาทีที่ยิงไป 200 request หลังจากนั้นคือผิดไปแล้ว
/// engine คำนวณให้แล้วใน window_confidence() — ที่นี่แค่แปลงเป็นวิธีแสดงผล
enum Certainty {
    case exact     // ตรงตามนี้
    case atLeast   // อย่างน้อยเท่านี้ ของจริงสูงกว่า
    case unknown   // ไม่รู้ ห้ามแสดงตัวเลข
}

/// - Parameters:
///   - snapshotAge: อายุของ snapshot.generated เป็นวินาที · nil = ไม่มีไฟล์
///   - wokeRecently: เครื่องเพิ่งตื่นภายใน wakeGrace วินาที
func freshness(snapshotAge: TimeInterval?, wokeRecently: Bool) -> Freshness {
    guard let age = snapshotAge else { return .dead }
    if wokeRecently { return .fresh }
    if age < freshLimit { return .fresh }
    if age < staleLimit { return .stale }
    return .dead
}

func certainty(confidence: String?) -> Certainty {
    switch confidence {
    case "valid", "zero": return .exact
    case "lower_bound": return .atLeast
    default: return .unknown
    }
}

/// อายุแบบสั้นที่สุดที่ยังอ่านรู้เรื่อง — ต้องไม่เกิน 4 ตัวอักษรเพราะแถบ menu bar แคบ
func ageText(_ seconds: TimeInterval) -> String {
    let s = max(0, Int(seconds))
    if s < 60 { return "\(s)s" }
    if s < 3600 { return "\(s / 60)m" }
    if s < 86_400 { return "\(s / 3600)h" }
    return "\(s / 86_400)d"
}
```

- [ ] **Step 4: รัน test ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: `** TEST SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add Shared/Freshness.swift Tests/FreshnessTests.swift project.yml
git commit -m "feat(app): freshness classification with wake grace period"
```

---

### Task 7: ขยายโมเดล Swift ให้ตรงกับสัญญาใหม่

`UsageSnapshot.swift` ยังเป็นของยุค WidgetKit — ไม่มีฟิลด์ที่ task 4–5 เพิ่มเข้ามา และ `isStale` ยังใช้ `generated` ซึ่งบอกแค่ว่าเราสแกนเมื่อไหร่ ไม่ได้บอกว่าตัวเลขเก่าแค่ไหน

**Files:**
- Modify: `Shared/UsageSnapshot.swift`
- Test: `Tests/UsageSnapshotTests.swift`

**Interfaces:**
- Consumes: `Freshness`, `Certainty`, `freshness(snapshotAge:wokeRecently:)`, `certainty(confidence:)` จาก task 6
- Produces:
  - `UsageItem` เพิ่ม: `pctSource: String?`, `confidence: String?`, `dataFetchedAt: Date?`, `severity: String?`, `activeLimit: String?`, `error: String?`, `local: Bool?`
  - `UsageItem.dataAge(now:) -> TimeInterval?`
  - `UsageItem.isOfficial: Bool`
  - `UsageSnapshot.decode(from data: Data) -> UsageSnapshot?`

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `Tests/UsageSnapshotTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class UsageSnapshotTests: XCTestCase {

    let json = """
    {
      "generated": "2026-08-07T06:40:00Z",
      "items": [
        {
          "group": "Claude Code", "label": "default", "window": "5 ชม.",
          "pct": 5.0, "pctEstimated": false, "pctSource": "official",
          "confidence": "valid", "dataFetchedAt": "2026-08-07T06:38:06Z",
          "severity": "critical", "activeLimit": "Fable", "error": null,
          "local": false, "tokens": 123456, "cost": 1.5, "calls": 20,
          "resetAt": "2026-08-07T07:10:00Z", "weekTokens": 999,
          "weekCost": 9.9, "weekPct": 96.0, "profile": null, "plan": "Max 20x"
        },
        {
          "group": "Claude Code", "label": "work", "window": "5 ชม.",
          "pct": null, "pctEstimated": false, "pctSource": null,
          "confidence": null, "dataFetchedAt": null, "severity": null,
          "activeLimit": null, "error": "OSError: permission denied",
          "local": false, "tokens": 0, "cost": 0, "calls": 0,
          "resetAt": null, "weekTokens": 0, "weekCost": 0,
          "weekPct": null, "profile": null, "plan": null
        }
      ]
    }
    """.data(using: .utf8)!

    func testDecodesAllContractFields() throws {
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: json))
        XCTAssertEqual(snap.items.count, 2)
        let first = snap.items[0]
        XCTAssertEqual(first.pctSource, "official")
        XCTAssertEqual(first.confidence, "valid")
        XCTAssertEqual(first.severity, "critical")
        XCTAssertEqual(first.activeLimit, "Fable")
        XCTAssertNotNil(first.dataFetchedAt)
    }

    func testErrorRowSurvivesDecoding() throws {
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: json))
        XCTAssertEqual(snap.items[1].error, "OSError: permission denied")
        XCTAssertNil(snap.items[1].pct)
    }

    func testDataAgeUsesFetchTimeNotGenerated() throws {
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: json))
        let now = ISO8601DateFormatter().date(from: "2026-08-07T06:48:06Z")!
        XCTAssertEqual(snap.items[0].dataAge(now: now) ?? 0, 600, accuracy: 1)
    }

    func testDataAgeIsNilWhenNeverFetched() throws {
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: json))
        XCTAssertNil(snap.items[1].dataAge(now: Date()))
    }

    func testIsOfficialOnlyWhenSourceSaysSo() throws {
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: json))
        XCTAssertTrue(snap.items[0].isOfficial)
        XCTAssertFalse(snap.items[1].isOfficial)
    }

    func testDecodingGarbageReturnsNil() {
        XCTAssertNil(UsageSnapshot.decode(from: Data("not json".utf8)))
    }
}
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: FAIL — `value of type 'UsageItem' has no member 'pctSource'`

- [ ] **Step 3: เขียนทับ Shared/UsageSnapshot.swift**

```swift
import Foundation
import SwiftUI

// อ่านไฟล์ที่ ai-usage.60s.py --snapshot เขียนไว้
// ต้องปิด App Sandbox ไม่งั้น NSHomeDirectory() จะชี้ไป container แล้วหาไฟล์ไม่เจอ

struct UsageItem: Codable, Identifiable, Hashable {
    var group: String
    var label: String
    var window: String
    var pct: Double?
    var tokens: Int
    var cost: Double
    var calls: Int
    var resetAt: Date?
    var weekTokens: Int
    var weekCost: Double
    var weekPct: Double?
    var profile: String?
    var plan: String?

    // สัญญาใหม่จาก engine
    var pctSource: String?      // "official" = ตัวเลขจาก Anthropic โดยตรง
    var confidence: String?     // zero | valid | lower_bound | unsure
    var dataFetchedAt: Date?    // เวลาที่ต้นทางให้ตัวเลขนี้มา
    var severity: String?       // normal | warning | critical
    var activeLimit: String?    // ลิมิตที่กำลังบล็อกอยู่
    var error: String?          // บัญชีนี้อ่านไม่สำเร็จเพราะอะไร
    var local: Bool?            // ถังที่รันในเครือข่ายตัวเอง ไม่มีโควตา

    var id: String { "\(group)/\(label)" }

    var isOfficial: Bool { pctSource == "official" }

    /// อายุของ *ตัวเลขต้นทาง* ไม่ใช่อายุของ snapshot
    /// snapshot สดไม่ได้แปลว่าตัวเลขข้างในสด — mooz เคยเก่า 40 ชม.
    func dataAge(now: Date) -> TimeInterval? {
        guard let fetched = dataFetchedAt else { return nil }
        return now.timeIntervalSince(fetched)
    }

    var tokensText: String {
        if tokens >= 1_000_000 { return String(format: "%.2fM", Double(tokens) / 1_000_000) }
        if tokens >= 1_000 { return String(format: "%.0fk", Double(tokens) / 1_000) }
        return "\(tokens)"
    }

    var tint: Color {
        if error != nil { return .secondary }
        guard let p = pct ?? weekPct else { return .secondary }
        if p >= 90 { return Color(red: 0.90, green: 0.33, blue: 0.29) }
        if p >= 70 { return Color(red: 0.89, green: 0.66, blue: 0.23) }
        return Color(red: 0.30, green: 0.76, blue: 0.54)
    }
}

struct UsageSnapshot: Codable {
    var generated: Date
    var items: [UsageItem]

    static let empty = UsageSnapshot(generated: .distantPast, items: [])

    static var fileURL: URL {
        URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Application Support/AIUsage/snapshot.json")
    }

    static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .custom { decoder in
            let raw = try decoder.singleValueContainer().decode(String.self)
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let d = iso.date(from: raw) { return d }
            iso.formatOptions = [.withInternetDateTime]
            return iso.date(from: raw) ?? Date()
        }
        return dec
    }

    static func decode(from data: Data) -> UsageSnapshot? {
        try? decoder().decode(UsageSnapshot.self, from: data)
    }

    static func load() -> UsageSnapshot {
        guard let data = try? Data(contentsOf: fileURL) else { return .empty }
        return decode(from: data) ?? .empty
    }

    /// แถวที่ควรขึ้นแถบ menu bar — เอาตัวที่ % สูงสุดในบรรดาที่วัดได้จริง
    var worst: UsageItem? {
        items.filter { $0.error == nil && ($0.pct ?? $0.weekPct) != nil }
            .max { ($0.pct ?? $0.weekPct ?? 0) < ($1.pct ?? $1.weekPct ?? 0) }
    }
}

func countdownText(to date: Date?, from now: Date) -> String {
    guard let date else { return "—" }
    let secs = Int(date.timeIntervalSince(now))
    if secs <= 0 { return "รีเซ็ตแล้ว" }
    let d = secs / 86400, h = (secs % 86400) / 3600, m = (secs % 3600) / 60
    if d > 0 { return "\(d)วัน \(h)ชม." }
    if h > 0 { return "\(h)ชม. \(m)น." }
    return "\(m)น."
}
```

- [ ] **Step 4: รัน test ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: `** TEST SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add Shared/UsageSnapshot.swift Tests/UsageSnapshotTests.swift
git commit -m "feat(app): extend snapshot model for official pct, confidence and errors"
```

---

### Task 8: ตัวเรียก engine แทน launchd

launchd เป็นชิ้นส่วนที่พังได้โดยที่แอปไม่มีทางรู้สาเหตุ ต้องเดาจากอายุไฟล์ ถ้าแอปเรียก `Process` เองจะได้ exit code กับ stderr ทันที และถ้าแอปไม่รัน ผู้ใช้ก็เห็นเองว่าไอคอนหายไป ไม่ใช่การโกหกเงียบ

**Files:**
- Create: `App/EngineRunner.swift`
- Test: `Tests/EngineRunnerTests.swift`

**Interfaces:**
- Consumes: ไม่มี
- Produces:
  - `final class EngineRunner` — `init(scriptURL: URL)`, `var isRunning: Bool`, `var lastError: String?`
  - `func run(completion: @escaping (Result<Void, EngineError>) -> Void)` — ไม่เริ่มรอบใหม่ถ้ารอบเก่ายังไม่จบ
  - `enum EngineError: Error { case alreadyRunning, timedOut, failed(code: Int32, stderr: String) }`
  - `static var bundledScriptURL: URL?` — หา `ai-usage.60s.py` ใน bundle resources
  - ค่าคงที่ `engineTimeout: TimeInterval = 45`

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `Tests/EngineRunnerTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class EngineRunnerTests: XCTestCase {

    /// เขียนสคริปต์ python ชั่วคราวเพื่อจำลองพฤติกรรมของ engine
    private func makeScript(_ body: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("engine-\(UUID().uuidString).py")
        try body.write(to: url, atomically: true, encoding: .utf8)
        return url
    }

    func testSuccessfulRunReportsSuccess() throws {
        let script = try makeScript("print('ok')\n")
        let runner = EngineRunner(scriptURL: script)
        let done = expectation(description: "run")
        runner.run { result in
            if case .failure(let e) = result { XCTFail("\(e)") }
            done.fulfill()
        }
        wait(for: [done], timeout: 20)
        XCTAssertFalse(runner.isRunning)
    }

    func testNonZeroExitIsReportedWithStderr() throws {
        let script = try makeScript("""
        import sys
        sys.stderr.write('boom: path missing')
        sys.exit(3)
        """)
        let runner = EngineRunner(scriptURL: script)
        let done = expectation(description: "run")
        runner.run { result in
            guard case .failure(.failed(let code, let err)) = result else {
                XCTFail("ควรล้มเหลว"); done.fulfill(); return
            }
            XCTAssertEqual(code, 3)
            XCTAssertTrue(err.contains("boom"))
            done.fulfill()
        }
        wait(for: [done], timeout: 20)
        XCTAssertNotNil(runner.lastError)
    }

    /// สแกนที่ค้างต้องไม่กินรอบถัดไปเรื่อยๆ
    func testHangingRunIsKilledAtTimeout() throws {
        let script = try makeScript("import time\ntime.sleep(120)\n")
        let runner = EngineRunner(scriptURL: script, timeout: 2)
        let done = expectation(description: "run")
        runner.run { result in
            guard case .failure(.timedOut) = result else {
                XCTFail("ควร timeout"); done.fulfill(); return
            }
            done.fulfill()
        }
        wait(for: [done], timeout: 20)
        XCTAssertFalse(runner.isRunning)
    }

    func testSecondRunIsRefusedWhileFirstIsInFlight() throws {
        let script = try makeScript("import time\ntime.sleep(3)\n")
        let runner = EngineRunner(scriptURL: script, timeout: 20)
        let first = expectation(description: "first")
        runner.run { _ in first.fulfill() }

        let second = expectation(description: "second")
        runner.run { result in
            guard case .failure(.alreadyRunning) = result else {
                XCTFail("ควรถูกปฏิเสธ"); second.fulfill(); return
            }
            second.fulfill()
        }
        wait(for: [second], timeout: 5)
        wait(for: [first], timeout: 30)
    }

    func testMissingScriptFailsInsteadOfCrashing() {
        let runner = EngineRunner(scriptURL: URL(fileURLWithPath: "/nope/missing.py"))
        let done = expectation(description: "run")
        runner.run { result in
            if case .success = result { XCTFail("ไม่ควรสำเร็จ") }
            done.fulfill()
        }
        wait(for: [done], timeout: 20)
    }
}
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: FAIL — `cannot find 'EngineRunner' in scope`

- [ ] **Step 3: เขียน implementation**

สร้าง `App/EngineRunner.swift`:

```swift
import Foundation

let engineTimeout: TimeInterval = 45

enum EngineError: Error {
    case alreadyRunning
    case timedOut
    case failed(code: Int32, stderr: String)
}

/// เรียก ai-usage.60s.py --snapshot แทน launchd
///
/// เหตุผลที่ไม่ใช้ launchd: plist พังได้โดยที่แอปไม่มีทางรู้สาเหตุ ต้องเดาจากอายุไฟล์
/// เรียกเองแล้วได้ exit code กับ stderr ทันที และถ้าแอปไม่รันผู้ใช้ก็เห็นเองว่าไอคอนหาย
final class EngineRunner {
    private let scriptURL: URL
    private let timeout: TimeInterval
    private let queue = DispatchQueue(label: "com.local.aiusage.engine")
    private var running = false
    private let lock = NSLock()

    private(set) var lastError: String?

    var isRunning: Bool {
        lock.lock(); defer { lock.unlock() }
        return running
    }

    init(scriptURL: URL, timeout: TimeInterval = engineTimeout) {
        self.scriptURL = scriptURL
        self.timeout = timeout
    }

    /// หา engine ที่มากับ bundle — ผูกเวอร์ชันไว้กับแอป ไม่ต้องพึ่ง path ข้างนอก
    static var bundledScriptURL: URL? {
        Bundle.main.url(forResource: "ai-usage.60s", withExtension: "py")
    }

    func run(completion: @escaping (Result<Void, EngineError>) -> Void) {
        lock.lock()
        if running {
            lock.unlock()
            completion(.failure(.alreadyRunning))
            return
        }
        running = true
        lock.unlock()

        queue.async { [weak self] in
            guard let self else { return }
            let result = self.execute()
            self.lock.lock()
            self.running = false
            self.lock.unlock()
            if case .failure(let e) = result {
                self.lastError = Self.describe(e)
            } else {
                self.lastError = nil
            }
            DispatchQueue.main.async { completion(result) }
        }
    }

    private func execute() -> Result<Void, EngineError> {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        proc.arguments = ["python3", scriptURL.path, "--snapshot"]
        let errPipe = Pipe()
        proc.standardError = errPipe
        proc.standardOutput = Pipe()

        do {
            try proc.run()
        } catch {
            return .failure(.failed(code: -1, stderr: error.localizedDescription))
        }

        let deadline = Date().addingTimeInterval(timeout)
        while proc.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.1)
        }
        if proc.isRunning {
            proc.terminate()
            return .failure(.timedOut)
        }

        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = String(data: errData, encoding: .utf8) ?? ""
        if proc.terminationStatus != 0 {
            return .failure(.failed(code: proc.terminationStatus,
                                    stderr: stderr.trimmingCharacters(in: .whitespacesAndNewlines)))
        }
        return .success(())
    }

    static func describe(_ error: EngineError) -> String {
        switch error {
        case .alreadyRunning: return "รอบก่อนยังไม่จบ"
        case .timedOut: return "engine ค้างเกิน \(Int(engineTimeout)) วินาที"
        case .failed(let code, let stderr):
            let line = stderr.split(separator: "\n").last.map(String.init) ?? ""
            return line.isEmpty ? "engine ออกด้วยรหัส \(code)" : line
        }
    }
}
```

- [ ] **Step 4: รัน test ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: `** TEST SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add App/EngineRunner.swift Tests/EngineRunnerTests.swift
git commit -m "feat(app): run engine in-process with timeout and overlap guard"
```

---

### Task 9: แถบ menu bar สองบรรทัด

ผู้ใช้ตีกลับแบบ 22 ตัวอักษรมาแล้ว และขอให้เห็น weekly ด้วย แบบซ้อนสองบรรทัดให้ทั้งสองอย่างโดยไม่กินที่แนวนอน

**Files:**
- Create: `App/MenuBarLabel.swift`
- Modify: `App/AIUsageApp.swift`
- Test: `Tests/MenuBarLabelTests.swift`

**Interfaces:**
- Consumes: `UsageSnapshot`, `UsageItem`, `Freshness`, `Certainty`, `freshness(snapshotAge:wokeRecently:)`, `certainty(confidence:)`, `ageText(_:)`
- Produces:
  - `struct MenuBarText { let top: String; let bottom: String; let dimmed: Bool }`
  - `func menuBarText(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool) -> MenuBarText`

- [ ] **Step 1: เขียน test ที่ยังไม่ผ่าน**

สร้าง `Tests/MenuBarLabelTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class MenuBarLabelTests: XCTestCase {

    private let now = Date()

    private func item(pct: Double?, weekPct: Double?, confidence: String? = "valid",
                      error: String? = nil) -> UsageItem {
        UsageItem(
            group: "Claude Code", label: "default", window: "5 ชม.",
            pct: pct, tokens: 0, cost: 0, calls: 0, resetAt: nil,
            weekTokens: 0, weekCost: 0, weekPct: weekPct, profile: nil, plan: nil,
            pctSource: pct == nil ? nil : "official", confidence: confidence,
            dataFetchedAt: now.addingTimeInterval(-40 * 3600),
            severity: "normal", activeLimit: nil, error: error, local: false)
    }

    /// generatedAgo = อายุของ snapshot ไม่ใช่อายุของตัวเลขต้นทาง
    private func snap(_ items: [UsageItem], generatedAgo: TimeInterval = 30) -> UsageSnapshot {
        UsageSnapshot(generated: now.addingTimeInterval(-generatedAgo), items: items)
    }

    func testExactNumbersShowBothWindows() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96)]),
                            now: now, wokeRecently: false)
        XCTAssertEqual(t.top, "5h   5%")
        XCTAssertEqual(t.bottom, "7d  96%")
        XCTAssertFalse(t.dimmed)
    }

    /// อายุของตัวเลขต้นทางต้องไม่ทำให้แถบตาย — 40 ชม. ที่เงียบสนิทคือถูกเป๊ะ
    func testOldFetchTimeDoesNotKillTheBar() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96, confidence: "zero")]),
                            now: now, wokeRecently: false)
        XCTAssertEqual(t.top, "5h   5%")
        XCTAssertFalse(t.dimmed)
    }

    /// สถานะปกติระหว่างทำงาน — วัดแล้วเป็นแบบนี้ตลอด 29 นาที
    func testLowerBoundIsMarkedWithGreaterOrEqual() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96,
                                                 confidence: "lower_bound")]),
                            now: now, wokeRecently: false)
        XCTAssertEqual(t.top, "5h  ≥5%")
        XCTAssertEqual(t.bottom, "7d ≥96%")
        XCTAssertFalse(t.dimmed)
    }

    func testUnsureShowsNoNumbers() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96, confidence: "unsure")]),
                            now: now, wokeRecently: false)
        XCTAssertTrue(t.top.contains("—"))
        XCTAssertFalse(t.top.contains("5"))
    }

    /// engine หยุดยิง — คนละเรื่องกับตัวเลขเก่า
    func testStaleSnapshotReplacesWeeklyWithAge() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96)], generatedAgo: 18 * 60),
                            now: now, wokeRecently: false)
        XCTAssertEqual(t.top, "5h   5%")
        XCTAssertEqual(t.bottom, "↻ 18m")
        XCTAssertTrue(t.dimmed)
    }

    func testDeadSnapshotShowsNoNumbers() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96)], generatedAgo: 2 * 3600),
                            now: now, wokeRecently: false)
        XCTAssertFalse(t.top.contains("5%"))
        XCTAssertFalse(t.bottom.contains("96"))
        XCTAssertTrue(t.top.contains("—"))
        XCTAssertTrue(t.dimmed)
    }

    func testEmptySnapshotShowsDashes() {
        let t = menuBarText(snapshot: snap([]), now: now, wokeRecently: false)
        XCTAssertTrue(t.top.contains("—"))
        XCTAssertTrue(t.dimmed)
    }

    func testErrorRowsAreNotChosenForTheBar() {
        let t = menuBarText(
            snapshot: snap([item(pct: nil, weekPct: nil, error: "boom"),
                            item(pct: 12, weekPct: 30)]),
            now: now, wokeRecently: false)
        XCTAssertEqual(t.top, "5h  12%")
    }

    func testBothLinesStayWithinTenCharacters() {
        let cases: [(Double?, Double?, String?, TimeInterval)] = [
            (100, 100, "valid", 30),
            (100, 100, "lower_bound", 30),
            (5, 96, "valid", 18 * 60),
            (0, 0, "zero", 2 * 3600),
            (99.9, 99.9, "lower_bound", 5),
        ]
        for (p, w, c, gen) in cases {
            let t = menuBarText(snapshot: snap([item(pct: p, weekPct: w, confidence: c)],
                                               generatedAgo: gen),
                                now: now, wokeRecently: false)
            XCTAssertLessThanOrEqual(t.top.count, 10, t.top)
            XCTAssertLessThanOrEqual(t.bottom.count, 10, t.bottom)
        }
    }

    func testWakeGraceKeepsNumbersVisible() {
        let t = menuBarText(snapshot: snap([item(pct: 5, weekPct: 96)],
                                           generatedAgo: 8 * 3600),
                            now: now, wokeRecently: true)
        XCTAssertEqual(t.bottom, "7d  96%")
        XCTAssertFalse(t.dimmed)
    }
}
```

- [ ] **Step 2: รัน test ให้เห็นว่าพัง**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: FAIL — `cannot find 'menuBarText' in scope`

- [ ] **Step 3: เขียน implementation**

สร้าง `App/MenuBarLabel.swift`:

```swift
import Foundation

struct MenuBarText: Equatable {
    let top: String
    let bottom: String
    let dimmed: Bool
}

/// ข้อความบนแถบ menu bar — ไม่เกิน 10 ตัวอักษรต่อบรรทัด
///
/// สองสัญญาณคุมคนละส่วน:
/// - Freshness (จาก snapshot.generated) → engine หยุดไหม · คุมการหรี่และตัว ↻
/// - Certainty (จาก item.confidence)    → ตัวเลขถูกไหม · คุมเครื่องหมาย ≥
///
/// ตอน engine หยุด บรรทัดล่างเปลี่ยนจาก weekly เป็นอายุ เพราะคำถามที่ผู้ใช้ต้องการ
/// คำตอบเปลี่ยนไป และเป็นการเปลี่ยนรูปร่าง ไม่ใช่แค่หรี่สี จึงยังอ่านได้สำหรับคนตาบอดสี
func menuBarText(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool) -> MenuBarText {
    let snapAge = snapshot.generated == .distantPast
        ? nil : now.timeIntervalSince(snapshot.generated)
    let state = freshness(snapshotAge: snapAge, wokeRecently: wokeRecently)
    let age = snapAge.map(ageText) ?? "—"

    guard let item = snapshot.worst else {
        return MenuBarText(top: "5h    —", bottom: "7d    —", dimmed: true)
    }
    if state == .dead {
        return MenuBarText(top: "5h    —", bottom: "↻ \(age)", dimmed: true)
    }

    let sure = certainty(confidence: item.confidence)
    let top = pctLine("5h", item.pct, sure)
    if state == .stale {
        return MenuBarText(top: top, bottom: "↻ \(age)", dimmed: true)
    }
    return MenuBarText(top: top, bottom: pctLine("7d", item.weekPct, sure), dimmed: false)
}

private func pctLine(_ prefix: String, _ pct: Double?, _ sure: Certainty) -> String {
    guard let pct, sure != .unknown else { return "\(prefix)    —" }
    let n = Int(pct.rounded())
    // ≥ บอกว่าของจริงสูงกว่านี้ — ซื่อสัตย์กว่าการโชว์เลขเปล่าที่รู้ว่าต่ำไป
    let body = sure == .atLeast ? "≥\(n)%" : "\(n)%"
    // จัดชิดขวาให้กว้าง 7 เท่ากันทุกบรรทัด ตัวเลขจะได้ไม่กระโดดตอนค่าเปลี่ยนหลัก
    return prefix + String(repeating: " ", count: max(1, 7 - prefix.count - body.count)) + body
}
```

- [ ] **Step 4: รัน test ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' \
  test 2>&1 | tail -20
```

Expected: `** TEST SUCCEEDED **` — ถ้าช่องว่างไม่ตรง ให้ปรับ format string ให้ตรงกับที่ test คาด อย่าแก้ test

- [ ] **Step 5: Commit**

```bash
git add App/MenuBarLabel.swift Tests/MenuBarLabelTests.swift
git commit -m "feat(app): two-line menu bar label with honest staleness"
```

---

### Task 10: ต่อ NSStatusItem กับ popover เข้าด้วยกัน

`AppDelegate` อ้างถึง `PopoverView` สองไฟล์นี้จึงต้องเกิดพร้อมกัน ไม่งั้น task ก่อนหน้าจะทิ้ง tree ที่ build ไม่ผ่าน

**Files:**
- Create: `App/PopoverView.swift`
- Modify: `App/AIUsageApp.swift`

**Interfaces:**
- Consumes: `UsageSnapshot`, `menuBarText(snapshot:now:wokeRecently:)`, `EngineRunner`, `freshness(snapshotAge:wokeRecently:)`, `certainty(confidence:)`, `ageText(_:)`, `countdownText(to:from:)`, `wakeGrace`
- Produces:
  - `final class UsageModel: ObservableObject` — `@Published var snapshot: UsageSnapshot`, `@Published var engineError: String?`, `@Published var wokeRecently: Bool`
  - `struct PopoverView: View` — `init(model: UsageModel)`

- [ ] **Step 1: เขียนทับ `App/AIUsageApp.swift`**

```swift
import SwiftUI
import AppKit

@main
struct AIUsageApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene { Settings { EmptyView() } }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var timer: Timer?
    private var runner: EngineRunner?
    private var lastWake = Date.distantPast

    private let model = UsageModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.action = #selector(togglePopover)
        statusItem.button?.target = self

        popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 340, height: 420)
        popover.contentViewController = NSHostingController(
            rootView: PopoverView(model: model))

        if let script = EngineRunner.bundledScriptURL {
            runner = EngineRunner(scriptURL: script)
        } else {
            model.engineError = "ไม่พบ ai-usage.60s.py ใน bundle"
        }

        NSWorkspace.shared.notificationCenter.addObserver(
            self, selector: #selector(didWake),
            name: NSWorkspace.didWakeNotification, object: nil)

        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    @objc private func didWake() { lastWake = Date(); refresh() }

    private var wokeRecently: Bool {
        Date().timeIntervalSince(lastWake) < wakeGrace
    }

    private func refresh() {
        runner?.run { [weak self] result in
            guard let self else { return }
            if case .failure(let e) = result, case .alreadyRunning = e { return }
            if case .failure(let e) = result {
                self.model.engineError = EngineRunner.describe(e)
            } else {
                self.model.engineError = nil
            }
            self.model.snapshot = UsageSnapshot.load()
            self.model.wokeRecently = self.wokeRecently
            self.updateBar()
        }
        updateBar()
    }

    private func updateBar() {
        let text = menuBarText(snapshot: model.snapshot, now: Date(),
                               wokeRecently: wokeRecently)
        guard let button = statusItem.button else { return }
        let font = NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .medium)
        let para = NSMutableParagraphStyle()
        para.alignment = .right
        para.maximumLineHeight = 10
        let attr = NSMutableAttributedString(
            string: "\(text.top)\n\(text.bottom)",
            attributes: [.font: font, .paragraphStyle: para,
                         .foregroundColor: NSColor.labelColor])
        button.attributedTitle = attr
        button.alphaValue = text.dimmed ? 0.55 : 1.0
    }

    @objc private func togglePopover() {
        guard let button = statusItem.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            model.snapshot = UsageSnapshot.load()
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            popover.contentViewController?.view.window?.makeKey()
        }
    }
}

final class UsageModel: ObservableObject {
    @Published var snapshot: UsageSnapshot = .load()
    @Published var engineError: String?
    @Published var wokeRecently = false
}
```

- [ ] **Step 2: เขียน popover**

สร้าง `App/PopoverView.swift`:

```swift
import SwiftUI

struct PopoverView: View {
    @ObservedObject var model: UsageModel
    @State private var now = Date()

    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    /// อายุของ snapshot — บอกว่า engine ยังทำงานอยู่ไหม
    /// คนละเรื่องกับ certainty ของแต่ละแถวซึ่งบอกว่าตัวเลขถูกไหม
    private var snapshotAge: TimeInterval? {
        model.snapshot.generated == .distantPast
            ? nil : now.timeIntervalSince(model.snapshot.generated)
    }

    private var snapshotState: Freshness {
        freshness(snapshotAge: snapshotAge, wokeRecently: model.wokeRecently)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let err = model.engineError {
                strip(icon: "exclamationmark.triangle.fill", text: err, tint: .red)
            } else if snapshotState != .fresh, let age = snapshotAge {
                strip(icon: "arrow.clockwise",
                      text: "อัปเดตล่าสุด \(ageText(age)) ที่แล้ว",
                      tint: snapshotState == .dead ? .red : .orange)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(model.snapshot.items) { item in
                        row(item)
                    }
                    if model.snapshot.items.isEmpty {
                        Text("ยังไม่มีข้อมูล")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 40)
                    }
                }
                .padding(14)
            }
        }
        .frame(width: 340, height: 420)
        .onReceive(tick) { now = $0 }
    }

    @ViewBuilder
    private func strip(icon: String, text: String, tint: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
            Text(text).font(.system(size: 11)).lineLimit(2)
            Spacer()
        }
        .foregroundStyle(tint)
        .padding(.horizontal, 14).padding(.vertical, 8)
        .background(tint.opacity(0.12))
    }

    @ViewBuilder
    private func row(_ item: UsageItem) -> some View {
        let sure = item.error == nil ? certainty(confidence: item.confidence) : .unknown

        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(item.group).font(.system(size: 12, weight: .semibold))
                Text(item.label).font(.system(size: 11)).foregroundStyle(.secondary)
                if let plan = item.plan {
                    Text(plan).font(.system(size: 9, weight: .medium))
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(Color.secondary.opacity(0.15))
                        .clipShape(Capsule())
                }
                Spacer()
                if let e = item.error {
                    Text("พัง").font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.red)
                        .help(e)
                } else {
                    Text(pctText(item.pct ?? item.weekPct, sure))
                        .font(.system(size: 12, weight: .medium))
                        .monospacedDigit()
                }
            }

            bar(pct: item.pct, tint: item.tint, sure: sure)
            bar(pct: item.weekPct, tint: item.tint, sure: sure)

            HStack(spacing: 8) {
                if let e = item.error {
                    Text(e).font(.system(size: 10)).foregroundStyle(.red).lineLimit(2)
                } else {
                    if item.local == true {
                        Text("ในเครือข่ายตัวเอง · ไม่มีโควตา")
                    } else if !item.isOfficial {
                        Text("\(item.tokensText) · ยังไม่รู้เพดาน")
                    } else {
                        Text("รีเซ็ต \(countdownText(to: item.resetAt, from: now))")
                    }
                    if sure == .atLeast {
                        Text("· ใช้ต่อหลังเช็คล่าสุด")
                    }
                    if let active = item.activeLimit {
                        Text("· ชนลิมิต \(active)").foregroundStyle(.red)
                    }
                }
                Spacer()
            }
            .font(.system(size: 10))
            .foregroundStyle(.secondary)
        }
    }

    private func pctText(_ pct: Double?, _ sure: Certainty) -> String {
        guard let p = pct, sure != .unknown else { return "—" }
        return (sure == .atLeast ? "≥" : "") + String(format: "%.0f%%", p)
    }

    /// แถบทึบ = ตรงตามนี้ · ทึบ+ลาย = อย่างน้อยเท่านี้ · จุดประ = ไม่รู้
    /// แถบทึบเต็มจากตัวเลขที่รู้ว่าต่ำไปคือการโกหก ไม่ใช่การประมาณ
    @ViewBuilder
    private func bar(pct: Double?, tint: Color, sure: Certainty) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.18))
                if let p = pct, sure != .unknown {
                    let known = geo.size.width * min(1, max(0, p / 100))
                    Capsule().fill(tint).frame(width: known)
                    if sure == .atLeast {
                        // ส่วนที่ยังไม่รู้ — ของจริงอยู่ที่ไหนสักแห่งทางขวาของเส้นทึบ
                        Capsule().fill(tint.opacity(0.25))
                            .frame(width: max(0, geo.size.width - known))
                            .offset(x: known)
                    }
                } else {
                    HStack(spacing: 3) {
                        ForEach(0..<max(1, Int(geo.size.width / 6)), id: \.self) { _ in
                            Circle().fill(Color.secondary.opacity(0.45))
                                .frame(width: 2, height: 2)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .frame(height: 6)
    }
}
```

- [ ] **Step 3: build ให้ผ่าน**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -5
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 4: ตรวจว่า engine ถูกวางในโครงที่มันหาตัวเองเจอ**

`ai-usage.60s.py` ทำ `sys.path.insert(0, dirname(__file__) + "/engine")` ถ้า xcodegen แบนโฟลเดอร์ `engine/` ตอน copy เข้า Resources การ import จะพัง — ตรวจก่อนเปิดแอป:

```bash
APP=build/Build/Products/Release/AIUsage.app/Contents/Resources
ls "$APP/ai-usage.60s.py" && ls "$APP/engine/aiusage/buckets.py"
/usr/bin/env python3 "$APP/ai-usage.60s.py" --json > /dev/null && echo "engine ใน bundle รันได้"
```

Expected: เจอทั้งสองไฟล์ และบรรทัดสุดท้ายพิมพ์ `engine ใน bundle รันได้`

ถ้า `engine/aiusage/buckets.py` ไม่อยู่ ให้เปลี่ยน entry ใน `project.yml` เป็น folder reference:

```yaml
      - path: engine
        buildPhase: resources
        type: folder
```

แล้ว `xcodegen generate` ใหม่

- [ ] **Step 5: รันจริงแล้วดูด้วยตา**

```bash
python3 ai-usage.60s.py --snapshot
open build/Build/Products/Release/AIUsage.app
```

ตรวจด้วยตาว่า: ไอคอนโผล่บน menu bar เป็นสองบรรทัด · ไม่มีไอคอนใน Dock · คลิกแล้ว popover เปิด · เห็นแถวของ default / mooz / Codex / GLM / Qwen Cloud · แถวที่ไม่มี % เป็นจุดประไม่ใช่แถบเต็ม

ถ้าไอคอนไม่โผล่ ตรวจว่า `INFOPLIST_KEY_LSUIElement: YES` อยู่ใน `project.yml` แล้ว และแอปไม่ได้ถูก quit ทันทีเพราะ crash — ดู `log stream --predicate 'process == "AIUsage"' --level error` คู่กัน

- [ ] **Step 6: ปิดแอปแล้ว commit**

```bash
osascript -e 'quit app "AIUsage"' 2>/dev/null || true
git add App/PopoverView.swift App/AIUsageApp.swift
git commit -m "feat(app): status item and popover wired to the engine"
```

---

### Task 11: setup.sh ที่รันซ้ำได้จริง

สคริปต์เดิมลบแล้ว copy แล้ว `open` โดยไม่ปิดแอปเก่าก่อน — macOS ยอมให้ลบ bundle ที่รันอยู่ (process เกาะ inode เดิม) แล้ว `open` ที่มี instance รันอยู่ก็แค่ activate ตัวเก่า ผลคือพิมพ์ "เสร็จแล้ว" ทั้งที่ผู้ใช้ยังรันไบนารีเดิม

**Files:**
- Modify: `setup.sh`
- Modify: `project.yml` (เวอร์ชันจาก git)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: target `AIUsage` จาก task 1
- Produces: `./setup.sh` และ `./setup.sh --uninstall`

- [ ] **Step 1: เขียนทับ setup.sh**

```bash
#!/bin/bash
# ติดตั้งหรืออัปเดต AI Usage — รันซ้ำได้ ผลลัพธ์เหมือนกันทุกครั้ง
# ใช้: ./setup.sh [--uninstall]
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$PWD"
APP_NAME="AIUsage"
INSTALLED="/Applications/${APP_NAME}.app"
SNAPSHOT="$HOME/Library/Application Support/AIUsage/snapshot.json"

quit_app() {
  osascript -e "quit app \"${APP_NAME}\"" >/dev/null 2>&1 || true
  for _ in $(seq 1 10); do
    pgrep -f "${APP_NAME}.app/Contents/MacOS" >/dev/null || return 0
    sleep 0.5
  done
  pkill -f "${APP_NAME}.app/Contents/MacOS" >/dev/null 2>&1 || true
  sleep 1
}

if [ "${1:-}" = "--uninstall" ]; then
  echo "▸ ถอนการติดตั้ง"
  quit_app
  # เผื่อเครื่องที่เคยติดตั้งแบบเก่าที่ยังใช้ launchd
  launchctl bootout "gui/$(id -u)/com.aiusage.snapshot" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/com.aiusage.snapshot.plist"
  rm -rf "$INSTALLED"
  echo "  ลบแอปและ launchd job แล้ว"
  echo "  ข้อมูลยังอยู่ที่ ~/Library/Application Support/AIUsage/"
  echo "  ลบเองด้วย: rm -rf ~/Library/Application\\ Support/AIUsage"
  exit 0
fi

echo "▸ 1/4 ตรวจเครื่องมือ"
command -v xcodegen >/dev/null 2>&1 || { echo "  ติดตั้ง xcodegen…"; brew install xcodegen; }
command -v xcodebuild >/dev/null 2>&1 || { echo "  ต้องมี Xcode ก่อน"; exit 1; }

echo "▸ 2/4 ตั้งเวอร์ชันจาก git"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BUILD_NUM=$(git rev-list --count HEAD)
  VERSION=$(git describe --tags --always 2>/dev/null || echo "dev")
else
  BUILD_NUM=0
  VERSION=dev
fi
echo "  $VERSION ($BUILD_NUM)"

echo "▸ 3/4 build"
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build \
  MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD_NUM" \
  CODE_SIGN_IDENTITY="-" CODE_SIGNING_REQUIRED=NO CODE_SIGNING_ALLOWED=NO \
  build > /tmp/aiusage-build.log 2>&1 || { tail -30 /tmp/aiusage-build.log; exit 1; }

APP="$ROOT/build/Build/Products/Release/${APP_NAME}.app"
[ -d "$APP" ] || { echo "  build ไม่ได้ .app — ดู /tmp/aiusage-build.log"; exit 1; }

echo "▸ 4/4 ติดตั้ง"
# ปิดตัวเก่าก่อนเสมอ ไม่งั้น copy ทับแล้ว process เดิมยังรันโค้ดเก่าอยู่
quit_app
rm -rf "$INSTALLED"
cp -R "$APP" /Applications/
open "$INSTALLED"

# ยืนยันว่าใช้ได้จริง ห้ามพิมพ์ว่าเสร็จลอยๆ
echo -n "  รอ snapshot ใหม่"
BEFORE=$(python3 -c "
import json,os,sys
try: print(json.load(open(os.path.expanduser('$SNAPSHOT')))['generated'])
except Exception: print('')
" 2>/dev/null || echo "")
for _ in $(seq 1 18); do
  sleep 5; echo -n "."
  NOW=$(python3 -c "
import json,os
try: print(json.load(open(os.path.expanduser('$SNAPSHOT')))['generated'])
except Exception: print('')
" 2>/dev/null || echo "")
  if [ -n "$NOW" ] && [ "$NOW" != "$BEFORE" ]; then
    echo
    echo "เสร็จแล้ว — $VERSION ทำงานอยู่บน menu bar"
    exit 0
  fi
done

echo
echo "แอปติดตั้งแล้วแต่ยังไม่เขียน snapshot ภายใน 90 วินาที"
echo "ตรวจด้วย: log stream --predicate 'process == \"AIUsage\"' --level error"
exit 1
```

- [ ] **Step 2: ให้รันได้**

```bash
chmod +x setup.sh
```

- [ ] **Step 3: ทดสอบว่ารันซ้ำได้จริง**

```bash
./setup.sh && ./setup.sh
```

Expected: ผ่านทั้งสองรอบ ลงท้ายด้วย `เสร็จแล้ว — <version> ทำงานอยู่บน menu bar` และรอบสองต้องไม่ค้างเพราะแอปเก่ายังเปิดอยู่

- [ ] **Step 4: ทดสอบว่าอัปเดตแล้วได้โค้ดใหม่จริง**

```bash
grep -n "5h" App/MenuBarLabel.swift | head -2
# แก้ข้อความชั่วคราวให้เห็นความต่าง
sed -i '' 's/"5h    —"/"5H    —"/' App/MenuBarLabel.swift
./setup.sh
```

Expected: แอปที่รันอยู่หลัง `setup.sh` ต้องเป็นตัวใหม่ ไม่ใช่ตัวเก่าที่ค้างอยู่ — ตรวจโดย:

```bash
/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" /Applications/AIUsage.app/Contents/Info.plist
```

ต้องตรงกับ `git rev-list --count HEAD` แล้วคืนค่าที่แก้:

```bash
git checkout App/MenuBarLabel.swift
./setup.sh
```

- [ ] **Step 5: ทดสอบ uninstall**

```bash
./setup.sh --uninstall
test ! -d /Applications/AIUsage.app && echo "ลบแล้ว"
./setup.sh
```

- [ ] **Step 6: แก้ CLAUDE.md ให้ตรงกับความจริง**

ใน `CLAUDE.md` แก้ให้ตรง — ตอนนี้มันยังบอกเรื่อง widget gallery และ launchd ซึ่งเลิกใช้แล้ว:

- หัวข้อ "สิ่งที่ต้องทำ" — เปลี่ยนจาก "widget ปรากฏใน widget gallery" เป็น "ไอคอนปรากฏบน menu bar"
- โครงสร้าง — ลบบรรทัด `Widget/AIUsageWidget.swift` และ `launchd/…plist` เพิ่ม `App/EngineRunner.swift`, `App/MenuBarLabel.swift`, `App/PopoverView.swift`, `Shared/Freshness.swift`, `engine/aiusage/`
- ข้อควรระวัง — ลบข้อ "widget extension เป็น com.apple.widgetkit-extension" เพิ่ม "แอปเรียก engine เอง ไม่ใช้ launchd"
- "ตรวจว่าใช้ได้จริง" — เปลี่ยน `tail /tmp/aiusage.err.log` เป็น `log stream --predicate 'process == "AIUsage"' --level error` และเพิ่ม `python3 -m unittest discover -s engine/tests`
- "ที่ยังทำไม่เสร็จ" — ลบข้อเรื่อง `budget5h` / `budgetWeek` ที่ผู้ใช้ต้องกรอกเอง (ตอนนี้ได้ % ทางการแล้ว) เพิ่มว่า Qwen Cloud กับ GLM ยังไม่มีแหล่ง % และรอแผน 2

- [ ] **Step 7: Commit**

```bash
git add setup.sh CLAUDE.md project.yml
git commit -m "fix(setup): quit old app before replacing it, verify install, add uninstall"
```

---

## หลังจบแผนนี้

รัน `python3 -m unittest discover -s engine/tests` และ `xcodebuild test` ต้องผ่านทั้งคู่ แล้ว `./setup.sh` ต้องจบด้วยไอคอนบน menu bar ที่แสดง % จริง

**แผนถัดไปต้องมี** (บางข้อรอคำตอบจากผู้ใช้):

1. **โหมดแสดงเงิน** — GLM ยืนยันแล้วว่าไม่มี coding plan (`当前用户不存在coding plan`) ถังแบบจ่ายตามใช้ต้องไม่มีแถบ % เลย
2. **Qwen Cloud** — ต้องได้ endpoint ของหน้า dashboard ก่อน หน่วยเป็น Credits แผน Standard 3,000/10,000 แต่ Alibaba ไม่ประกาศสูตรแปลง token → credit
3. **บัญชี `work`** — เป็น Team tier แล้วไม่มี `cachedUsageUtilization` เลย ต้องเช็คซ้ำหลังใช้บัญชีนั้นว่าเป็นเพราะไม่ได้ใช้นาน หรือ Team ไม่ได้รับข้อมูลนี้
4. **หน้า settings + โลโก้ provider** — จาก simple-icons (CC0) และ lobe-icons (MIT)
5. **แจ้งเตือนใกล้ชนลิมิต** — ใช้ `severity` จาก Anthropic ไม่ต้องคิดเกณฑ์เอง
6. **GLM ถ้าต่ออายุ coding plan** — `GET https://api.z.ai/api/monitor/usage/quota/limit` จะคืนโควตาจริงทันที โค้ดต้องรองรับทั้งสองแบบ
