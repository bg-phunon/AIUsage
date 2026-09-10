import XCTest
@testable import AIUsage

/// เตือนตอนใกล้ชนลิมิต — ของที่ CLAUDE.md ค้างไว้ในหัวข้อ "ที่ยังทำไม่เสร็จ"
///
/// กติกาที่ยากกว่าการเทียบตัวเลข คือการไม่กวน: เอนจินรันทุก 60 วินาที ถ้าเตือนทุกครั้ง
/// ที่เห็น 95% ผู้ใช้จะโดนเด้ง 60 ครั้งต่อชั่วโมงแล้วปิดการแจ้งเตือนทิ้งถาวร
final class LimitNotifierTests: XCTestCase {
    private let reset = Date(timeIntervalSince1970: 1_800_000_000)

    private func item(_ label: String, pct: Double? = nil, confidence: String? = nil,
                      weekPct: Double? = nil, weekConfidence: String? = nil,
                      resetAt: Date? = nil, weekResetAt: Date? = nil) -> UsageItem {
        var it = UsageItem(group: "Claude Code", label: label, window: "5 ชม.")
        it.pct = pct
        it.confidence = confidence
        it.weekPct = weekPct
        it.weekConfidence = weekConfidence
        it.resetAt = resetAt
        it.weekResetAt = weekResetAt
        return it
    }

    // MARK: - ควรเตือนเมื่อไหร่

    func testQuietBelowTheFirstThreshold() {
        let alerts = pendingLimitAlerts(items: [item("work", pct: 79, resetAt: reset)], alreadySent: [])
        XCTAssertTrue(alerts.isEmpty)
    }

    func testAlertsOnceTheBucketCrossesEighty() {
        let alerts = pendingLimitAlerts(items: [item("work", pct: 80, resetAt: reset)], alreadySent: [])
        XCTAssertEqual(alerts.count, 1)
        XCTAssertTrue(alerts[0].body.contains("80"))
        XCTAssertTrue(alerts[0].title.contains("work"))
    }

    /// ข้ามจาก 0 ไป 96 ในรอบเดียว — ต้องได้ใบเดียวคือขั้นสูงสุด ไม่ใช่สองใบซ้อน
    func testJumpingPastBothThresholdsOnlyAlertsTheHigherOne() {
        let alerts = pendingLimitAlerts(items: [item("work", pct: 96, resetAt: reset)], alreadySent: [])
        XCTAssertEqual(alerts.count, 1)
        XCTAssertTrue(alerts[0].body.contains("95"), "ควรรายงานขั้นที่ร้ายแรงที่สุดที่ข้ามมา")
    }

    func testWeeklyWindowIsWatchedToo() {
        let alerts = pendingLimitAlerts(
            items: [item("work", weekPct: 97, weekResetAt: reset)], alreadySent: [])
        XCTAssertEqual(alerts.count, 1)
        XCTAssertTrue(alerts[0].body.contains("7d"))
    }

    // MARK: - ไม่กวน

    func testTheSameThresholdIsNeverSentTwiceInOneWindow() {
        let items = [item("work", pct: 96, resetAt: reset)]
        let first = pendingLimitAlerts(items: items, alreadySent: [])
        let second = pendingLimitAlerts(items: items, alreadySent: [first[0].key])
        XCTAssertTrue(second.isEmpty, "รันทุก 60 วิ ถ้าเตือนซ้ำผู้ใช้จะปิดการแจ้งเตือนทิ้ง")
    }

    /// หน้าต่างใหม่ = โควตาก้อนใหม่ ต้องเตือนได้อีก กุญแจจึงผูกกับเวลารีเซ็ต
    func testANewWindowRearmsTheSameThreshold() {
        let old = pendingLimitAlerts(items: [item("work", pct: 96, resetAt: reset)], alreadySent: [])
        let next = pendingLimitAlerts(
            items: [item("work", pct: 96, resetAt: reset.addingTimeInterval(18_000))],
            alreadySent: [old[0].key])
        XCTAssertEqual(next.count, 1)
    }

    func testCrossingTheHigherStepStillAlertsAfterTheLowerOneWasSent() {
        let at80 = pendingLimitAlerts(items: [item("work", pct: 82, resetAt: reset)], alreadySent: [])
        let at95 = pendingLimitAlerts(items: [item("work", pct: 96, resetAt: reset)],
                                      alreadySent: [at80[0].key])
        XCTAssertEqual(at95.count, 1)
        XCTAssertTrue(at95[0].body.contains("95"))
    }

    // MARK: - เลขที่เชื่อไม่ได้ ห้ามเตือน

    func testNeverAlertsFromANumberMarkedUnsure() {
        let alerts = pendingLimitAlerts(
            items: [item("work", pct: 99, confidence: "unsure", resetAt: reset)], alreadySent: [])
        XCTAssertTrue(alerts.isEmpty, "unsure แปลว่าตอบไม่ได้ — เตือนจากมันคือการเดา")
    }

    /// lower_bound แปลว่า "อย่างน้อยเท่านี้" ของจริงมีแต่จะสูงกว่า — เตือนได้
    func testALowerBoundThatAlreadyCrossedIsWorthAlerting() {
        let alerts = pendingLimitAlerts(
            items: [item("work", pct: 96, confidence: "lower_bound", resetAt: reset)],
            alreadySent: [])
        XCTAssertEqual(alerts.count, 1)
    }

    func testMissingPercentIsSilent() {
        XCTAssertTrue(pendingLimitAlerts(items: [item("work", resetAt: reset)], alreadySent: []).isEmpty)
    }

    func testEachBucketIsTrackedSeparately() {
        let alerts = pendingLimitAlerts(
            items: [item("work", pct: 96, resetAt: reset), item("mooz", pct: 96, resetAt: reset)],
            alreadySent: [])
        XCTAssertEqual(Set(alerts.map(\.key)).count, 2)
    }
}
