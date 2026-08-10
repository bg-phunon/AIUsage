import XCTest
@testable import AIUsage

final class FreshnessTests: XCTestCase {
    func testClassification() {
        XCTAssertEqual(freshness(snapshotAge: 0, wokeRecently: false), .fresh)
        XCTAssertEqual(freshness(snapshotAge: 181, wokeRecently: false), .stale)
        XCTAssertEqual(freshness(snapshotAge: 1801, wokeRecently: false), .dead)
        XCTAssertEqual(freshness(snapshotAge: nil, wokeRecently: false), .dead)
        XCTAssertEqual(freshness(snapshotAge: 8 * 3600, wokeRecently: true), .fresh)
    }

    func testCertaintyAndAgeText() {
        XCTAssertEqual(certainty(confidence: "valid"), .exact)
        XCTAssertEqual(certainty(confidence: "zero"), .exact)
        XCTAssertEqual(certainty(confidence: "lower_bound"), .atLeast)
        XCTAssertEqual(certainty(confidence: "unsure"), .unknown)
        XCTAssertEqual(ageText(45), "45s")
        XCTAssertEqual(ageText(18 * 60), "18m")
        XCTAssertEqual(ageText(2 * 3600), "2h")
    }

    // MARK: - เหตุผลที่ไม่มี %

    /// Claude ที่แคชเก่าจนหน้าต่างหมุนไปแล้ว — รู้ว่ามีเพดาน แค่ข้อมูลเก่า
    /// ต้องบอกวิธีแก้ ไม่ใช่บอกว่า "ยังไม่รู้เพดาน" ซึ่งผิดและไม่มีทางออก
    func testStaleQuotaTellsTheUserHowToFixIt() {
        let now = Date()
        let item = UsageItem(group: "Claude Code", label: "default", window: "5 ชม.",
                             tokens: 18_180_000, confidence: "unsure",
                             dataFetchedAt: now.addingTimeInterval(-53 * 3600))
        let reason = missingPercentReason(item, now: now)
        XCTAssertTrue(reason.contains("/usage"), "ต้องบอกว่าเปิด /usage แล้วจะกลับมามีตัวเลข")
        XCTAssertTrue(reason.contains(ageText(53 * 3600)), "ต้องบอกอายุด้วย")
        XCTAssertFalse(reason.contains("ยังไม่รู้เพดาน"), "รู้ว่ามีเพดาน อย่าบอกว่าไม่รู้")
    }

    /// Qwen Cloud / GLM — ไม่เคยมีแหล่งเพดานเลย บอกตามตรงและอย่าแนะนำ /usage
    func testNoQuotaSourceSaysSoPlainly() {
        let item = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.",
                             tokens: 2_400_000)
        let reason = missingPercentReason(item, now: Date())
        XCTAssertTrue(reason.contains("ยังไม่รู้เพดาน"))
        XCTAssertFalse(reason.contains("/usage"), "ถังนี้เปิด /usage ก็ไม่ช่วย")
    }

    func testBothReasonsKeepTheTokenCountVisible() {
        let now = Date()
        let stale = UsageItem(group: "Claude Code", label: "d", window: "5 ชม.",
                              tokens: 18_180_000,
                              dataFetchedAt: now.addingTimeInterval(-53 * 3600))
        let unknown = UsageItem(group: "GLM", label: "d", window: "5 ชม.",
                                tokens: 18_180_000)
        XCTAssertTrue(missingPercentReason(stale, now: now).hasPrefix("18.18M"))
        XCTAssertTrue(missingPercentReason(unknown, now: now).hasPrefix("18.18M"))
    }

    /// Codex อ่าน % มาจาก rate_limits ตรงๆ ไม่มีฟิลด์ confidence เลย
    /// ถ้าตีความ nil ว่า "ไม่รู้" ตัวเลข 99% ที่ถูกต้องจะถูกกลบเป็นขีด
    /// เคยพังมาแล้วเพราะเทสต์ไม่เคยครอบเคส nil
    func testMissingConfidenceIsExactNotUnknown() {
        XCTAssertEqual(certainty(confidence: nil), .exact)
        XCTAssertEqual(certainty(confidence: "ค่าที่ยังไม่รู้จัก"), .exact)
    }

    /// แถวที่ไม่มีตัวเลขต้องขึ้นขีดจาก pct == nil ไม่ใช่จาก certainty
    func testRowWithoutPercentStillHidesItsNumber() {
        let codex = UsageItem(group: "Codex", label: "Codex", window: "5 ชม.", pct: 99)
        let empty = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.")
        XCTAssertEqual(certainty(confidence: codex.confidence), .exact)
        XCTAssertNotNil(codex.pct)
        XCTAssertNil(empty.pct)
    }
}
