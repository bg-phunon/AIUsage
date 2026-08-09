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

func certainty(confidence: String?) -> Certainty {
    switch confidence {
    case "valid", "zero": return .exact
    case "lower_bound": return .atLeast
    default: return .unknown
    }
}

func ageText(_ seconds: TimeInterval) -> String {
    let value = max(0, Int(seconds))
    if value < 60 { return "\(value)s" }
    if value < 3600 { return "\(value / 60)m" }
    if value < 86400 { return "\(value / 3600)h" }
    return "\(value / 86400)d"
}

/// ทำไมแถวนี้ถึงไม่มี % — สองสาเหตุที่หน้าตาเหมือนกันแต่แก้คนละแบบ
///
/// `dataFetchedAt` มีค่า แปลว่าเคยได้ตัวเลขทางการจาก Anthropic มาแล้ว คือ**รู้ว่ามีเพดาน**
/// แค่แคชเก่าจนหน้าต่างหมุนไปและมีการใช้งานต่อ → บอกวิธีแก้ไปเลย เพราะเปิด /usage
/// ครั้งเดียวก็กลับมามีตัวเลข
///
/// ไม่มี `dataFetchedAt` แปลว่าไม่เคยมีแหล่งเพดานเลย (Qwen Cloud, GLM) → บอกตามตรง
func missingPercentReason(_ item: UsageItem, now: Date) -> String {
    if let age = item.dataAge(now: now) {
        return "\(item.tokensText) · โควตาเก่า \(ageText(age)) — เปิด /usage ใน Claude Code เพื่ออัปเดต"
    }
    return "\(item.tokensText) · ยังไม่รู้เพดาน"
}
