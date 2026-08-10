import Foundation

/// ราคาที่ผู้ใช้ใส่เอง — ผูกกับ "ถัง" ไม่ใช่โมเดล
/// เพราะทุกโมเดลที่วิ่งผ่าน endpoint เดียวกันกินกระเป๋าใบเดียวกัน
struct Price: Codable, Equatable {
    var inputPerMillion: Double
    var outputPerMillion: Double
}

/// ตัวเลือกของผู้ใช้ ไม่ปนกับข้อมูลใน snapshot
///
/// snapshot คือความจริงที่วัดได้ · ที่นี่คือความชอบส่วนตัว
/// แยกกันไว้เอนจินจะได้ไม่ต้องรู้จักคำว่า "ปักหมุด" เลย
final class Preferences: ObservableObject {
    static let maxPins = 4

    private enum Key {
        static let pinned = "pinned"
        static let hidden = "hidden"
        static let prices = "prices"
    }

    private let defaults: UserDefaults

    @Published private(set) var pinned: [String]
    @Published private(set) var hidden: Set<String>
    @Published private(set) var prices: [String: Price]

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        pinned = (defaults.array(forKey: Key.pinned) as? [String]) ?? []
        hidden = Set((defaults.array(forKey: Key.hidden) as? [String]) ?? [])
        prices = Self.decodePrices(defaults.data(forKey: Key.prices))
    }

    var maxPins: Int { Self.maxPins }

    /// ตัวที่ปักแล้วต้องปลดได้เสมอ ไม่งั้นผู้ใช้จะติดกับตอนปักครบ 4
    func canPin(_ id: String) -> Bool {
        pinned.contains(id) || pinned.count < Self.maxPins
    }

    func togglePin(_ id: String) {
        if let index = pinned.firstIndex(of: id) {
            pinned.remove(at: index)
        } else if pinned.count < Self.maxPins {
            pinned.append(id)
        } else {
            return
        }
        defaults.set(pinned, forKey: Key.pinned)
    }

    func clearPins() {
        pinned = []
        defaults.set(pinned, forKey: Key.pinned)
    }

    func setHidden(_ id: String, _ isHidden: Bool) {
        if isHidden { hidden.insert(id) } else { hidden.remove(id) }
        defaults.set(Array(hidden), forKey: Key.hidden)
    }

    func isVisible(_ id: String) -> Bool { !hidden.contains(id) }

    /// ย้ายค่าจากกลไกเดิม (ซ่อนราย group สำหรับแถบเมนู) มาเป็น hidden ราย bucket
    /// ลบคีย์เดิมทิ้งหลังย้าย จะได้ไม่ทับสิ่งที่ผู้ใช้เลือกใหม่ในรอบถัดไป
    func migrateVisibleGroups(_ defaults: UserDefaults, allItems: [UsageItem]) {
        let key = "visibleMenuBarProviders"
        guard let visible = defaults.stringArray(forKey: key) else { return }
        let visibleSet = Set(visible)
        for item in allItems where !visibleSet.contains(item.group) {
            hidden.insert(item.id)
        }
        defaults.set(Array(hidden), forKey: Key.hidden)
        defaults.removeObject(forKey: key)
    }

    func setPrice(_ id: String, _ price: Price?) {
        if let price { prices[id] = price } else { prices.removeValue(forKey: id) }
        defaults.set(try? JSONEncoder().encode(prices), forKey: Key.prices)
    }

    private static func decodePrices(_ data: Data?) -> [String: Price] {
        guard let data,
              let decoded = try? JSONDecoder().decode([String: Price].self, from: data)
        else { return [:] }
        return decoded
    }
}
