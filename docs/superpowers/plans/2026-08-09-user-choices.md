# AI Usage — แผนลงมือ เฟส 2: สิ่งที่ผู้ใช้เลือกเองได้

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ให้ผู้ใช้คุมได้สามเรื่องที่แอปไม่ควรตัดสินใจแทน — ปักหมุดเลือกว่าแถบเมนูโชว์ถังไหน · แสดง/ซ่อนถังในรายการ · ใส่ราคาเองสำหรับถังที่ระบบไม่รู้ราคา

**Architecture:** ตัวเลือกทั้งหมดเก็บใน `UserDefaults` ฝั่ง Swift อย่างเดียว **ไม่แตะเอนจิน Python** เพราะมันเป็นเรื่องการแสดงผลล้วนๆ ยกเว้นราคาที่ผู้ใช้ใส่เอง ซึ่งคำนวณฝั่ง Swift จาก `tokens` ที่เอนจินให้มาแล้ว การแยกแบบนี้ทำให้ snapshot ยังเป็นข้อมูลดิบที่ไม่มีความชอบส่วนตัวปนอยู่

**Tech Stack:** Swift 5 / SwiftUI / AppKit · XCTest · macOS 14+

## Global Constraints

- **ห้ามเปิด App Sandbox** — `ENABLE_APP_SANDBOX: NO` ถ้าเปิด `NSHomeDirectory()` จะชี้ไป container แล้วอ่าน snapshot ไม่เจอ
- **ห้ามแก้ตรรกะการนับใน `ai-usage.60s.py`** — `claude_entries` / `summarize` / `current_block` / `total_tokens` ทดสอบกับข้อมูลจริงแล้ว
- **ห้ามอ่านหรือ log ค่า `ANTHROPIC_AUTH_TOKEN` / `oauth_creds` / `.credentials.json`**
- **แถบ menu bar ไม่เกิน 10 ตัวอักษรต่อบรรทัด** — ผู้ใช้ตีกลับแบบ 22 ตัวอักษรมาแล้ว
- **ห้ามแสดง `$0.00` เมื่อไม่รู้ราคา** — ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี" และมันจะไปตกกับ GLM พอดี ซึ่งเป็นถังเดียวที่เงินไหลจริง
- **ห้ามแสดงแถบทึบจากตัวเลขที่รู้ว่าต่ำไป** — `lower_bound` ต้องขึ้น `≥` เสมอ
- ข้อความที่ผู้ใช้เห็นเป็น**ภาษาไทย**
- ทุก task จบด้วย commit

**อ้างอิง:** สเปก `docs/superpowers/specs/2026-08-06-ai-usage-menubar-design.md` · ดีไซน์ https://claude.ai/code/artifact/96fb24ff-b984-4136-b071-4f7533dd6042

---

## สถานะจริง ณ 2026-08-09 (ตรวจแล้ว ไม่ใช่สมมติ)

แผนเฟส 1 (`2026-08-07-menubar-real-numbers.md`) **ถูกทำไปเกือบหมดแล้ว** ห้ามรันซ้ำ

| ของ | สถานะ |
|---|---|
| `engine/aiusage/buckets.py` + `utilization.py` + เทสต์ | ✅ 7 เทสต์ผ่าน |
| ฟิลด์ตามสัญญาใน snapshot (`pctSource` `confidence` `weekConfidence` `severity` `costKnown` `costKind` …) | ✅ |
| `bucket_rows()` แยกแถวตาม (บัญชี × ถัง) | ✅ |
| แถว error แทนการ `continue` เงียบ · ไม่เขียนทับด้วยผลว่าง | ✅ |
| `Shared/Freshness.swift` — `Freshness` + `Certainty` | ✅ |
| `Shared/UsageSnapshot.swift` · `App/EngineRunner.swift` · `MenuBarLabel.swift` · `PopoverView.swift` | ✅ |
| `setup.sh` — ปิดแอปเก่าก่อน copy · เวอร์ชันจาก git · `--uninstall` · ยืนยันหลังติดตั้ง | ✅ |
| เทสต์ Swift | ✅ 11 เทสต์ผ่าน |

**ที่ยังไม่มี:**

- **ยังไม่ใช่ git repo** — ไม่มีตาข่ายรองรับเลย ← Task 1
- ยังไม่เคยติดตั้งลง `/Applications`
- ไม่มีหน้าตั้งค่า · ไม่มีการปักหมุด · ไม่มีที่เก็บราคาที่ผู้ใช้ใส่เอง

**บั๊กที่เพิ่งแก้ไประหว่างสำรวจ (อย่าทำซ้ำ):**

1. `PRICES` ตั้ง `opus` ไว้ $15/$75 (ของ Opus รุ่นเก่า) และ **ไม่มี `fable` เลย** ทั้งที่ใช้มากอันดับสอง → ยอดสัปดาห์เกินจริงจาก $2,614.96 เหลือ $1,160.38
2. `<synthetic>` งอกเป็นถัง "ยังไม่รู้จัก" → เพิ่ม `buckets.is_real_model()` กรองออก
3. `cost`/`weekCost` คืน `0.0` ตอนไม่รู้ราคา → เปลี่ยนเป็น `None` (6 จุด)
4. **ผลข้างเคียงของข้อ 3** — Swift ประกาศ `cost: Double` แบบไม่ optional และใช้ `decode()` ไม่ใช่ `decodeIfPresent()` → `null` ทำให้ decode **ล้มทั้งไฟล์** แอปขึ้นว่างเปล่าทั้งหมด แก้เป็น `Double?` แล้ว และปักหมุดด้วยเทสต์ `testNullCostDoesNotBreakTheWholeSnapshot`
5. `AIUsageTests` ไม่มี `GENERATE_INFOPLIST_FILE` → `xcodebuild test` พังตั้งแต่ code sign

---

### Task 1: ตั้ง git ก่อนแตะอะไรอีก

ตอนนี้มีโค้ดที่ทำงานได้แล้วหลายพันบรรทัด แต่ไม่มี git เลย งานทุกอย่างหลังจากนี้แก้กลับไม่ได้ถ้าพลาด

**Files:**
- Create: `.gitignore`

**Interfaces:**
- Consumes: ไม่มี
- Produces: git repo ที่มีคอมมิตแรกครอบโค้ดปัจจุบันทั้งหมด — ทุก task หลังจากนี้พึ่งพา `git rev-list --count HEAD` ที่ `setup.sh` เรียกใช้อยู่แล้ว

- [ ] **Step 1: ยืนยันว่าเทสต์ผ่านก่อน commit ของที่พัง**

```bash
cd /Users/phunonkoysawat/Documents/Develop/projects/AIUsageWidget
python3 -m unittest discover -s engine/tests -q
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "Executed .* tests.*failures" | tail -1
```

Expected: Python `OK` · Swift `Executed 11 tests, with 0 failures`

- [ ] **Step 2: สร้าง .gitignore**

```gitignore
build/
AIUsage.xcodeproj/
__pycache__/
*.pyc
.DS_Store
*.bak-*
```

`AIUsage.xcodeproj/` ไม่เข้า git เพราะ `xcodegen generate` สร้างใหม่ได้จาก `project.yml` เสมอ

- [ ] **Step 3: init และ commit**

```bash
git init
git add -A
git commit -m "feat: menu bar app with official Anthropic utilization data

เอนจิน Python อ่าน cachedUsageUtilization แล้วแยกแถวตาม (บัญชี x ถังโควตา)
โดยถังกำหนดจาก endpoint ใน ~/.ccs/*.settings.json ไม่ใช่ชื่อโมเดล
แอป Swift เรียกเอนจินเองทุก 60 วิ ไม่ใช้ launchd"
```

- [ ] **Step 4: ยืนยัน**

```bash
git log --oneline
git status --short
```

Expected: มี 1 คอมมิต · `git status` ว่าง (ยกเว้นของที่ ignore)

---

### Task 2: ที่เก็บตัวเลือกของผู้ใช้

ทั้งสามฟีเจอร์ต้องจำค่าข้ามการเปิดปิดแอป ทำที่เก็บให้เสร็จก่อนแล้วอีกสาม task ค่อยต่อยอด แยกเป็นไฟล์เดียวที่ทดสอบได้โดยไม่ต้องเปิดหน้าต่าง

**Files:**
- Create: `Shared/Preferences.swift`
- Test: `Tests/PreferencesTests.swift`

**Interfaces:**
- Consumes: ไม่มี
- Produces:
  - `final class Preferences: ObservableObject` — `init(defaults: UserDefaults)`
  - `@Published private(set) var pinned: [String]` — id ของถังที่ปักหมุด เรียงตามที่ผู้ใช้ปัก
  - `@Published private(set) var hidden: Set<String>` — id ของถังที่ซ่อน
  - `@Published private(set) var prices: [String: Price]` — id → ราคาที่ผู้ใช้ใส่เอง
  - `struct Price: Codable, Equatable { var inputPerMillion: Double; var outputPerMillion: Double }`
  - `func togglePin(_ id: String)` · `func setHidden(_ id: String, _ hidden: Bool)` · `func setPrice(_ id: String, _ price: Price?)` · `func clearPins()`
  - `let maxPins = 4`
  - `func canPin(_ id: String) -> Bool`

`id` คือ `UsageItem.id` ซึ่งเป็น `"\(group)/\(label)"` — คงที่ข้ามรอบ

- [ ] **Step 1: เขียนเทสต์ที่ยังไม่ผ่าน**

สร้าง `Tests/PreferencesTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class PreferencesTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "aiusage.tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        super.tearDown()
    }

    func testStartsEmpty() {
        let prefs = Preferences(defaults: defaults)
        XCTAssertTrue(prefs.pinned.isEmpty)
        XCTAssertTrue(prefs.hidden.isEmpty)
        XCTAssertTrue(prefs.prices.isEmpty)
    }

    func testPinToggleRoundTrips() {
        let prefs = Preferences(defaults: defaults)
        prefs.togglePin("Claude Code/default")
        XCTAssertEqual(prefs.pinned, ["Claude Code/default"])
        prefs.togglePin("Claude Code/default")
        XCTAssertTrue(prefs.pinned.isEmpty)
    }

    func testPinOrderFollowsTheOrderTheUserPinned() {
        let prefs = Preferences(defaults: defaults)
        prefs.togglePin("Codex/Codex")
        prefs.togglePin("Claude Code/default")
        XCTAssertEqual(prefs.pinned, ["Codex/Codex", "Claude Code/default"])
    }

    /// แถบเมนูไม่ใช่ dashboard
    func testCannotPinMoreThanFour() {
        let prefs = Preferences(defaults: defaults)
        for i in 0..<4 { prefs.togglePin("bucket/\(i)") }
        XCTAssertFalse(prefs.canPin("bucket/5"))
        prefs.togglePin("bucket/5")
        XCTAssertEqual(prefs.pinned.count, 4, "ปักเกิน 4 ไม่ได้")
    }

    func testAlreadyPinnedCanAlwaysBeUnpinned() {
        let prefs = Preferences(defaults: defaults)
        for i in 0..<4 { prefs.togglePin("bucket/\(i)") }
        XCTAssertTrue(prefs.canPin("bucket/0"), "ตัวที่ปักแล้วต้องกดปลดได้เสมอ")
        prefs.togglePin("bucket/0")
        XCTAssertEqual(prefs.pinned.count, 3)
    }

    func testHiddenRoundTrips() {
        let prefs = Preferences(defaults: defaults)
        prefs.setHidden("กรอกเอง/ChatGPT", true)
        XCTAssertTrue(prefs.hidden.contains("กรอกเอง/ChatGPT"))
        prefs.setHidden("กรอกเอง/ChatGPT", false)
        XCTAssertFalse(prefs.hidden.contains("กรอกเอง/ChatGPT"))
    }

    func testPriceRoundTrips() {
        let prefs = Preferences(defaults: defaults)
        prefs.setPrice("GLM/default", Price(inputPerMillion: 0.6, outputPerMillion: 2.2))
        XCTAssertEqual(prefs.prices["GLM/default"]?.outputPerMillion, 2.2)
        prefs.setPrice("GLM/default", nil)
        XCTAssertNil(prefs.prices["GLM/default"])
    }

    func testEverythingSurvivesRelaunch() {
        let first = Preferences(defaults: defaults)
        first.togglePin("Codex/Codex")
        first.setHidden("spark/spark", true)
        first.setPrice("GLM/default", Price(inputPerMillion: 0.6, outputPerMillion: 2.2))

        let second = Preferences(defaults: defaults)
        XCTAssertEqual(second.pinned, ["Codex/Codex"])
        XCTAssertTrue(second.hidden.contains("spark/spark"))
        XCTAssertEqual(second.prices["GLM/default"]?.inputPerMillion, 0.6)
    }

    func testClearPinsReturnsToAutomatic() {
        let prefs = Preferences(defaults: defaults)
        prefs.togglePin("Codex/Codex")
        prefs.clearPins()
        XCTAssertTrue(prefs.pinned.isEmpty, "ไม่ปักเลย = โหมดอัตโนมัติ")
    }

    func testCorruptStoredDataDoesNotCrash() {
        defaults.set("ไม่ใช่ JSON", forKey: "prices")
        defaults.set(42, forKey: "pinned")
        let prefs = Preferences(defaults: defaults)
        XCTAssertTrue(prefs.prices.isEmpty)
        XCTAssertTrue(prefs.pinned.isEmpty)
    }
}
```

- [ ] **Step 2: รันให้เห็นว่าพัง**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "error:" | head -3
```

Expected: `cannot find 'Preferences' in scope`

- [ ] **Step 3: เขียน implementation**

สร้าง `Shared/Preferences.swift`:

```swift
import Foundation

/// ราคาที่ผู้ใช้ใส่เอง — ผูกกับ "ถัง" ไม่ใช่โมเดล
/// เพราะทุกโมเดลที่วิ่งผ่าน endpoint เดียวกันกินกระเป๋าใบเดียวกัน
struct Price: Codable, Equatable {
    var inputPerMillion: Double
    var outputPerMillion: Double
}

/// ตัวเลือกของผู้ใช้ ไม่ปนกับข้อมูลใน snapshot
///
/// snapshot คือความจริงที่วัดได้ · ที่นี่คือความชอบส่วนตัว
/// แยกกันไว้เอนจินจะได้ไม่ต้องรู้จักคำว่า "ปักหมุด" เลย
final class Preferences: ObservableObject {
    static let maxPins = 4

    private enum Key {
        static let pinned = "pinned"
        static let hidden = "hidden"
        static let prices = "prices"
    }

    private let defaults: UserDefaults

    @Published private(set) var pinned: [String]
    @Published private(set) var hidden: Set<String>
    @Published private(set) var prices: [String: Price]

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        pinned = (defaults.array(forKey: Key.pinned) as? [String]) ?? []
        hidden = Set((defaults.array(forKey: Key.hidden) as? [String]) ?? [])
        prices = Self.decodePrices(defaults.data(forKey: Key.prices))
    }

    var maxPins: Int { Self.maxPins }

    /// ตัวที่ปักแล้วต้องปลดได้เสมอ ไม่งั้นผู้ใช้จะติดกับตอนปักครบ 4
    func canPin(_ id: String) -> Bool {
        pinned.contains(id) || pinned.count < Self.maxPins
    }

    func togglePin(_ id: String) {
        if let index = pinned.firstIndex(of: id) {
            pinned.remove(at: index)
        } else if pinned.count < Self.maxPins {
            pinned.append(id)
        } else {
            return
        }
        defaults.set(pinned, forKey: Key.pinned)
    }

    func clearPins() {
        pinned = []
        defaults.set(pinned, forKey: Key.pinned)
    }

    func setHidden(_ id: String, _ isHidden: Bool) {
        if isHidden { hidden.insert(id) } else { hidden.remove(id) }
        defaults.set(Array(hidden), forKey: Key.hidden)
    }

    func setPrice(_ id: String, _ price: Price?) {
        if let price { prices[id] = price } else { prices.removeValue(forKey: id) }
        defaults.set(try? JSONEncoder().encode(prices), forKey: Key.prices)
    }

    private static func decodePrices(_ data: Data?) -> [String: Price] {
        guard let data,
              let decoded = try? JSONDecoder().decode([String: Price].self, from: data)
        else { return [:] }
        return decoded
    }
}
```

`defaults.array(forKey:) as? [String]` คืน `nil` เองเมื่อค่าที่เก็บไว้เป็นชนิดอื่น จึงรอดจากข้อมูลเสียโดยไม่ต้องดักเพิ่ม

- [ ] **Step 4: รันให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "Executed .* tests.*failures" | tail -1
```

Expected: `Executed 21 tests, with 0 failures` (11 เดิม + 10 ใหม่)

- [ ] **Step 5: Commit**

```bash
git add Shared/Preferences.swift Tests/PreferencesTests.swift project.yml
git commit -m "feat(app): persist user choices for pins, hidden buckets and prices"
```

---

### Task 3: ปักหมุดเลือกว่าแถบเมนูโชว์ถังไหน

ตอนนี้แถบเมนูเลือก `snapshot.worst` ให้เสมอ ผู้ใช้คุมไม่ได้ว่าจะเห็นของใคร

**Files:**
- Modify: `App/MenuBarLabel.swift`
- Modify: `App/AIUsageApp.swift`
- Modify: `App/PopoverView.swift`
- Test: `Tests/MenuBarLabelTests.swift`

**Interfaces:**
- Consumes: `Preferences` (`pinned`, `canPin`, `togglePin`, `clearPins`), `UsageSnapshot`, `Certainty`, `Freshness`
- Produces:
  - `func menuBarUnits(snapshot: UsageSnapshot, pinned: [String]) -> [UsageItem]` — คืนถังที่จะขึ้นแถบเมนู ว่างเปล่าแปลว่าไม่มีอะไรแสดงได้
  - `func compactLine(_ item: UsageItem) -> String` — บรรทัดเดียว เช่น `"≥96%"`
  - `func hasUnpinnedCritical(snapshot: UsageSnapshot, pinned: [String]) -> Bool`
  - `menuBarText(snapshot:now:wokeRecently:)` เดิมยังอยู่ ใช้เมื่อมีถังเดียว

- [ ] **Step 1: เขียนเทสต์ที่ยังไม่ผ่าน**

เพิ่มลงท้าย `Tests/MenuBarLabelTests.swift` ก่อนปีกกาปิดคลาส:

```swift
    // MARK: - ปักหมุด

    private func named(_ group: String, _ label: String,
                       pct: Double?, weekPct: Double?,
                       severity: String? = "normal") -> UsageItem {
        UsageItem(group: group, label: label, window: "5 ชม.", pct: pct,
                  weekPct: weekPct, pctSource: "official", confidence: "valid",
                  weekConfidence: "valid",
                  dataFetchedAt: now.addingTimeInterval(-60), severity: severity)
    }

    func testNoPinsFallsBackToWorst() {
        let snap = snapshot([named("Codex", "Codex", pct: 12, weekPct: 30),
                             named("Claude Code", "default", pct: 5, weekPct: 96)])
        let units = menuBarUnits(snapshot: snap, pinned: [])
        XCTAssertEqual(units.count, 1)
        XCTAssertEqual(units[0].id, "Claude Code/default")
    }

    func testPinnedOrderIsRespected() {
        let snap = snapshot([named("Codex", "Codex", pct: 12, weekPct: 30),
                             named("Claude Code", "default", pct: 5, weekPct: 96)])
        let units = menuBarUnits(snapshot: snap,
                                 pinned: ["Codex/Codex", "Claude Code/default"])
        XCTAssertEqual(units.map(\.id), ["Codex/Codex", "Claude Code/default"])
    }

    /// ถังที่ปักไว้หายไป (ลบบัญชี · engine พัง) ต้องตกกลับไปอัตโนมัติ ไม่ใช่แถบว่าง
    func testMissingPinFallsBackInsteadOfShowingNothing() {
        let snap = snapshot([named("Claude Code", "default", pct: 5, weekPct: 96)])
        let units = menuBarUnits(snapshot: snap, pinned: ["GLM/ที่หายไป"])
        XCTAssertEqual(units.map(\.id), ["Claude Code/default"])
    }

    func testCompactLineMarksLowerBound() {
        var item = named("Claude Code", "default", pct: 5, weekPct: 96)
        item.confidence = "lower_bound"
        item.weekConfidence = "lower_bound"
        XCTAssertEqual(compactLine(item), "≥96%")
    }

    func testCompactLineShowsTheMoreUrgentWindow() {
        let item = named("Claude Code", "default", pct: 5, weekPct: 96)
        XCTAssertEqual(compactLine(item), "96%")
    }

    func testCompactLineStaysWithinFiveCharacters() {
        for (p, w) in [(100.0, 100.0), (0.0, 0.0), (5.0, 96.0)] {
            let item = named("x", "y", pct: p, weekPct: w)
            XCTAssertLessThanOrEqual(compactLine(item).count, 5)
        }
    }

    /// ปัก Codex ไว้อย่างเดียวแล้ว Claude weekly พุ่ง 96% ต้องมีอะไรบอก
    func testUnpinnedCriticalIsFlagged() {
        let snap = snapshot([named("Codex", "Codex", pct: 12, weekPct: 30),
                             named("Claude Code", "default", pct: 5, weekPct: 96,
                                   severity: "critical")])
        XCTAssertTrue(hasUnpinnedCritical(snapshot: snap, pinned: ["Codex/Codex"]))
    }

    func testCriticalOnAPinnedBucketIsNotFlagged() {
        let snap = snapshot([named("Claude Code", "default", pct: 5, weekPct: 96,
                                   severity: "critical")])
        XCTAssertFalse(hasUnpinnedCritical(snapshot: snap,
                                           pinned: ["Claude Code/default"]),
                       "ตัวที่เห็นอยู่แล้วไม่ต้องเตือนซ้ำ")
    }

    func testErrorRowsNeverReachTheBar() {
        var broken = named("Claude Code", "work", pct: nil, weekPct: nil)
        broken.error = "OSError"
        let snap = snapshot([broken, named("Codex", "Codex", pct: 12, weekPct: 30)])
        XCTAssertEqual(menuBarUnits(snapshot: snap, pinned: []).map(\.id), ["Codex/Codex"])
    }
```

- [ ] **Step 2: รันให้เห็นว่าพัง**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "error:" | head -3
```

Expected: `cannot find 'menuBarUnits' in scope`

- [ ] **Step 3: เขียน implementation**

เพิ่มลงท้าย `App/MenuBarLabel.swift`:

```swift
/// ถังที่จะขึ้นแถบเมนู
///
/// ไม่ปักเลย = อัตโนมัติ เลือกตัวที่ใกล้ชนที่สุด — ไม่ต้องมีสวิตช์โหมดแยก
/// เพราะ "ไม่ปัก" คืออัตโนมัติอยู่แล้วโดยธรรมชาติ
func menuBarUnits(snapshot: UsageSnapshot, pinned: [String]) -> [UsageItem] {
    let usable = snapshot.items.filter { $0.error == nil && $0.displayPct != nil }
    let chosen = pinned.compactMap { id in usable.first { $0.id == id } }
    if !chosen.isEmpty { return chosen }
    // ปักไว้แต่หาไม่เจอแล้ว → ตกกลับไปอัตโนมัติ ดีกว่าโชว์แถบว่าง
    return snapshot.worst.map { [$0] } ?? []
}

/// บรรทัดเดียวสำหรับตอนปักหลายถัง — โลโก้บอกว่าของใครอยู่แล้ว
/// เลือกหน้าต่างที่เร่งด่วนกว่า เพราะมีที่ให้ตัวเลขเดียว
func compactLine(_ item: UsageItem) -> String {
    let useWeek = (item.weekPct ?? -1) >= (item.pct ?? -1)
    let pct = useWeek ? item.weekPct : item.pct
    let sure = certainty(confidence: useWeek ? (item.weekConfidence ?? item.confidence)
                                             : item.confidence)
    guard let pct, sure != .unknown else { return "—" }
    return (sure == .atLeast ? "≥" : "") + "\(Int(pct.rounded()))%"
}

/// มีถังที่ไม่ได้ปักกำลังวิกฤตอยู่ไหม
///
/// ถ้าผู้ใช้ปัก Codex ไว้อย่างเดียวแล้ว Claude weekly พุ่งไป 96%
/// เขาจะไม่รู้เลยเพราะเลือกที่จะไม่มองมัน — จุดแดงไม่แย่งที่และไม่เปลี่ยน
/// สิ่งที่เขาเลือก แค่บอกว่าควรเปิดดู
func hasUnpinnedCritical(snapshot: UsageSnapshot, pinned: [String]) -> Bool {
    guard !pinned.isEmpty else { return false }
    return snapshot.items.contains {
        $0.error == nil && $0.severity == "critical" && !pinned.contains($0.id)
    }
}
```

- [ ] **Step 4: ต่อเข้ากับแถบเมนูจริง**

ใน `App/AIUsageApp.swift` แทนที่ฟังก์ชัน `updateBar()` ทั้งตัวด้วย:

```swift
    private func updateBar() {
        guard let button = statusItem.button else { return }
        let snapshot = model.snapshot
        let units = menuBarUnits(snapshot: snapshot, pinned: model.prefs.pinned)
        let snapshotAge = snapshot.generated == .distantPast
            ? nil : Date().timeIntervalSince(snapshot.generated)
        let state = freshness(snapshotAge: snapshotAge, wokeRecently: wokeRecently)
        let alert = hasUnpinnedCritical(snapshot: snapshot, pinned: model.prefs.pinned)

        if units.count <= 1 {
            let text = menuBarText(snapshot: snapshot, now: Date(),
                                   wokeRecently: wokeRecently)
            button.attributedTitle = stackedTitle(text.top, text.bottom, alert: alert)
            button.alphaValue = text.dimmed ? 0.55 : 1.0
        } else {
            let line = units.map(compactLine).joined(separator: "  ")
            button.attributedTitle = singleTitle((alert ? "• " : "") + line)
            button.alphaValue = state == .fresh ? 1.0 : 0.55
        }
    }

    private func stackedTitle(_ top: String, _ bottom: String,
                              alert: Bool) -> NSAttributedString {
        let para = NSMutableParagraphStyle()
        para.alignment = .right
        para.maximumLineHeight = 10
        return NSAttributedString(
            string: (alert ? "• " : "") + top + "\n" + bottom,
            attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .medium),
                         .paragraphStyle: para,
                         .foregroundColor: NSColor.labelColor])
    }

    private func singleTitle(_ line: String) -> NSAttributedString {
        NSAttributedString(
            string: line,
            attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium),
                         .foregroundColor: NSColor.labelColor])
    }
```

และใน `UsageModel` เพิ่มบรรทัด:

```swift
    let prefs = Preferences()
```

**กับดักที่ต้องรู้ก่อน:** `Preferences` เป็น `ObservableObject` คนละตัวกับ `UsageModel`
การเปลี่ยนค่าใน `prefs` **จะไม่ทำให้ view ที่ดูแค่ `model` วาดใหม่** ต้องผูกตรงเสมอ —
ใน `PopoverView` และ `SettingsView` ประกาศเพิ่ม:

```swift
    @ObservedObject var prefs: Preferences
```

แล้วส่งเข้าไปตอนสร้าง (`PopoverView(model: model, prefs: model.prefs)`)
ถ้าลืมข้อนี้ ปุ่มหมุดจะกดแล้วไม่มีอะไรเกิดขึ้นบนจอ ทั้งที่ค่าถูกบันทึกแล้ว

- [ ] **Step 4b: ให้แถบเมนูอัปเดตทันทีที่กดหมุด**

`updateBar()` ถูกเรียกจาก timer ทุก 60 วิ ถ้าไม่ทำอะไรเพิ่ม ผู้ใช้จะกดหมุดแล้วรอถึงนาที
ใน `AppDelegate.applicationDidFinishLaunching` เพิ่ม:

```swift
        prefsObserver = model.prefs.objectWillChange.sink { [weak self] _ in
            DispatchQueue.main.async { self?.updateBar() }
        }
```

พร้อมประกาศ `private var prefsObserver: AnyCancellable?` และ `import Combine`
(`objectWillChange` ยิง *ก่อน* ค่าเปลี่ยน จึงต้อง `DispatchQueue.main.async` ไม่งั้นได้ค่าเก่า)

- [ ] **Step 5: ใส่ปุ่มหมุดในรายการ**

ใน `App/PopoverView.swift` เพิ่มปุ่มหมุดหน้าแต่ละแถว โดยแทรกก่อน `VStack(alignment: .leading, spacing: 5)` ของ `row(_:)` แล้วครอบด้วย `HStack`:

```swift
            HStack(alignment: .top, spacing: 10) {
                Button {
                    model.prefs.togglePin(item.id)
                } label: {
                    Image(systemName: model.prefs.pinned.contains(item.id)
                          ? "pin.fill" : "pin")
                        .font(.system(size: 11))
                        .frame(width: 22, height: 22)
                }
                .buttonStyle(.plain)
                .disabled(!model.prefs.canPin(item.id))
                .help(model.prefs.pinned.contains(item.id)
                      ? "เอาออกจากแถบเมนู"
                      : (model.prefs.canPin(item.id)
                         ? "ปักหมุดขึ้นแถบเมนู"
                         : "ปักได้สูงสุด \(model.prefs.maxPins) ถัง"))
```

ปิด `HStack` ท้าย `row(_:)` และเพิ่มหัวรายการเหนือ `ScrollView`:

```swift
            if !model.prefs.pinned.isEmpty {
                HStack(spacing: 8) {
                    Text("แถบเมนู: ปักหมุดไว้ \(model.prefs.pinned.count)")
                    Spacer()
                    Button("ยกเลิกทั้งหมด → อัตโนมัติ") { model.prefs.clearPins() }
                        .buttonStyle(.plain)
                        .foregroundStyle(.tint)
                }
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 14).padding(.vertical, 8)
            }
```

- [ ] **Step 6: รันเทสต์ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "Executed .* tests.*failures" | tail -1
```

Expected: `Executed 30 tests, with 0 failures`

- [ ] **Step 7: ดูด้วยตา**

```bash
python3 ai-usage.60s.py --snapshot
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -2
osascript -e 'quit app "AIUsage"' 2>/dev/null || true
open build/Build/Products/Release/AIUsage.app
```

ตรวจ: ปักหมุด 1 ถัง → แถบเป็นสองบรรทัดของถังนั้น · ปัก 2 ถัง → บรรทัดเดียวเรียงกัน · ปักครบ 4 แล้วปุ่มที่เหลือกดไม่ได้ · กด "ยกเลิกทั้งหมด" แล้วกลับไปอัตโนมัติ · ปิดแอปเปิดใหม่แล้วหมุดยังอยู่

- [ ] **Step 8: Commit**

```bash
osascript -e 'quit app "AIUsage"' 2>/dev/null || true
git add App Tests
git commit -m "feat(app): pin buckets to the menu bar, with unpinned-critical dot"
```

---

### Task 4: แสดง/ซ่อนถัง และใส่ราคาเอง

ถังที่ไม่ได้ใช้ไม่ควรกินที่ แต่การลบทิ้งให้เลยไม่ใช่หน้าที่แอป และราคาที่ระบบไม่รู้ต้องให้ผู้ใช้เติมได้ ไม่ใช่เดาให้

**Files:**
- Create: `App/SettingsView.swift`
- Modify: `App/PopoverView.swift`
- Modify: `App/AIUsageApp.swift`
- Test: `Tests/CostTests.swift`

**Interfaces:**
- Consumes: `Preferences`, `Price`, `UsageItem`
- Produces:
  - `func effectiveWeekCost(_ item: UsageItem, price: Price?) -> Double?`
  - `func costLabel(_ item: UsageItem, price: Price?) -> String?` — `nil` แปลว่าไม่มีอะไรให้แสดง
  - `struct SettingsView: View` — `init(model: UsageModel)`

- [ ] **Step 1: เขียนเทสต์ที่ยังไม่ผ่าน**

สร้าง `Tests/CostTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class CostTests: XCTestCase {

    private func item(weekCost: Double?, costKnown: Bool, costKind: String? = nil,
                      weekTokens: Int = 0) -> UsageItem {
        UsageItem(group: "GLM", label: "default", window: "5 ชม.",
                  weekTokens: weekTokens, weekCost: weekCost,
                  costKnown: costKnown, costKind: costKind)
    }

    func testKnownCostIsUsedAsIs() {
        let claude = item(weekCost: 1160.38, costKnown: true, costKind: "notional")
        XCTAssertEqual(effectiveWeekCost(claude, price: nil), 1160.38)
    }

    /// ห้ามขึ้น $0.00 เพราะศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี"
    func testUnknownCostWithoutUserPriceIsNil() {
        XCTAssertNil(effectiveWeekCost(item(weekCost: nil, costKnown: false), price: nil))
        XCTAssertNil(costLabel(item(weekCost: nil, costKnown: false), price: nil))
    }

    func testUserPriceFillsTheGap() {
        let glm = item(weekCost: nil, costKnown: false, weekTokens: 2_000_000)
        let price = Price(inputPerMillion: 0.6, outputPerMillion: 2.2)
        // ไม่รู้สัดส่วนเข้า/ออก จึงใช้ค่าเฉลี่ยของสองอัตราเป็นตัวประมาณ
        XCTAssertEqual(effectiveWeekCost(glm, price: price) ?? 0, 2.8, accuracy: 0.001)
    }

    func testNotionalCostIsLabelledAsValueNotBill() {
        let claude = item(weekCost: 1160.38, costKnown: true, costKind: "notional")
        let label = try? XCTUnwrap(costLabel(claude, price: nil))
        XCTAssertEqual(label?.contains("มูลค่า"), true, "จ่ายเหมาแล้ว ไม่ใช่บิล")
    }

    func testPayPerUseCostIsLabelledAsSpent() {
        let glm = item(weekCost: nil, costKnown: false, weekTokens: 1_000_000)
        let label = try? XCTUnwrap(costLabel(glm, price: Price(inputPerMillion: 1,
                                                               outputPerMillion: 1)))
        XCTAssertEqual(label?.contains("ใช้ไป"), true, "เงินไหลจริง")
    }

    func testUserPriceOverridesTheBuiltInTable() {
        let claude = item(weekCost: 1160.38, costKnown: true, costKind: "notional",
                          weekTokens: 1_000_000)
        let price = Price(inputPerMillion: 2, outputPerMillion: 2)
        XCTAssertEqual(effectiveWeekCost(claude, price: price) ?? 0, 2.0, accuracy: 0.001,
                       "ราคาที่ผู้ใช้ใส่ต้องชนะตารางระบบ")
    }
}
```

- [ ] **Step 2: รันให้เห็นว่าพัง**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "error:" | head -3
```

Expected: `cannot find 'effectiveWeekCost' in scope`

- [ ] **Step 3: เขียนตรรกะราคา**

สร้าง `App/SettingsView.swift` แล้วเริ่มด้วยส่วนคำนวณ:

```swift
import SwiftUI

/// ค่าใช้จ่าย 7 วันของถังนี้ — nil แปลว่าไม่รู้ ห้ามแทนด้วย 0
///
/// ราคาที่ผู้ใช้ใส่เองชนะตารางในตัวเสมอ เพราะเขารู้บิลจริงของเขา
func effectiveWeekCost(_ item: UsageItem, price: Price?) -> Double? {
    if let price {
        // snapshot ไม่ได้แยก token เข้า/ออกในระดับสัปดาห์ จึงใช้ค่าเฉลี่ยของสองอัตรา
        let rate = (price.inputPerMillion + price.outputPerMillion) / 2
        return Double(item.weekTokens) / 1_000_000 * rate
    }
    return item.costKnown ? item.weekCost : nil
}

/// ข้อความค่าใช้จ่าย — แยกให้ชัดว่าเป็นมูลค่าหรือเงินที่ไหลจริง
func costLabel(_ item: UsageItem, price: Price?) -> String? {
    guard let cost = effectiveWeekCost(item, price: price) else { return nil }
    let kind = (price == nil && item.costKind == "notional") ? "มูลค่า" : "ใช้ไป"
    return kind + " $" + String(format: "%.2f", cost) + " / 7 วัน"
}
```

- [ ] **Step 4: เขียนหน้าตั้งค่า**

เพิ่มต่อในไฟล์เดิม:

```swift
struct SettingsView: View {
    @ObservedObject var model: UsageModel
    @State private var editing: String?
    @State private var inputText = ""
    @State private var outputText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("แสดง \(shown) จาก \(model.snapshot.items.count) ถัง")
                Spacer()
                Button("เปิดทั้งหมด") {
                    for item in model.snapshot.items {
                        model.prefs.setHidden(item.id, false)
                    }
                }
                .buttonStyle(.plain).foregroundStyle(.tint)
            }
            .font(.system(size: 11)).foregroundStyle(.secondary)
            .padding(.horizontal, 14).padding(.vertical, 10)
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(model.snapshot.items) { item in
                        row(item)
                        Divider()
                    }
                }
            }
        }
        .frame(width: 460, height: 480)
    }

    private var shown: Int {
        model.snapshot.items.filter { !model.prefs.hidden.contains($0.id) }.count
    }

    @ViewBuilder
    private func row(_ item: UsageItem) -> some View {
        let isHidden = model.prefs.hidden.contains(item.id)
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 10) {
                Toggle("", isOn: Binding(
                    get: { !isHidden },
                    set: { model.prefs.setHidden(item.id, !$0) }))
                    .labelsHidden()
                    .help(isHidden ? "แสดงถังนี้" : "ซ่อนถังนี้")

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(item.group).font(.system(size: 12.5, weight: .semibold))
                        Text("· \(item.label)").font(.system(size: 11))
                            .foregroundStyle(.secondary)
                        if let plan = item.plan {
                            Text(plan).font(.system(size: 9.5))
                                .padding(.horizontal, 5).padding(.vertical, 1)
                                .background(Color.secondary.opacity(0.15))
                                .clipShape(Capsule())
                        }
                    }
                    priceLine(item)
                }
                Spacer()
                if item.local != true {
                    Button(model.prefs.prices[item.id] == nil ? "ใส่ราคา" : "แก้ราคา") {
                        beginEditing(item)
                    }
                    .font(.system(size: 11))
                }
            }
            if editing == item.id { editor(item) }
        }
        .opacity(isHidden ? 0.5 : 1)
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    @ViewBuilder
    private func priceLine(_ item: UsageItem) -> some View {
        HStack(spacing: 6) {
            if item.local == true {
                Text("ในเครือข่ายตัวเอง · ไม่มีค่าใช้จ่าย").foregroundStyle(.secondary)
            } else if let price = model.prefs.prices[item.id] {
                Text(String(format: "$%.2f / $%.2f", price.inputPerMillion,
                            price.outputPerMillion)).monospaced()
                badge("ใส่เอง", .orange)
            } else if item.costKnown {
                Text("ตารางของ Anthropic").foregroundStyle(.secondary)
                if item.costKind == "notional" { badge("มูลค่า ไม่ใช่บิล", .secondary) }
            } else {
                Text("ยังไม่ได้ตั้งราคา").italic().foregroundStyle(.secondary)
            }
        }
        .font(.system(size: 11))
    }

    @ViewBuilder
    private func badge(_ text: String, _ tint: Color) -> some View {
        Text(text).font(.system(size: 9.5, weight: .medium))
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background(tint.opacity(0.18)).foregroundStyle(tint)
            .clipShape(Capsule())
    }

    @ViewBuilder
    private func editor(_ item: UsageItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                field("เข้า · USD / 1M", $inputText)
                field("ออก · USD / 1M", $outputText)
            }
            HStack(spacing: 10) {
                Button("บันทึก") { save(item) }.keyboardShortcut(.defaultAction)
                Button("ลบราคา") {
                    model.prefs.setPrice(item.id, nil); editing = nil
                }
                Button("ยกเลิก") { editing = nil }
                Spacer()
            }
            Text("ราคาผูกกับถัง ไม่ใช่โมเดล — ทุกโมเดลที่วิ่งผ่าน endpoint นี้กินกระเป๋าใบเดียวกัน")
                .font(.system(size: 10.5)).foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    @ViewBuilder
    private func field(_ label: String, _ text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
            TextField("0.00", text: text).frame(width: 90).monospaced()
        }
    }

    private func beginEditing(_ item: UsageItem) {
        let existing = model.prefs.prices[item.id]
        inputText = existing.map { String($0.inputPerMillion) } ?? ""
        outputText = existing.map { String($0.outputPerMillion) } ?? ""
        editing = item.id
    }

    private func save(_ item: UsageItem) {
        guard let input = Double(inputText), let output = Double(outputText),
              input >= 0, output >= 0 else { return }
        model.prefs.setPrice(item.id,
                             Price(inputPerMillion: input, outputPerMillion: output))
        editing = nil
    }
}
```

- [ ] **Step 5: กรองถังที่ซ่อนออกจากรายการหลัก และเปิดหน้าตั้งค่าได้**

ใน `App/PopoverView.swift` เปลี่ยนแหล่งของ `ForEach` ให้ข้ามถังที่ซ่อน:

```swift
    private var visibleItems: [UsageItem] {
        model.snapshot.items.filter { !model.prefs.hidden.contains($0.id) }
    }
```

แล้วเพิ่มปุ่มท้าย popover:

```swift
            Divider()
            HStack {
                Button("ตั้งค่า…") { model.showSettings = true }
                    .buttonStyle(.plain).font(.system(size: 11))
                Spacer()
            }
            .padding(.horizontal, 14).padding(.vertical, 8)
```

ใน `UsageModel` เพิ่ม `@Published var showSettings = false` และใน `PopoverView` ผูก:

```swift
        .sheet(isPresented: $model.showSettings) {
            VStack(spacing: 0) {
                SettingsView(model: model)
                Divider()
                HStack { Spacer(); Button("เสร็จ") { model.showSettings = false } }
                    .padding(10)
            }
        }
```

และให้แถวใน popover ใช้ `costLabel(item, price: model.prefs.prices[item.id])` แทนข้อความค่าใช้จ่ายเดิม

- [ ] **Step 6: รันเทสต์ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "Executed .* tests.*failures" | tail -1
```

Expected: `Executed 36 tests, with 0 failures`

- [ ] **Step 7: ดูด้วยตา**

```bash
python3 ai-usage.60s.py --snapshot
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -2
osascript -e 'quit app "AIUsage"' 2>/dev/null || true
open build/Build/Products/Release/AIUsage.app
```

ตรวจ: กด "ตั้งค่า…" แล้วเห็นทุกถังพร้อม path · ปิดถัง `กรอกเอง` แล้วมันหายจากรายการหลักแต่ยังอยู่ในหน้าตั้งค่า · ใส่ราคาให้ GLM แล้วรายการหลักขึ้น "ใช้ไป $…" · แถว Claude ขึ้น "มูลค่า $…" ไม่ใช่ "ใช้ไป" · **ไม่มีแถวไหนขึ้น `$0.00`** · ปิดเปิดแอปแล้วค่ายังอยู่

- [ ] **Step 8: Commit**

```bash
osascript -e 'quit app "AIUsage"' 2>/dev/null || true
git add App Tests
git commit -m "feat(app): settings sheet for hiding buckets and entering own prices"
```

---

### Task 5: ติดตั้งจริงและยืนยันว่าใช้ได้

โค้ดผ่านเทสต์ไม่ได้แปลว่าแอปทำงาน — ยังไม่เคยถูกติดตั้งลง `/Applications` เลยสักครั้ง

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `setup.sh` จากเฟส 1
- Produces: แอปที่ติดตั้งแล้วและเอกสารที่ตรงกับความจริง

- [ ] **Step 1: ติดตั้ง**

```bash
./setup.sh
```

Expected: จบด้วย `เสร็จแล้ว — <version> ทำงานอยู่บน menu bar` ถ้าค้างที่ "รอ snapshot ใหม่" ให้ดู `log stream --predicate 'process == "AIUsage"' --level error`

- [ ] **Step 2: ยืนยันว่าเป็นตัวใหม่จริง**

```bash
/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" /Applications/AIUsage.app/Contents/Info.plist
git rev-list --count HEAD
```

Expected: ตรงกัน

- [ ] **Step 3: ยืนยันว่า engine ใน bundle รันได้**

```bash
R=/Applications/AIUsage.app/Contents/Resources
ls "$R/ai-usage.60s.py" && ls "$R/engine/aiusage/buckets.py"
/usr/bin/env python3 "$R/ai-usage.60s.py" --json > /dev/null && echo "engine ใน bundle รันได้"
```

ถ้า `engine/aiusage/buckets.py` ไม่อยู่ ให้เปลี่ยน entry ใน `project.yml` เป็น folder reference แล้ว `xcodegen generate` ใหม่:

```yaml
      - path: engine
        buildPhase: resources
        type: folder
```

- [ ] **Step 4: รันซ้ำต้องไม่พัง**

```bash
./setup.sh && ./setup.sh
```

Expected: ผ่านทั้งสองรอบ · รอบสองไม่ค้างเพราะแอปเก่ายังเปิดอยู่

- [ ] **Step 5: แก้ CLAUDE.md ให้ตรงกับความจริง**

- "สิ่งที่ต้องทำ" — เปลี่ยนจาก "widget ปรากฏใน widget gallery" เป็น "ไอคอนปรากฏบน menu bar"
- โครงสร้าง — ลบ `Widget/AIUsageWidget.swift` และ `launchd/…plist` เพิ่ม `App/EngineRunner.swift` `App/MenuBarLabel.swift` `App/PopoverView.swift` `App/SettingsView.swift` `Shared/Freshness.swift` `Shared/Preferences.swift` `Shared/Appearance.swift` `engine/aiusage/`
- ข้อควรระวัง — ลบข้อ widgetkit-extension · เพิ่ม "แอปเรียก engine เอง ไม่ใช้ launchd" และ "ห้ามแสดง `$0.00` เมื่อ `costKnown` เป็น false"
- "ตรวจว่าใช้ได้จริง" — เปลี่ยน `tail /tmp/aiusage.err.log` เป็น `log stream --predicate 'process == "AIUsage"' --level error` และเพิ่ม `python3 -m unittest discover -s engine/tests` กับ `xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test`
- "ที่ยังทำไม่เสร็จ" — ลบข้อ `budget5h`/`budgetWeek` ที่ผู้ใช้ต้องกรอกเอง (ได้ % ทางการแล้ว) · เพิ่มว่า Qwen Cloud ยังไม่มีแหล่ง % และ GLM ไม่มี coding plan

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md project.yml
git commit -m "docs: align CLAUDE.md with the menu bar app as built"
```

---

## หลังจบแผนนี้

`python3 -m unittest discover -s engine/tests` และ `xcodebuild test` ต้องผ่านทั้งคู่ · `./setup.sh` จบด้วยไอคอนบนแถบเมนูที่แสดง % จริง · ปักหมุด ซ่อนถัง และใส่ราคาเองได้ครบ

**ที่ยังค้างและต้องการคำตอบจากผู้ใช้:**

1. **endpoint ของ dashboard Qwen Cloud** — หน่วยคือ Credits แผน Standard 3,000/10,000 แต่ Alibaba ไม่ประกาศสูตรแปลง token → credit และไม่มี API สาธารณะ ได้ URL มาเมื่อไหร่ Qwen Cloud ขึ้นชั้น "วัดได้จริง" ทันที
2. **บัญชี `work`** — เป็น Team tier แล้วไม่มี `cachedUsageUtilization` เลย ต้องเช็คซ้ำหลังใช้บัญชีนั้นว่าเพราะไม่ได้ใช้นาน หรือ Team ไม่ได้รับข้อมูลนี้
3. **GLM ถ้าต่ออายุ coding plan** — `GET https://api.z.ai/api/monitor/usage/quota/limit` จะคืนโควตาจริงทันที (ตอนนี้คืน `当前用户不存在coding plan`) โค้ดต้องรองรับทั้งสองแบบ

**งานที่รู้แล้วว่าต้องทำแต่ยังไม่มีในแผน:**

- แจ้งเตือนใกล้ชนลิมิต — ใช้ `severity` จาก Anthropic ไม่ต้องคิดเกณฑ์เอง
- โลโก้ provider จริงในแอป (simple-icons CC0 · lobe-icons MIT — ต้องแนบสัญญาอนุญาต MIT ในรีโป)
- เอา `[1308]` (GLM) และ `token-plan` (Qwen Cloud) กลับมาใช้ปรับเทียบ ตัวกรองปัจจุบันทิ้งของจริงทั้งคู่
