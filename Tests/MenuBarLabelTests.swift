import XCTest
@testable import AIUsage

final class MenuBarLabelTests: XCTestCase {
    private let now = Date()

    private func item(pct: Double?, weekPct: Double?, confidence: String? = "valid", error: String? = nil) -> UsageItem {
        UsageItem(group: "Claude Code", label: "default", window: "5 ชม.", pct: pct,
                  tokens: 0, cost: 0, calls: 0, resetAt: nil, weekTokens: 0,
                  weekCost: 0, weekPct: weekPct, profile: nil, plan: nil,
                  pctSource: pct == nil ? nil : "official", confidence: confidence,
                  dataFetchedAt: now.addingTimeInterval(-40 * 3600), severity: "normal",
                  activeLimit: nil, error: error, local: false)
    }

    private func snapshot(_ items: [UsageItem], generatedAgo: TimeInterval = 30) -> UsageSnapshot {
        UsageSnapshot(generated: now.addingTimeInterval(-generatedAgo), items: items)
    }

    func testExactAndLowerBoundNumbers() {
        let exact = menuBarText(snapshot: snapshot([item(pct: 5, weekPct: 96)]), now: now, wokeRecently: false)
        XCTAssertEqual(exact.top, "5h   5%")
        XCTAssertEqual(exact.bottom, "7d  96%")
        let lower = menuBarText(snapshot: snapshot([item(pct: 5, weekPct: 96, confidence: "lower_bound")]), now: now, wokeRecently: false)
        XCTAssertEqual(lower.top, "5h   5%")
        XCTAssertEqual(lower.bottom, "7d  96%")
    }

    func testStaleAndDeadSnapshot() {
        let stale = menuBarText(snapshot: snapshot([item(pct: 5, weekPct: 96)], generatedAgo: 18 * 60), now: now, wokeRecently: false)
        XCTAssertEqual(stale.bottom, "↻ 18m")
        XCTAssertTrue(stale.dimmed)
        let dead = menuBarText(snapshot: snapshot([item(pct: 5, weekPct: 96)], generatedAgo: 2 * 3600), now: now, wokeRecently: false)
        XCTAssertTrue(dead.top.contains("—"))
        XCTAssertTrue(dead.dimmed)
    }

    func testUnknownAndEmptyDoNotShowNumbers() {
        let unsure = menuBarText(snapshot: snapshot([item(pct: 5, weekPct: 96, confidence: "unsure")]), now: now, wokeRecently: false)
        XCTAssertTrue(unsure.top.contains("—"))
        let empty = menuBarText(snapshot: snapshot([]), now: now, wokeRecently: false)
        XCTAssertTrue(empty.dimmed)
    }

    func testErrorRowsAreIgnoredAndWakeGraceKeepsNumbers() {
        let value = menuBarText(snapshot: snapshot([item(pct: nil, weekPct: nil, error: "boom"), item(pct: 12, weekPct: 30)]), now: now, wokeRecently: false)
        XCTAssertEqual(value.top, "5h  12%")
        let awake = menuBarText(snapshot: snapshot([item(pct: 5, weekPct: 96)], generatedAgo: 8 * 3600), now: now, wokeRecently: true)
        XCTAssertEqual(awake.bottom, "7d  96%")
        XCTAssertFalse(awake.dimmed)
    }

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
        XCTAssertEqual(compactLine(item), "96%")
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
}
