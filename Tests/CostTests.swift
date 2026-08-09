import XCTest
@testable import AIUsage

final class CostTests: XCTestCase {

    private func item(weekCost: Double?, costKnown: Bool, costKind: String? = nil,
                      weekTokens: Int = 0) -> UsageItem {
        UsageItem(group: "GLM", label: "default", window: "5 ชม.",
                  weekTokens: weekTokens, weekCost: weekCost,
                  costKnown: costKnown, costKind: costKind)
    }

    func testKnownCostIsUsedAsIs() {
        let claude = item(weekCost: 1160.38, costKnown: true, costKind: "notional")
        XCTAssertEqual(effectiveWeekCost(claude, price: nil), 1160.38)
    }

    /// ห้ามขึ้น $0.00 เพราะศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี"
    func testUnknownCostWithoutUserPriceIsNil() {
        XCTAssertNil(effectiveWeekCost(item(weekCost: nil, costKnown: false), price: nil))
        XCTAssertNil(costLabel(item(weekCost: nil, costKnown: false), price: nil))
    }

    func testUserPriceFillsTheGap() {
        let glm = item(weekCost: nil, costKnown: false, weekTokens: 2_000_000)
        let price = Price(inputPerMillion: 0.6, outputPerMillion: 2.2)
        // ไม่รู้สัดส่วนเข้า/ออก จึงใช้ค่าเฉลี่ยของสองอัตราเป็นตัวประมาณ
        XCTAssertEqual(effectiveWeekCost(glm, price: price) ?? 0, 2.8, accuracy: 0.001)
    }

    func testNotionalCostIsLabelledAsValueNotBill() {
        let claude = item(weekCost: 1160.38, costKnown: true, costKind: "notional")
        let label = try? XCTUnwrap(costLabel(claude, price: nil))
        XCTAssertEqual(label?.contains("มูลค่า"), true, "จ่ายเหมาแล้ว ไม่ใช่บิล")
    }

    func testPayPerUseCostIsLabelledAsSpent() {
        let glm = item(weekCost: nil, costKnown: false, weekTokens: 1_000_000)
        let label = try? XCTUnwrap(costLabel(glm, price: Price(inputPerMillion: 1,
                                                               outputPerMillion: 1)))
        XCTAssertEqual(label?.contains("ใช้ไป"), true, "เงินไหลจริง")
    }

    func testUserPriceOverridesTheBuiltInTable() {
        let claude = item(weekCost: 1160.38, costKnown: true, costKind: "notional",
                          weekTokens: 1_000_000)
        let price = Price(inputPerMillion: 2, outputPerMillion: 2)
        XCTAssertEqual(effectiveWeekCost(claude, price: price) ?? 0, 2.0, accuracy: 0.001,
                       "ราคาที่ผู้ใช้ใส่ต้องชนะตารางระบบ")
    }
}
