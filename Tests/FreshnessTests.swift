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
