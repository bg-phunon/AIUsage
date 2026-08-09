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
}
