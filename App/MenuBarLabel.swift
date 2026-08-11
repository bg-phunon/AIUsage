import Foundation

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

/// เรียงตามลำดับที่ผู้ใช้จัดไว้ — ของที่ไม่อยู่ในลำดับต่อท้ายตามลำดับเดิม
func applyUserOrder<T>(_ items: [T], order: [String], id: (T) -> String) -> [T] {
    guard !order.isEmpty else { return items }
    let position = Dictionary(order.enumerated().map { ($1, $0) },
                              uniquingKeysWith: { first, _ in first })
    return items.enumerated().sorted { a, b in
        (position[id(a.element)] ?? order.count + a.offset)
            < (position[id(b.element)] ?? order.count + b.offset)
    }.map(\.element)
}

/// แถบสั้นแบบ provider × เปอร์เซ็นต์ สำหรับพื้นที่ menu bar
/// ไม่มีการสร้างตัวเลขขึ้นเอง: ถ้ายังวัดไม่ได้จะแสดง `—`
func menuBarSegments(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool,
                     hidden: Set<String> = [],
                     pinned: [String] = [],
                     order: [String] = []) -> [MenuBarSegment] {
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
            if session == nil && week == nil {
                // เห็นทุกบัญชี ccs คือเหตุผลข้อแรกของแอปนี้ — บัญชีที่มี traffic จริง
                // แต่แคชโควตาเก่าจนไม่มี % ต้องยังได้ที่บนแถบเป็นขีดคู่ ไม่ใช่ล่องหน
                // ถังที่เงียบสนิท (ไม่มีเลข ไม่มี traffic) ค่อยไม่กินที่ฟรีๆ
                guard state != .dead, item.weekTokens > 0 else { continue }
            }
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
    // ลำดับผู้ใช้มาก่อนลำดับ provider ที่ระบบเดา — แต่หมุดชนะทุกอย่างเพราะชี้ตรงกว่า
    let arranged = applyUserOrder(all, order: order) { $0.id }
    guard !pinned.isEmpty else { return arranged }
    // หมุดเป็น "ตัวกรอง" — เรียงตามลำดับที่ปัก โลโก้และการจัดวางเหมือนเดิมทุกอย่าง
    let filtered = pinned.compactMap { id in arranged.first { $0.id == id } }
    return filtered.isEmpty ? arranged : filtered
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
