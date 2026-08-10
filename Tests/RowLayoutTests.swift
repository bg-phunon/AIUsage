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
