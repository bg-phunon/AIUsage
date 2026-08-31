import XCTest
@testable import AIUsage

final class RowLayoutTests: XCTestCase {

    func testWindowRowsAlwaysDescribeBothWindows() {
        // windowRows เป็นข้อมูลดิบ — สองหน้าต่างหลักเสมอ ส่วนจะวาดกี่แถวเป็นเรื่องของ displayableWindows
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

    // MARK: - gauge เฉพาะโมเดล (เช่น Fable)

    /// gauge ของ Fable ต้องได้แถวของตัวเองต่อท้าย 5h/7d ไม่ถูกกลืนหายไปใน 7d
    func testModelGaugeGetsItsOwnRow() {
        let item = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             pct: 12, weekPct: 5, confidence: "valid", weekConfidence: "valid",
                             modelWindows: [ModelWindow(label: "Fable", pct: 30,
                                                        resetAt: Date().addingTimeInterval(3600),
                                                        confidence: "valid")])
        let rows = displayableWindows(item)
        XCTAssertEqual(rows.map(\.label), ["5h", "7d", "Fable"])
        XCTAssertEqual(rows[2].pct, 30)
        XCTAssertEqual(rows[2].sure, .exact)
    }

    /// snapshot เก่าที่ไม่มีฟิลด์ modelWindows ต้องถอดรหัสได้เหมือนเดิม
    func testDecodingWithoutModelWindowsStillWorks() {
        let json = """
        {"generated": "2026-08-12T00:00:00Z", "items": [
          {"group": "Claude Code", "label": "d", "window": "5h",
           "tokens": 1, "calls": 0, "weekTokens": 1}]}
        """.data(using: .utf8)!
        let snap = UsageSnapshot.decode(from: json)
        XCTAssertNotNil(snap)
        XCTAssertEqual(snap?.items.first?.modelWindows, [])
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

    /// Qwen Cloud ตอน weekly เต็ม: 5h ไม่มีข้อมูล เวลารีเซ็ตต้องไปอยู่แถว 7d
    func testResetTimeFollowsTheRowThatHasData() {
        let reset = Date().addingTimeInterval(3600)
        let qwen = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.",
                             pct: nil, resetAt: reset, weekPct: 100,
                             pctSource: "official", weekConfidence: "valid")
        let rows = windowRows(qwen)
        XCTAssertNil(rows[0].resetAt)
        XCTAssertEqual(rows[1].resetAt, reset)

        let claude = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                               pct: 12, resetAt: reset, weekPct: 96,
                               confidence: "valid", weekConfidence: "valid")
        XCTAssertEqual(windowRows(claude)[0].resetAt, reset, "มี 5h อยู่แล้ว เกาะที่เดิม")
    }

    /// Codex/Claude ส่งเวลารีเซ็ตมาสองอัน — แถว 7d ต้องใช้ของตัวเอง ไม่ใช่ว่างเปล่า
    func testWeekRowUsesItsOwnResetTime() {
        let fiveHour = Date().addingTimeInterval(3600)
        let sevenDay = Date().addingTimeInterval(6 * 86400)
        let codex = UsageItem(group: "Codex", label: "Codex", window: "5 ชม.",
                              pct: 0, resetAt: fiveHour, weekPct: 14,
                              weekResetAt: sevenDay, pctSource: "official",
                              confidence: "valid", weekConfidence: "valid")
        let rows = windowRows(codex)
        XCTAssertEqual(rows[0].resetAt, fiveHour)
        XCTAssertEqual(rows[1].resetAt, sevenDay, "แถว 7d ไม่มีวันรีเซ็ตให้ดู")
    }

    /// ถังที่มีเวลารีเซ็ตอันเดียวและเป็นของสัปดาห์ (Qwen Cloud) ต้องไม่เสียพฤติกรรมเดิม
    func testWeekRowStillFallsBackWhenThereIsOnlyOneResetTime() {
        let reset = Date().addingTimeInterval(3600)
        let qwen = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.",
                             pct: nil, resetAt: reset, weekPct: 100,
                             weekResetAt: nil, pctSource: "official", weekConfidence: "valid")
        XCTAssertEqual(windowRows(qwen)[1].resetAt, reset)
    }

    /// snapshot เก่าที่ไม่มีฟิลด์ weekResetAt ต้องถอดรหัสได้เหมือนเดิม
    func testDecodingWithoutWeekResetAtStillWorks() {
        let json = """
        {"generated": "2026-08-12T00:00:00Z", "items": [
          {"group": "Codex", "label": "Codex", "window": "5h",
           "tokens": 1, "calls": 0, "weekTokens": 1}]}
        """.data(using: .utf8)!
        let snap = UsageSnapshot.decode(from: json)
        XCTAssertNotNil(snap)
        XCTAssertNil(snap?.items.first?.weekResetAt)
    }
}
