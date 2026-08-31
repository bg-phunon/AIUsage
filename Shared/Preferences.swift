import Foundation

/// ราคาที่ผู้ใช้ใส่เอง — ผูกกับ "ถัง" ไม่ใช่โมเดล
/// เพราะทุกโมเดลที่วิ่งผ่าน endpoint เดียวกันกินกระเป๋าใบเดียวกัน
struct Price: Codable, Equatable {
    var inputPerMillion: Double
    var outputPerMillion: Double
}

/// แถบเมนูยอมเสียอะไรเมื่อพื้นที่ไม่พอ
///
/// จอมีรอยบากเหลือที่ให้ status item ของทุกแอปรวมกันแค่ 772 pt (วัดจาก
/// `NSScreen.auxiliaryTopRightArea` ของ MacBook 16") ของเรากิน 295.6 pt = 38%
/// เกินเมื่อไหร่ macOS ซ่อนตัวที่อยู่ซ้ายสุดไว้ใต้รอยบาก — ของเราหายก่อนเพราะกว้างสุด
///
/// วัดด้วยเมตริกฟอนต์จริงแล้วมีสามอย่างเท่านั้นที่ลดความกว้างได้: ตัดเครื่องหมาย %
/// (−54 pt) · บีบช่องไฟ (−20 pt) · โชว์ถังน้อยลง (−99 pt) ส่วน "ตัดป้ายบัญชี" กับ
/// "ยุบเหลือบรรทัดเดียว" กลับ *กว้างขึ้น* 19 pt เพราะป้ายอยู่ใต้โลโก้อยู่แล้วไม่กิน
/// แนวนอน และบรรทัดเดียวใช้ฟอนต์ 11.5 แทน 9.5 — จึงไม่มีอยู่ในทางเลือกไหนเลย
enum BarDensity: String, CaseIterable, Identifiable {
    case full, snug, minimal

    var id: String { rawValue }

    var title: String {
        switch self {
        case .full: return "เต็ม"
        case .snug: return "กระชับ"
        case .minimal: return "น้อยที่สุด"
        }
    }

    var subtitle: String {
        switch self {
        case .full: return "ทุกถัง พร้อมเครื่องหมาย % · 296 pt"
        case .snug: return "ทุกถัง ตัด % และบีบช่องไฟ · 221 pt"
        case .minimal: return "กระชับ + เหลือ 3 ถังแรก · 151 pt"
        }
    }

    /// จำนวนถังสูงสุดบนแถบ — nil คือไม่จำกัด
    var bucketLimit: Int? { self == .minimal ? 3 : nil }
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
        static let tagBelowLogo = "tagBelowLogo"
        static let launchAtLogin = "launchAtLogin"
        static let order = "bucketOrder"
        static let barDensity = "barDensity"
    }

    private let defaults: UserDefaults

    @Published private(set) var pinned: [String]
    @Published private(set) var hidden: Set<String>
    @Published private(set) var prices: [String: Price]
    /// ป้ายบัญชี (de/mo/wo) อยู่ใต้โลโก้หรือข้างโลโก้ — ใต้ประหยัดที่แนวนอนกว่า
    @Published private(set) var tagBelowLogo: Bool
    /// เปิดแอปเองตอนเข้าระบบ — ค่าเริ่มต้นเปิด เพราะ widget โควตาที่ต้องเปิดเอง
    /// ทุกเช้าคือ widget ที่จะถูกลืม (การ register จริงอยู่ที่ LaunchAtLogin ฝั่งแอป)
    @Published private(set) var launchAtLogin: Bool
    /// ลำดับถังที่ผู้ใช้จัดเอง — คุมทั้ง popover และแถบเมนู ว่าง = ตามเอนจิน
    @Published private(set) var order: [String]
    /// แถบเมนูกะทัดรัดแค่ไหน — ไม่ตรวจจอให้เอง เพราะจอนอกกับจอในเครื่องคนละเรื่อง
    /// และการสลับเองตอนต่อจอชัดเจนกว่าการเดาแล้วเดาผิด
    @Published private(set) var barDensity: BarDensity

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        pinned = (defaults.array(forKey: Key.pinned) as? [String]) ?? []
        hidden = Set((defaults.array(forKey: Key.hidden) as? [String]) ?? [])
        prices = Self.decodePrices(defaults.data(forKey: Key.prices))
        tagBelowLogo = defaults.object(forKey: Key.tagBelowLogo) == nil
            ? true : defaults.bool(forKey: Key.tagBelowLogo)
        launchAtLogin = defaults.object(forKey: Key.launchAtLogin) == nil
            ? true : defaults.bool(forKey: Key.launchAtLogin)
        order = (defaults.array(forKey: Key.order) as? [String]) ?? []
        // ค่าที่อ่านไม่ออก (ของเวอร์ชันหน้า/ไฟล์เสีย) ตกกลับเป็นเต็ม ไม่ใช่พัง
        barDensity = BarDensity(rawValue: defaults.string(forKey: Key.barDensity) ?? "") ?? .full
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

    func setTagBelowLogo(_ below: Bool) {
        tagBelowLogo = below
        defaults.set(below, forKey: Key.tagBelowLogo)
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        launchAtLogin = enabled
        defaults.set(enabled, forKey: Key.launchAtLogin)
    }

    func setBarDensity(_ density: BarDensity) {
        barDensity = density
        defaults.set(density.rawValue, forKey: Key.barDensity)
    }

    func setOrder(_ ids: [String]) {
        order = ids
        defaults.set(ids, forKey: Key.order)
    }

    /// ย้ายค่าจากกลไกเดิม (ซ่อนราย group สำหรับแถบเมนู) มาเป็น hidden ราย bucket
    /// ลบคีย์เดิมทิ้งหลังย้าย จะได้ไม่ทับสิ่งที่ผู้ใช้เลือกใหม่ในรอบถัดไป
    func migrateVisibleGroups(_ defaults: UserDefaults, allItems: [UsageItem]) {
        let key = "visibleMenuBarProviders"
        guard let visible = defaults.stringArray(forKey: key) else { return }
        // snapshot ยังว่าง (เครื่องใหม่ เอนจินยังไม่เคยรัน) = ยังไม่รู้จะย้ายอะไร
        // ต้องเก็บคีย์เดิมไว้รอรอบหน้า ไม่ใช่ลบทิ้งทั้งที่ยังไม่ได้ย้าย
        guard !allItems.isEmpty else { return }
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
