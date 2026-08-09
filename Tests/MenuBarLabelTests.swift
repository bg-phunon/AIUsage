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
        XCTAssertEqual(lower.top, "5h  ≥5%")
        XCTAssertEqual(lower.bottom, "7d ≥96%")
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
}
