import Foundation

struct MenuBarText: Equatable {
    let top: String
    let bottom: String
    let dimmed: Bool
}

struct MenuBarSegment: Equatable {
    /// bucket id ("group/label") — segment ต่อถัง ไม่ใช่ต่อ provider
    /// หลายบัญชี ccs คือเหตุผลข้อแรกของแอปนี้ การยุบเหลือตัวเดียวคือการทิ้งมัน
    let id: String
    let group: String
    let assetName: String
    /// ตัวย่อบัญชี โชว์เมื่อ provider เดียวกันมีหลายบัญชีบนแถบ (de/mo/wo)
    let tag: String?
    let top: String
    let bottom: String?
    let color: String

    var value: String { bottom == nil ? top : "\(top)/\(bottom!)" }
}

/// แถบสั้นแบบ provider × เปอร์เซ็นต์ สำหรับพื้นที่ menu bar
/// ไม่มีการสร้างตัวเลขขึ้นเอง: ถ้ายังวัดไม่ได้จะแสดง `—`
func menuBarSegments(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool,
                     hidden: Set<String> = [],
                     pinned: [String] = []) -> [MenuBarSegment] {
    let age = snapshot.generated == .distantPast ? nil : now.timeIntervalSince(snapshot.generated)
    let state = freshness(snapshotAge: age, wokeRecently: wokeRecently)
    let definitions: [(String, String, String)] = [
        ("Claude Code", "claude", "#E49A54"),
        ("Qwen Cloud", "qwen", "#5C9DED"),
        ("GLM", "zai", "#B087E8"),
        ("Codex", "codex", "#67C587"),
    ]
    func windowText(_ pct: Double?, _ conf: String?) -> String? {
        guard state != .dead, let pct, certainty(confidence: conf) != .unknown else { return nil }
        return "\(Int(pct.rounded()))%"
    }
    var all: [MenuBarSegment] = []
    for (group, symbol, color) in definitions {
        // segment ต่อถัง — ทุกบัญชีที่มีเลขได้ที่ของตัวเอง ไม่ถูกยุบเหลือตัวที่แย่สุด
        let candidates = snapshot.items
            .filter { $0.group == group && $0.error == nil && $0.local != true && !hidden.contains($0.id) }
            .sorted { $0.label < $1.label }
        var made: [MenuBarSegment] = []
        for item in candidates {
            let session = windowText(item.pct, item.confidence)
            let week = windowText(item.weekPct, item.weekConfidence ?? item.confidence)
            // สองบรรทัดเสมอ: บน 5h ล่าง 7d ตัวที่ไม่มีเป็นขีด
            // เลขเดี่ยวลอยๆ อ่านไม่ออกว่าเป็นหน้าต่างไหน — weekly ต้องมีที่ประจำ
            if session == nil && week == nil { continue }
            let top = session ?? "–"
            let bottom = week ?? "–"
            made.append(MenuBarSegment(id: item.id, group: group, assetName: symbol,
                                       tag: nil, top: top, bottom: bottom, color: color))
        }
        if made.count > 1 {
            // ป้ายบัญชีจำเป็นเฉพาะตอนโลโก้ซ้ำกัน — ตัวเดียวไม่ต้องมีให้รก
            made = made.map { seg in
                let label = String(seg.id.split(separator: "/").last ?? "").prefix(2)
                return MenuBarSegment(id: seg.id, group: seg.group, assetName: seg.assetName,
                                      tag: String(label), top: seg.top, bottom: seg.bottom,
                                      color: seg.color)
            }
        }
        all.append(contentsOf: made)
    }
    guard !pinned.isEmpty else { return all }
    // หมุดเป็น "ตัวกรอง" — เรียงตามลำดับที่ปัก โลโก้และการจัดวางเหมือนเดิมทุกอย่าง
    let filtered = pinned.compactMap { id in all.first { $0.id == id } }
    return filtered.isEmpty ? all : filtered
}

func menuBarText(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool) -> MenuBarText {
    let snapshotAge = snapshot.generated == .distantPast
        ? nil : now.timeIntervalSince(snapshot.generated)
    let state = freshness(snapshotAge: snapshotAge, wokeRecently: wokeRecently)
    let age = snapshotAge.map(ageText) ?? "—"

    guard let item = snapshot.worst else {
        return MenuBarText(top: "5h    —", bottom: "7d    —", dimmed: true)
    }
    if state == .dead {
        return MenuBarText(top: "5h    —", bottom: "↻ \(age)", dimmed: true)
    }

    let certaintyValue = certainty(confidence: item.confidence)
    let top = percentageLine("5h", item.pct, certaintyValue)
    if state == .stale {
        return MenuBarText(top: top, bottom: "↻ \(age)", dimmed: true)
    }
    let weekCertainty = certainty(confidence: item.weekConfidence ?? item.confidence)
    return MenuBarText(top: top, bottom: percentageLine("7d", item.weekPct, weekCertainty), dimmed: false)
}

private func percentageLine(_ prefix: String, _ pct: Double?, _ certaintyValue: Certainty) -> String {
    guard let pct, certaintyValue != .unknown else { return "\(prefix)    —" }
    let number = Int(pct.rounded())
    let body = "\(number)%"
    return prefix + String(repeating: " ", count: max(1, 7 - prefix.count - body.count)) + body
}

/// ถังที่จะขึ้นแถบเมนู
///
/// ไม่ปักเลย = อัตโนมัติ เลือกตัวที่ใกล้ชนที่สุด — ไม่ต้องมีสวิตช์โหมดแยก
/// เพราะ "ไม่ปัก" คืออัตโนมัติอยู่แล้วโดยธรรมชาติ
func menuBarUnits(snapshot: UsageSnapshot, pinned: [String]) -> [UsageItem] {
    let usable = snapshot.items.filter { $0.error == nil && $0.displayPct != nil }
    let chosen = pinned.compactMap { id in usable.first { $0.id == id } }
    if !chosen.isEmpty { return chosen }
    // ปักไว้แต่หาไม่เจอแล้ว → ตกกลับไปอัตโนมัติ ดีกว่าโชว์แถบว่าง
    return snapshot.worst.map { [$0] } ?? []
}

/// บรรทัดเดียวสำหรับตอนปักหลายถัง — โลโก้บอกว่าของใครอยู่แล้ว
/// เลือกหน้าต่างที่เร่งด่วนกว่า เพราะมีที่ให้ตัวเลขเดียว
func compactLine(_ item: UsageItem) -> String {
    let useWeek = (item.weekPct ?? -1) >= (item.pct ?? -1)
    let pct = useWeek ? item.weekPct : item.pct
    let sure = certainty(confidence: useWeek ? (item.weekConfidence ?? item.confidence)
                                             : item.confidence)
    guard let pct, sure != .unknown else { return "—" }
    return "\(Int(pct.rounded()))%"
}

/// มีถังที่ไม่ได้ปักกำลังวิกฤตอยู่ไหม
///
/// ถ้าผู้ใช้ปัก Codex ไว้อย่างเดียวแล้ว Claude weekly พุ่งไป 96%
/// เขาจะไม่รู้เลยเพราะเลือกที่จะไม่มองมัน — จุดแดงไม่แย่งที่และไม่เปลี่ยน
/// สิ่งที่เขาเลือก แค่บอกว่าควรเปิดดู
func hasUnpinnedCritical(snapshot: UsageSnapshot, pinned: [String]) -> Bool {
    guard !pinned.isEmpty else { return false }
    return snapshot.items.contains {
        $0.error == nil && $0.severity == "critical" && !pinned.contains($0.id)
    }
}
