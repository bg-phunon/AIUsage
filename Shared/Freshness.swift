import Foundation

let freshLimit: TimeInterval = 180
let staleLimit: TimeInterval = 1800
let wakeGrace: TimeInterval = 90

enum Freshness: Equatable {
    case fresh
    case stale
    case dead
}

enum Certainty: Equatable {
    case exact
    case atLeast
    case unknown
}

func freshness(snapshotAge: TimeInterval?, wokeRecently: Bool) -> Freshness {
    guard let age = snapshotAge else { return .dead }
    if wokeRecently { return .fresh }
    if age < freshLimit { return .fresh }
    if age < staleLimit { return .stale }
    return .dead
}

/// `confidence` เป็นเรื่องของแคช utilization ของ Claude เท่านั้น
///
/// ถังอื่น (Codex ที่อ่าน % มาจาก rate_limits ตรงๆ) ไม่มีฟิลด์นี้เลย — `nil` จึงแปลว่า
/// "ไม่มีอะไรให้สงสัย" ไม่ใช่ "ไม่รู้" ถ้าตีความว่าไม่รู้ ตัวเลขจริงของ Codex จะถูกกลบเป็นขีด
/// แถวที่ไม่มีตัวเลขอยู่แล้วขึ้นขีดเองจาก `pct == nil` ไม่ต้องพึ่งค่านี้
func certainty(confidence: String?) -> Certainty {
    switch confidence {
    case "lower_bound": return .atLeast
    case "unsure": return .unknown
    default: return .exact
    }
}

func ageText(_ seconds: TimeInterval) -> String {
    let value = max(0, Int(seconds))
    if value < 60 { return "\(value)s" }
    if value < 3600 { return "\(value / 60)m" }
    if value < 86400 { return "\(value / 3600)h" }
    return "\(value / 86400)d"
}
