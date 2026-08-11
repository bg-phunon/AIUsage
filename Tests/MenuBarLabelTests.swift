import XCTest
@testable import AIUsage

final class MenuBarLabelTests: XCTestCase {
    private let now = Date()

    private func snapshot(_ items: [UsageItem], generatedAgo: TimeInterval = 30) -> UsageSnapshot {
        UsageSnapshot(generated: now.addingTimeInterval(-generatedAgo), items: items)
    }

    // MARK: - จุดแดงถังวิกฤตที่ไม่ได้ปัก

    private func named(_ group: String, _ label: String,
                       pct: Double?, weekPct: Double?,
                       severity: String? = "normal") -> UsageItem {
        UsageItem(group: group, label: label, window: "5 ชม.", pct: pct,
                  weekPct: weekPct, pctSource: "official", confidence: "valid",
                  weekConfidence: "valid",
                  dataFetchedAt: now.addingTimeInterval(-60), severity: severity)
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
        var broken = named("Claude Code", "work", pct: 96, weekPct: 96)
        broken.error = "OSError"
        let snap = snapshot([broken, named("Codex", "Codex", pct: 12, weekPct: 30)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
    }

    /// snapshot ตาย = เอนจินหยุดเดินไปนานแล้ว — เลขค้างเก่าห้ามแสร้งว่าเป็นปัจจุบัน
    /// และถังมี traffic ก็ห้ามขึ้นเป็นขีดด้วย เพราะขีดตอนตายแปลว่า "ยังเดินอยู่แต่ไม่มีเลข" ซึ่งโกหก
    func testDeadSnapshotDropsAllSegments() {
        var item = named("Codex", "Codex", pct: 99, weekPct: 30)
        item.weekTokens = 1_000_000
        let segments = menuBarSegments(snapshot: snapshot([item], generatedAgo: 2 * 3600),
                                       now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertTrue(segments.isEmpty)
    }

    func testUnsureConfidenceShowsNoNumber() {
        var item = named("Claude Code", "default", pct: 5, weekPct: 96)
        item.confidence = "unsure"
        item.weekConfidence = "unsure"
        let segments = menuBarSegments(snapshot: snapshot([item]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertTrue(segments.isEmpty, "ไม่แน่ใจ = ไม่มีเลข ไม่ใช่เลขมั่วๆ")
    }

    /// บัญชี ccs ที่แคชโควตาเก่าจนไม่มี % — ต้องยังเห็นบนแถบเป็นขีดคู่ ไม่ใช่ล่องหน
    /// เห็นทุกบัญชีคือเหตุผลข้อแรกของแอปนี้
    func testAccountWithTrafficButNoNumbersKeepsItsSlot() {
        var mooz = named("Claude Code", "mooz", pct: nil, weekPct: nil)
        mooz.confidence = "unsure"
        mooz.weekConfidence = "unsure"
        mooz.weekTokens = 60_000_000
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96), mooz])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.id), ["Claude Code/default", "Claude Code/mooz"])
        XCTAssertEqual(segments[1].top, "–")
        XCTAssertEqual(segments[1].bottom, "–")
        XCTAssertEqual(segments.map(\.tag), ["de", "mo"], "โลโก้ซ้ำต้องมีป้ายบอกบัญชี")
    }

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
                                       hidden: [],
                                       pinned: ["Codex/Codex"])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
        XCTAssertFalse(segments[0].assetName.isEmpty, "โลโก้ต้องไม่หายตอนปักหมุด")
    }

    func testNoPinsShowsEveryVisibleGroup() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertEqual(segments.count, 2, "ไม่ปัก = โชว์ทุกเจ้าที่เปิดไว้")
    }

    func testPinnedOrderDrivesSegmentOrder() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [],
                                       pinned: ["Codex/Codex", "Claude Code/default"])
        XCTAssertEqual(segments.map(\.group), ["Codex", "Claude Code"])
    }

    func testPinToAMissingBucketFallsBackToShowingEverything() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [],
                                       pinned: ["GLM/ที่หายไป"])
        XCTAssertEqual(segments.count, 1, "ปักไปที่ถังที่ไม่มีแล้ว ต้องไม่ได้แถบว่าง")
    }

    // MARK: - เลขซ้อนสองบรรทัดแบบ OpenUsage

    func testSegmentStacksBothWindows() {
        var item = groupItem("Claude Code", "default", pct: 6)
        item.weekPct = 100
        item.weekConfidence = "valid"
        let segments = menuBarSegments(snapshot: snapshot([item]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments[0].top, "6%")
        XCTAssertEqual(segments[0].bottom, "100%")
    }

    /// เลขเดี่ยวลอยๆ อ่านไม่ออกว่าเป็นหน้าต่างไหน — weekly มีที่ประจำคือบรรทัดล่างเสมอ
    func testMissingWindowShowsDashNotCollapse() {
        let codex = groupItem("Codex", "Codex", pct: 99)   // ไม่มี weekly → ขีด
        let segments = menuBarSegments(snapshot: snapshot([codex]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments[0].top, "99%")
        XCTAssertEqual(segments[0].bottom, "–")

        var qwen = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.",
                             weekPct: 100, pctSource: "official", weekConfidence: "valid")
        qwen.resetAt = now.addingTimeInterval(3600)
        let qsegs = menuBarSegments(snapshot: snapshot([qwen]), now: now,
                                    wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(qsegs[0].top, "–", "5h ไม่มีข้อมูล = ขีด ไม่ใช่เอา weekly ขึ้นบน")
        XCTAssertEqual(qsegs[0].bottom, "100%")
    }

    /// ขีด — บนแถบเมนูคือที่ที่เสียไปฟรีๆ ถังที่ไม่มีเลขให้ดูใน popover เอา
    func testSegmentWithNoNumbersIsDroppedFromTheBar() {
        let empty = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.")
        let real = groupItem("Codex", "Codex", pct: 99)
        let segments = menuBarSegments(snapshot: snapshot([empty, real]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
    }

    /// หลายบัญชี ccs คือเหตุผลข้อแรกของแอปนี้ — แต่ละบัญชีต้องได้ segment ของตัวเอง
    func testEachClaudeAccountGetsItsOwnSegment() {
        var mooz = groupItem("Claude Code", "mooz", pct: 27)
        mooz.weekPct = 27; mooz.weekConfidence = "valid"
        let segments = menuBarSegments(snapshot: snapshot([groupItem("Claude Code", "default", pct: 96), mooz]),
                                       now: now, wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.id), ["Claude Code/default", "Claude Code/mooz"])
        XCTAssertEqual(segments.map(\.tag), ["de", "mo"], "โลโก้ซ้ำกันต้องมีป้ายบัญชี")
    }

    func testSingleAccountNeedsNoTag() {
        let segments = menuBarSegments(snapshot: snapshot([groupItem("Codex", "Codex", pct: 99)]),
                                       now: now, wokeRecently: false, hidden: [], pinned: [])
        XCTAssertNil(segments[0].tag)
    }

    // MARK: - ลำดับที่ผู้ใช้จัดเอง

    func testUserOrderRearrangesSegments() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [],
                                       order: ["Codex/Codex", "Claude Code/default"])
        XCTAssertEqual(segments.map(\.id), ["Codex/Codex", "Claude Code/default"])
    }

    /// ถังใหม่ที่เพิ่งงอก (ยังไม่เคยถูกจัด) ต้องต่อท้าย ไม่แทรกมั่วและไม่หาย
    func testUnknownIdsAppendAfterOrderedOnes() {
        let items = [groupItem("Claude Code", "default", pct: 96),
                     groupItem("Codex", "Codex", pct: 92),
                     groupItem("Qwen Cloud", "default", pct: 50)]
        let ordered = applyUserOrder(items, order: ["Codex/Codex"]) { $0.id }
        XCTAssertEqual(ordered.map(\.id),
                       ["Codex/Codex", "Claude Code/default", "Qwen Cloud/default"])
    }
}
