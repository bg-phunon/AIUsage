# AI Usage — แผนลงมือ เฟส 3: ความหนาแน่นและการจัดคอลัมน์

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ให้ popover อ่านได้แบบกวาดตาลงคอลัมน์เหมือน OpenUsage — ทุกแถวสูงเท่ากัน คอลัมน์ตรงกัน · แถบเมนูโชว์ทุก provider พร้อมโลโก้เสมอไม่ว่าจะปักหมุดหรือไม่ · เลิกมีกลไกซ้ำซ้อนสองชุดที่ทำเรื่องเดียวกัน

**Architecture:** งานทั้งหมดอยู่ฝั่ง Swift **ไม่แตะเอนจิน Python และไม่แตะสัญญาของ `snapshot.json`** เป็นการจัดวางและรวมกลไกที่ซ้ำกัน ไม่ใช่การเพิ่มข้อมูล

**Tech Stack:** Swift 5 / SwiftUI / AppKit · XCTest · macOS 14+

## Global Constraints

- **ห้ามเปิด App Sandbox** · **ห้ามแก้ `ai-usage.60s.py` หรือ `engine/`**
- **ห้ามแสดง `$0.00` เมื่อ `costKnown` เป็น false** — ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี"
- **`lower_bound` สื่อด้วยแถบสองโซนอย่างเดียว** (ทึบถึงค่าที่รู้ แล้วจางต่อจนสุดราง)
  ตัวเลขไม่มีเครื่องหมายนำหน้า — ผู้ใช้ตัดสินใจว่า `≥` รกเกินไป
- **แถบ menu bar ไม่เกิน 10 ตัวอักษรต่อบรรทัด** ต่อ segment
- **โลโก้บนแถบเมนูต้องเป็น `isTemplate = true`** เสมอ ไม่งั้นมันไม่สลับขาว/ดำตามธีม
- ข้อความที่ผู้ใช้เห็นเป็น**ภาษาไทย** · ทุก task จบด้วย commit
- เทสต์ทั้งสองชุดต้องผ่านก่อน commit: `python3 -m unittest discover -s engine/tests -q` และ
  `xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test`
  **ตรวจบรรทัด `Test Suite 'All tests'` เสมอ** อย่าดูแค่ผลรายชุด — ผลรายชุดผ่านหมดทั้งที่รวมแล้วมีพังได้

**อ้างอิง:** OpenUsage (https://www.openusage.ai/) · สเปก `docs/superpowers/specs/2026-08-06-ai-usage-menubar-design.md`

---

## ข้อเท็จจริงที่ตรวจแล้ว (2026-08-10)

**OpenUsage ไม่ได้เรียบกว่าเรา — มันแน่นกว่า** เว็บระบุเองว่าเน้น "density and quick scanning"
เป็น SwiftUI native เหมือนกัน แถบเมนูโชว์หลาย provider พร้อมกัน (99% 63% 100% 81% 73% 98%)
ต่อ provider มี Session / Weekly / Last 30 Days พร้อมแถบ % เวลารีเซ็ต และค่าใช้จ่าย

**สิ่งที่เรามีอยู่แล้วและดีอยู่แล้ว:** `menuBarSegments()` ใน `App/MenuBarLabel.swift`
โชว์ทุก provider พร้อม **โลโก้แบรนด์จริงเป็น template image** — ตรงกับที่ต้องการอยู่แล้ว

**สิ่งที่ต้องแก้ เรียงตามความเสียหาย:**

1. **การปักหมุดเป็น regression** — `AIUsageApp.updateBar()` เมื่อ `pinned` ไม่ว่าง จะ
   `button.image = nil` แล้วเรนเดอร์เป็นข้อความล้วน **โลโก้หายทั้งแถบ** ผู้ใช้ที่ปักหมุด
   จะได้ `96% 92%` แทน `[โลโก้] 96%  [โลโก้] 92%` — แย่ลงกว่าไม่ปัก
2. **กลไกซ่อนมีสองชุดที่ทับกัน** — `model.visibleGroups` (ราย *group* สำหรับแถบเมนู เก็บใน
   `UserDefaults` คีย์ `visibleMenuBarProviders`) กับ `prefs.hidden` (ราย *bucket id* สำหรับ popover)
   ผู้ใช้ต้องเรียนรู้สองระบบที่ทำเรื่องเดียวกัน
3. **หน้าตั้งค่ามีสองบาน** — `settingsPresented` → `ProviderSettingsView` และ
   `showSettings` → `SettingsView` เปิดคนละที่ ตั้งค่าคนละครึ่ง
4. **แถวไม่เป็นตาราง** — บรรทัดข้อเท็จจริงกับป้ายสถานะยาวไม่เท่ากันและมีบ้างไม่มีบ้าง
   ความสูงแต่ละแถวจึงไม่เท่ากัน จังหวะการกวาดตาพัง

**ที่ยืนยันแล้วว่าทำไม่ได้:** ไม่มีหน้าต่าง 30 วันในข้อมูลของเรา
`cachedUsageUtilization` มีแค่ `five_hour` กับ `seven_day` (limits: session / weekly_all / weekly_scoped)
Codex ก็มีแค่ `pct` กับ `weekPct` — **อย่าวางแผนคอลัมน์ 30 วัน มันไม่มีข้อมูลรองรับ**

---

### Task 1: ปักหมุดต้องกรอง segment ไม่ใช่แทนที่การเรนเดอร์

**Files:**
- Modify: `App/MenuBarLabel.swift`
- Modify: `App/AIUsageApp.swift`
- Test: `Tests/MenuBarLabelTests.swift`

**Interfaces:**
- Consumes: `MenuBarSegment`, `menuBarSegments(snapshot:now:wokeRecently:visibleGroups:)`
- Produces: `menuBarSegments` เพิ่มพารามิเตอร์ `pinned: [String] = []` — เมื่อไม่ว่าง จะคืนเฉพาะ
  segment ที่มี bucket ถูกปักไว้ เรียงตามลำดับที่ผู้ใช้ปัก และคง `assetName` ไว้เสมอ

- [ ] **Step 1: เขียนเทสต์ที่ยังไม่ผ่าน**

เพิ่มลงท้ายคลาสใน `Tests/MenuBarLabelTests.swift`:

```swift
    // MARK: - หมุดต้องไม่ทำให้โลโก้หาย

    private func groupItem(_ group: String, _ label: String, pct: Double) -> UsageItem {
        UsageItem(group: group, label: label, window: "5 ชม.", pct: pct,
                  pctSource: "official", confidence: "valid",
                  dataFetchedAt: now.addingTimeInterval(-60), severity: "normal")
    }

    func testPinsFilterSegmentsAndKeepLogos() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       visibleGroups: ["Claude Code", "Codex"],
                                       pinned: ["Codex/Codex"])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
        XCTAssertFalse(segments[0].assetName.isEmpty, "โลโก้ต้องไม่หายตอนปักหมุด")
    }

    func testNoPinsShowsEveryVisibleGroup() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       visibleGroups: ["Claude Code", "Codex"], pinned: [])
        XCTAssertEqual(segments.count, 2, "ไม่ปัก = โชว์ทุกเจ้าที่เปิดไว้")
    }

    func testPinnedOrderDrivesSegmentOrder() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       visibleGroups: ["Claude Code", "Codex"],
                                       pinned: ["Codex/Codex", "Claude Code/default"])
        XCTAssertEqual(segments.map(\.group), ["Codex", "Claude Code"])
    }

    func testPinToAMissingBucketFallsBackToShowingEverything() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       visibleGroups: ["Claude Code"],
                                       pinned: ["GLM/ที่หายไป"])
        XCTAssertEqual(segments.count, 1, "ปักไปที่ถังที่ไม่มีแล้ว ต้องไม่ได้แถบว่าง")
    }
```

- [ ] **Step 2: รันให้เห็นว่าพัง**

```bash
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "error:" | head -3
```

Expected: `extra argument 'pinned' in call`

- [ ] **Step 3: เพิ่มพารามิเตอร์ pinned ให้ menuBarSegments**

ใน `App/MenuBarLabel.swift` แก้ลายเซ็นและเติมการกรองท้ายฟังก์ชัน — เก็บ logic เดิมทั้งหมดไว้
แล้วเพิ่มการเรียงลำดับตามหมุดเป็นขั้นสุดท้าย:

```swift
func menuBarSegments(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool,
                     visibleGroups: Set<String> = ["Claude Code", "Qwen Cloud", "GLM", "Codex"],
                     pinned: [String] = []) -> [MenuBarSegment] {
```

แล้วก่อน `return` ของฟังก์ชัน เปลี่ยนจากการคืน `definitions.compactMap { … }` ตรงๆ เป็น:

```swift
    let all: [MenuBarSegment] = definitions.compactMap { group, symbol, color in
        // …เนื้อในเดิม ไม่ต้องแก้…
    }
    guard !pinned.isEmpty else { return all }
    // หมุดเป็น "ตัวกรอง" ไม่ใช่ "โหมดใหม่" — โลโก้และการจัดวางต้องเหมือนเดิมทุกอย่าง
    let pinnedGroups = pinned.compactMap { id -> String? in
        snapshot.items.first { $0.id == id }?.group
    }
    let filtered = pinnedGroups.compactMap { group in all.first { $0.group == group } }
    return filtered.isEmpty ? all : filtered
}
```

- [ ] **Step 4: ให้ updateBar เลิกมีสองเส้นทาง**

ใน `App/AIUsageApp.swift` แทน `updateBar()` ทั้งตัว — เหลือเส้นทางเดียวที่วาด segment เสมอ:

```swift
    private func updateBar() {
        guard let button = statusItem.button else { return }
        let snapshot = model.snapshot
        // เส้นทางเดียว — ปักหมุดแค่กรองว่าจะโชว์ตัวไหน ไม่เปลี่ยนวิธีวาด
        let segments = menuBarSegments(snapshot: snapshot, now: Date(),
                                       wokeRecently: wokeRecently,
                                       visibleGroups: model.visibleGroups,
                                       pinned: model.prefs.pinned)
        let alert = hasUnpinnedCritical(snapshot: snapshot, pinned: model.prefs.pinned)
        button.attributedTitle = segmentTitle(segments, alert: alert)
        let age = snapshot.generated == .distantPast
            ? nil : Date().timeIntervalSince(snapshot.generated)
        button.alphaValue = freshness(snapshotAge: age, wokeRecently: wokeRecently) == .fresh
            ? 1.0 : 0.55
    }
```

ย้ายโค้ดที่ประกอบ `NSMutableAttributedString` จาก `updateBar()` เดิมไปเป็นฟังก์ชัน
`segmentTitle(_ segments: [MenuBarSegment], alert: Bool) -> NSAttributedString`
โดยเติมจุดเตือนไว้หน้าสุดเมื่อ `alert` เป็นจริง:

```swift
        if alert {
            title.append(NSAttributedString(string: "• ", attributes: [
                .font: font, .foregroundColor: NSColor.systemRed]))
        }
```

ลบ `stackedTitle`, `singleTitle` และการเรียก `menuBarUnits` / `compactLine` ออกจาก `AIUsageApp.swift`
(ฟังก์ชันใน `MenuBarLabel.swift` ยังอยู่ได้ เทสต์เดิมยังใช้)

- [ ] **Step 5: รันเทสต์ให้ผ่าน**

```bash
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test 2>&1 | grep -E "Test Suite 'All tests'|Executed [0-9]+ tests" | tail -2
```

Expected: `Test Suite 'All tests' passed` · `Executed 43 tests, with 0 failures`

- [ ] **Step 6: Commit**

```bash
git add App Tests
git commit -m "fix(ui): หมุดต้องกรอง segment ไม่ใช่ทิ้งโลโก้ทั้งแถบ"
```

---

### Task 2: รวมกลไกซ่อนสองชุดและหน้าตั้งค่าสองบานเป็นชุดเดียว

ตอนนี้ผู้ใช้ต้องเรียนรู้สองระบบที่ทำเรื่องเดียวกัน — `visibleGroups` ซ่อนราย group สำหรับแถบเมนู
ส่วน `prefs.hidden` ซ่อนราย bucket สำหรับ popover และเปิดจากคนละปุ่ม

**Files:**
- Modify: `App/AIUsageApp.swift`
- Modify: `App/PopoverView.swift`
- Modify: `App/SettingsView.swift`
- Delete: `ProviderSettingsView` (อยู่ในไฟล์ไหนให้ค้นด้วย `grep -rn "struct ProviderSettingsView" App`)
- Test: `Tests/PreferencesTests.swift`

**Interfaces:**
- Consumes: `Preferences`
- Produces:
  - `Preferences` เพิ่ม `func isVisible(_ id: String) -> Bool` (= `!hidden.contains(id)`)
  - `Preferences` เพิ่ม `func migrateVisibleGroups(_ defaults: UserDefaults, allItems: [UsageItem])`
    — อ่านคีย์เดิม `visibleMenuBarProviders` ครั้งเดียว แปลงเป็น `hidden` แล้วลบคีย์เดิมทิ้ง
  - `UsageModel` ตัด `visibleGroups` และ `settingsPresented` ออก เหลือ `showSettings` อย่างเดียว

- [ ] **Step 1: เขียนเทสต์การย้ายค่าเดิม**

เพิ่มใน `Tests/PreferencesTests.swift`:

```swift
    /// ผู้ใช้เคยตั้ง visibleMenuBarProviders ไว้ ต้องไม่หายตอนรวมกลไก
    func testMigratesOldVisibleGroupsIntoHidden() {
        defaults.set(["Claude Code", "Codex"], forKey: "visibleMenuBarProviders")
        let items = [
            UsageItem(group: "Claude Code", label: "default", window: "5 ชม."),
            UsageItem(group: "Codex", label: "Codex", window: "5 ชม."),
            UsageItem(group: "GLM", label: "default", window: "5 ชม."),
        ]
        let prefs = Preferences(defaults: defaults)
        prefs.migrateVisibleGroups(defaults, allItems: items)
        XCTAssertTrue(prefs.isVisible("Claude Code/default"))
        XCTAssertTrue(prefs.isVisible("Codex/Codex"))
        XCTAssertFalse(prefs.isVisible("GLM/default"), "group ที่เคยปิดไว้ต้องยังปิดอยู่")
    }

    func testMigrationRunsOnlyOnce() {
        defaults.set(["Claude Code"], forKey: "visibleMenuBarProviders")
        let items = [UsageItem(group: "GLM", label: "default", window: "5 ชม.")]
        let prefs = Preferences(defaults: defaults)
        prefs.migrateVisibleGroups(defaults, allItems: items)
        prefs.setHidden("GLM/default", false)          // ผู้ใช้เปิดคืนเอง
        prefs.migrateVisibleGroups(defaults, allItems: items)
        XCTAssertTrue(prefs.isVisible("GLM/default"), "ห้ามย้ายซ้ำแล้วทับสิ่งที่ผู้ใช้เพิ่งเลือก")
        XCTAssertNil(defaults.array(forKey: "visibleMenuBarProviders"))
    }

    func testMigrationWithNoOldKeyChangesNothing() {
        let prefs = Preferences(defaults: defaults)
        prefs.migrateVisibleGroups(defaults, allItems: [])
        XCTAssertTrue(prefs.hidden.isEmpty)
    }
```

- [ ] **Step 2: รันให้เห็นว่าพัง** — `value of type 'Preferences' has no member 'migrateVisibleGroups'`

- [ ] **Step 3: เขียน implementation ใน `Shared/Preferences.swift`**

```swift
    func isVisible(_ id: String) -> Bool { !hidden.contains(id) }

    /// ย้ายค่าจากกลไกเดิม (ซ่อนราย group สำหรับแถบเมนู) มาเป็น hidden ราย bucket
    /// ลบคีย์เดิมทิ้งหลังย้าย จะได้ไม่ทับสิ่งที่ผู้ใช้เลือกใหม่ในรอบถัดไป
    func migrateVisibleGroups(_ defaults: UserDefaults, allItems: [UsageItem]) {
        let key = "visibleMenuBarProviders"
        guard let visible = defaults.stringArray(forKey: key) else { return }
        let visibleSet = Set(visible)
        for item in allItems where !visibleSet.contains(item.group) {
            hidden.insert(item.id)
        }
        defaults.set(Array(hidden), forKey: Key.hidden)
        defaults.removeObject(forKey: key)
    }
```

- [ ] **Step 4: ให้ segment ใช้ hidden แทน visibleGroups**

ใน `menuBarSegments` เปลี่ยนพารามิเตอร์ `visibleGroups: Set<String>` เป็น `hidden: Set<String>`
แล้วเปลี่ยนเงื่อนไขจาก `guard visibleGroups.contains(group)` เป็นการกรองรายตัว:

```swift
        let candidates = snapshot.items.filter {
            $0.group == group && $0.error == nil && $0.local != true && !hidden.contains($0.id)
        }
```

แก้เทสต์ใน Task 1 ที่ส่ง `visibleGroups:` ให้ส่ง `hidden:` แทน (ค่าว่างคือโชว์หมด)

- [ ] **Step 5: เหลือหน้าตั้งค่าบานเดียว**

- ลบ `struct ProviderSettingsView` ทั้งตัว และ `.sheet(isPresented: $model.settingsPresented)`
- ลบ `@Published var settingsPresented` และ `@Published var visibleGroups` จาก `UsageModel`
- ปุ่มเฟือง (`gearshape`) ในหัว popover เปลี่ยนไปเปิด `model.showSettings = true`
- ลบปุ่มข้อความ "ตั้งค่า…" ท้าย popover ทิ้ง — มีสองทางเข้าไปที่เดียวกันไม่มีประโยชน์
- ถ้า `ProviderSettingsView` มีตัวเลือก `DesignStyle` อยู่ ให้ย้ายไปไว้ท้าย `SettingsView`

- [ ] **Step 6: เรียก migration ตอนเปิดแอป**

ใน `AppDelegate.applicationDidFinishLaunching` หลังโหลด snapshot ครั้งแรก:

```swift
        model.prefs.migrateVisibleGroups(.standard, allItems: model.snapshot.items)
```

- [ ] **Step 7: รันเทสต์ให้ผ่าน** — Expected `Executed 46 tests, with 0 failures`

- [ ] **Step 8: Commit**

```bash
git add App Shared Tests
git commit -m "refactor(ui): รวมกลไกซ่อนและหน้าตั้งค่าที่มีสองชุดให้เหลือชุดเดียว"
```

---

### Task 3: แถวเป็นตารางที่คอลัมน์ตรงกัน

นี่คือความต่างจริงจาก OpenUsage — ของเขาแต่ละหน้าต่างเป็นแถวในตาราง ป้ายซ้ายตรงกัน
แถบตรงกัน ตัวเลขตรงกัน เวลารีเซ็ตตรงกัน ตากวาดลงคอลัมน์ได้ ของเราเนื้อหาไหลไปเรื่อยและ
ความสูงไม่เท่ากันเพราะป้ายสถานะมีบ้างไม่มีบ้าง

**Files:**
- Modify: `App/PopoverView.swift`
- Test: `Tests/RowLayoutTests.swift`

**Interfaces:**
- Consumes: `UsageItem`, `Certainty`, `countdownText(to:from:)`
- Produces:
  - `struct WindowRow { let label: String; let pct: Double?; let sure: Certainty; let resetAt: Date? }`
  - `func windowRows(_ item: UsageItem) -> [WindowRow]` — คืนสองแถวเสมอ (`5h`, `7d`)
    ความยาวคงที่ทำให้ทุกการ์ดสูงเท่ากัน
  - `func rowFootnote(_ item: UsageItem, price: Price?, now: Date) -> String?`

- [ ] **Step 1: เขียนเทสต์**

สร้าง `Tests/RowLayoutTests.swift`:

```swift
import XCTest
@testable import AIUsage

final class RowLayoutTests: XCTestCase {

    func testAlwaysTwoWindowRowsSoCardsShareOneHeight() {
        let full = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             pct: 12, weekPct: 5, confidence: "valid", weekConfidence: "valid")
        let empty = UsageItem(group: "GLM", label: "default", window: "5 ชม.")
        XCTAssertEqual(windowRows(full).count, 2)
        XCTAssertEqual(windowRows(empty).count, 2, "ถังที่ไม่มีข้อมูลก็ต้องสูงเท่ากัน")
    }

    func testWindowRowsKeepTheirOwnCertainty() {
        let item = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             pct: 12, weekPct: 5,
                             confidence: "lower_bound", weekConfidence: "valid")
        let rows = windowRows(item)
        XCTAssertEqual(rows[0].sure, .atLeast)
        XCTAssertEqual(rows[1].sure, .exact)
    }

    func testLabelsAreFixedAndShort() {
        XCTAssertEqual(windowRows(UsageItem(group: "g", label: "l", window: "w")).map(\.label),
                       ["5h", "7d"])
    }

    /// เชิงอรรถต้องเป็นบรรทัดเดียวสั้นๆ ไม่ใช่ประโยคยาวที่ลากไปตัดบรรทัด
    func testFootnoteIsShortOrAbsent() {
        let item = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             tokens: 18_180_000, weekTokens: 2, weekCost: 1160.38,
                             costKnown: true, costKind: "notional")
        let note = rowFootnote(item, price: nil, now: Date())
        XCTAssertNotNil(note)
        XCTAssertLessThanOrEqual(note!.count, 44, "ยาวเกินจะตัดบรรทัดแล้วแถวสูงไม่เท่ากัน")
    }

    func testNoFootnoteWhenThereIsNothingToSay() {
        let bare = UsageItem(group: "spark", label: "spark", window: "5 ชม.", local: true)
        XCTAssertNil(rowFootnote(bare, price: nil, now: Date()))
    }

    func testFootnoteNeverShowsZeroDollars() {
        let unknown = UsageItem(group: "GLM", label: "default", window: "5 ชม.",
                                weekTokens: 1_000_000, costKnown: false)
        XCTAssertFalse((rowFootnote(unknown, price: nil, now: Date()) ?? "").contains("$0.00"))
    }
}
```

- [ ] **Step 2: รันให้เห็นว่าพัง** — `cannot find 'windowRows' in scope`

- [ ] **Step 3: เขียน implementation** — เพิ่มใน `App/PopoverView.swift` นอก `struct`

```swift
struct WindowRow {
    let label: String
    let pct: Double?
    let sure: Certainty
    let resetAt: Date?
}

/// สองแถวเสมอ ไม่ว่าถังนั้นจะมีข้อมูลหรือไม่ — ความสูงคงที่คือสิ่งที่ทำให้กวาดตาลงคอลัมน์ได้
func windowRows(_ item: UsageItem) -> [WindowRow] {
    [WindowRow(label: "5h", pct: item.pct,
               sure: certainty(confidence: item.confidence), resetAt: item.resetAt),
     WindowRow(label: "7d", pct: item.weekPct,
               sure: certainty(confidence: item.weekConfidence ?? item.confidence),
               resetAt: nil)]
}

/// บรรทัดเดียวใต้แถบ — สั้นพอที่จะไม่ตัดบรรทัด nil เมื่อไม่มีอะไรต้องบอก
func rowFootnote(_ item: UsageItem, price: Price?, now: Date) -> String? {
    if let error = item.error { return String(error.prefix(40)) }
    if item.local == true { return nil }
    var parts: [String] = []
    if item.tokens > 0 { parts.append(item.tokensText) }
    if let cost = costLabel(item, price: price) { parts.append(cost) }
    return parts.isEmpty ? nil : parts.joined(separator: " · ")
}
```

- [ ] **Step 4: วาดแถวใหม่เป็นตาราง**

ใน `row(_:)` แทนบล็อกของ `usageBar` สองบรรทัด บรรทัดข้อเท็จจริง และแถวป้ายสถานะ ด้วย:

```swift
                ForEach(windowRows(item), id: \.label) { window in
                    HStack(spacing: 8) {
                        Text(window.label)
                            .font(.system(size: 9, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .frame(width: 20, alignment: .leading)
                        bar(window, tint: item.tint)
                        Text(pctText(window.pct, window.sure))
                            .font(.system(size: 10, weight: .medium, design: .rounded))
                            .monospacedDigit()
                            .frame(width: 42, alignment: .trailing)
                        Text(window.resetAt == nil ? "" : countdownText(to: window.resetAt, from: now))
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                            .frame(width: 56, alignment: .trailing)
                    }
                    .frame(height: 16)
                }
                if let note = rowFootnote(item, price: prefs.prices[item.id], now: now) {
                    Text(note).font(.system(size: 10)).foregroundStyle(.secondary)
                        .lineLimit(1)
                } else {
                    Color.clear.frame(height: 13)   // กันที่ไว้ ทุกการ์ดจะได้สูงเท่ากัน
                }
```

`bar(_:tint:)` คือ `usageBar` เดิมที่ตัดส่วนป้ายกับตัวเลขออก เหลือแค่รางกับแถบ
(สองอย่างนั้นย้ายมาเป็นคอลัมน์ของตารางแล้ว)

- [ ] **Step 5: ย้ายเรื่องผิดปกติไปเป็นสัญญาณที่ไม่กินความสูง**

`statusFlags` ที่ทำไว้เฟสก่อนกินความสูงไม่เท่ากันในแต่ละแถว ให้เปลี่ยนเป็น:
- **ชนลิมิต** → จุดแดงเล็กหลังชื่อ provider + `.help()` บอกรายละเอียด
- **โควตาเก่า** → ไอคอน `arrow.clockwise` จางหลังชื่อ + `.help()` บอกให้เปิด `/usage`
- **ใช้ต่อหลังเช็ค** → แถบสองโซนสื่ออยู่แล้ว ไม่ต้องมีป้ายซ้ำ

ลบฟังก์ชัน `statusFlags` และ `StatusFlag` ทิ้งหลังย้ายครบ

- [ ] **Step 6: รันเทสต์ให้ผ่าน** — Expected `Executed 52 tests, with 0 failures`

- [ ] **Step 7: build แล้วติดตั้ง**

```bash
python3 ai-usage.60s.py --snapshot
./setup.sh
```

- [ ] **Step 8: Commit**

```bash
git add App Tests
git commit -m "feat(ui): แถวเป็นตารางที่คอลัมน์ตรงกันและทุกการ์ดสูงเท่ากัน"
```

---

## หลังจบแผนนี้

ทั้งสองชุดเทสต์ผ่าน · `./setup.sh` ติดตั้งแล้วแถบเมนูโชว์ทุก provider พร้อมโลโก้
ไม่ว่าจะปักหมุดหรือไม่ · popover ทุกการ์ดสูงเท่ากันและคอลัมน์ตรงกันลงมาทั้งรายการ

**ต้องให้ผู้ใช้ดูด้วยตา** — เครื่องนี้ไม่ให้สิทธิ์ screen recording จึงจับภาพยืนยันเองไม่ได้
ทุก task ที่แตะการแสดงผลต้องจบด้วยการให้ผู้ใช้เปิดดูจริง

**ที่ยังไม่ทำในแผนนี้:**

- **คอลัมน์ 30 วัน** — ยืนยันแล้วว่าไม่มีข้อมูลรองรับ ทั้ง Claude และ Codex มีแค่ 5 ชม. กับ 7 วัน
- **ตัดสไตล์ให้เลือกสามแบบเหลือแบบเดียว** — ควรทำ แต่ต้องให้ผู้ใช้เลือกก่อนว่าจะเก็บแบบไหน
- **แจ้งเตือนใกล้ชนลิมิต** ใช้ `severity` จาก Anthropic
