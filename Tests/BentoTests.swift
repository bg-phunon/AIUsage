import XCTest
@testable import AIUsage

/// การ์ดใหญ่ต้องเป็นตัวที่จะชนก่อน — ไม่งั้นหน้าแรกโชว์ของที่ไม่ต้องรีบดู
final class BentoTests: XCTestCase {
    private func item(_ label: String, pct: Double? = nil, week: Double? = nil) -> UsageItem {
        var it = UsageItem(group: "Claude Code", label: label, window: "5 ชม.")
        it.pct = pct
        it.weekPct = week
        it.confidence = "valid"
        it.weekConfidence = "valid"
        return it
    }

    func testHeadlineIsTheFullestWindow() {
        XCTAssertEqual(headlinePct(item("a", pct: 4, week: 46)), 46)
        XCTAssertNil(headlinePct(item("none")))
    }

    func testHeroIsTheClosestToTheLimit() {
        let items = [item("a", pct: 4, week: 46), item("b", week: 100), item("c", pct: 10)]
        XCTAssertEqual(heroItem(items, selected: nil)?.label, "b")
    }

    func testAPickedTileWins() {
        let items = [item("a", pct: 4, week: 46), item("b", week: 100)]
        XCTAssertEqual(heroItem(items, selected: items[0].id)?.label, "a")
    }

    func testBucketsWithoutPercentNeverBecomeTheHero() {
        XCTAssertNil(heroItem([item("none")], selected: nil))
    }

    func testColourOnlyWhenItMatters() {
        XCTAssertEqual(severity(79), .calm)
        XCTAssertEqual(severity(80), .warn)
        XCTAssertEqual(severity(95), .critical)
        XCTAssertEqual(severity(nil), .calm)
    }

    func testShortCountdown() {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        XCTAssertEqual(shortCountdown(now.addingTimeInterval(3 * 86_400 + 5), now: now), "3ว")
        XCTAssertEqual(shortCountdown(now.addingTimeInterval(2 * 3_600), now: now), "2ช")
        XCTAssertEqual(shortCountdown(now.addingTimeInterval(-1), now: now), "—")
    }

    func testCompactTokens() {
        XCTAssertEqual(compactTokens(166_180_000), "166M")
        XCTAssertEqual(compactTokens(7_660_000), "7.7M")
        XCTAssertEqual(compactTokens(2_400_000_000), "2.4B")
    }

    func testResetDetailsSayWhatIsKnown() {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        var it = item("default")
        XCTAssertTrue(resetDetailLines(it, now: now)[0].contains("ไม่ได้จดสถานะ"))
        it.limitResets = 1; it.limitResetsAtLeast = true
        XCTAssertTrue(resetDetailLines(it, now: now)[0].contains("อย่างน้อย 1 ใบ"))
        XCTAssertTrue(resetDetailLines(it, now: now).last!.contains("/limit-reset"))
        var codex = UsageItem(group: "Codex", label: "Codex", window: "5h")
        codex.limitResets = 2
        codex.limitResetsExpiring = [now.addingTimeInterval(86_400), now.addingTimeInterval(172_800)]
        let lines = resetDetailLines(codex, now: now)
        XCTAssertEqual(lines.count, 3)
        XCTAssertTrue(lines[0].hasPrefix("ใบที่ 1"))
        codex.limitResets = 0; codex.limitResetsExpiring = []
        XCTAssertEqual(resetDetailLines(codex, now: now), ["ไม่มีใบให้ใช้ตอนนี้"])
    }
}
