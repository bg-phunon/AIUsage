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

    // MARK: - ตำแหน่งป้ายบัญชีบนแถบเมนู

    /// ค่าเริ่มต้นคือใต้โลโก้ และการสลับต้องรอดข้าม restart
    func testTagBelowLogoDefaultsTrueAndPersists() {
        XCTAssertTrue(Preferences(defaults: defaults).tagBelowLogo)
        let prefs = Preferences(defaults: defaults)
        prefs.setTagBelowLogo(false)
        XCTAssertFalse(prefs.tagBelowLogo)
        XCTAssertFalse(Preferences(defaults: defaults).tagBelowLogo, "ต้องอ่านค่าที่ตั้งไว้กลับมาได้")
    }

    /// เปิดเองตอนเข้าระบบ: ค่าเริ่มต้นเปิด และการปิดต้องรอดข้าม restart
    func testLaunchAtLoginDefaultsTrueAndPersists() {
        XCTAssertTrue(Preferences(defaults: defaults).launchAtLogin)
        let prefs = Preferences(defaults: defaults)
        prefs.setLaunchAtLogin(false)
        XCTAssertFalse(Preferences(defaults: defaults).launchAtLogin)
    }

    // MARK: - ย้ายกลไก visibleMenuBarProviders เดิมมาเป็น hidden

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

    /// เครื่องที่เอนจินยังไม่เคยเขียน snapshot — ค่าเดิมของผู้ใช้ห้ามหายไปเฉยๆ
    /// ต้องเก็บคีย์ไว้รอรอบที่มี snapshot จริง ไม่ใช่ลบทิ้งทั้งที่ยังไม่ได้ย้ายอะไร
    func testMigrationWaitsForARealSnapshotBeforeDeletingTheOldKey() {
        defaults.set(["Claude Code"], forKey: "visibleMenuBarProviders")
        let prefs = Preferences(defaults: defaults)
        prefs.migrateVisibleGroups(defaults, allItems: [])
        XCTAssertEqual(defaults.stringArray(forKey: "visibleMenuBarProviders"),
                       ["Claude Code"], "คีย์เดิมต้องยังอยู่จนกว่าจะได้ย้ายจริง")

        let items = [UsageItem(group: "GLM", label: "default", window: "5 ชม.")]
        prefs.migrateVisibleGroups(defaults, allItems: items)
        XCTAssertFalse(prefs.isVisible("GLM/default"), "รอบที่มี snapshot แล้วต้องย้ายตามปกติ")
        XCTAssertNil(defaults.array(forKey: "visibleMenuBarProviders"))
    }
}
