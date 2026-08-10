import XCTest
@testable import AIUsage

final class RowLayoutTests: XCTestCase {

    func testWindowRowsAlwaysDescribeBothWindows() {
        // windowRows เป็นข้อมูลดิบ — สองหน้าต่างเสมอ ส่วนจะวาดกี่แถวเป็นเรื่องของ displayableWindows
        let full = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             pct: 12, weekPct: 5, confidence: "valid", weekConfidence: "valid")
        XCTAssertEqual(windowRows(full).count, 2)
    }

    /// แถวจุดประกับขีดไม่บอกอะไร — ถังไม่มีเลขต้องไม่ได้แถวตารางเลย (ไปเป็นบรรทัดเดียวแทน)
    func testOnlyWindowsWithRealNumbersAreDisplayed() {
        let full = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             pct: 12, weekPct: 5, confidence: "valid", weekConfidence: "valid")
        let halfKnown = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                                  pct: nil, weekPct: 5,
                                  confidence: "unsure", weekConfidence: "lower_bound")
        let empty = UsageItem(group: "GLM", label: "default", window: "5 ชม.")
        XCTAssertEqual(displayableWindows(full).count, 2)
        XCTAssertEqual(displayableWindows(halfKnown).map(\.label), ["7d"],
                       "หน้าต่างที่ unsure ต้องหาย เหลือเฉพาะที่มีเลขจริง")
        XCTAssertTrue(displayableWindows(empty).isEmpty)
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
