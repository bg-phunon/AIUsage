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
}
