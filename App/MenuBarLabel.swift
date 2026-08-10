import Foundation

struct MenuBarText: Equatable {
    let top: String
    let bottom: String
    let dimmed: Bool
}

struct MenuBarSegment: Equatable {
    let group: String
    let assetName: String
    /// เลขบน (5 ชม.) — สไตล์ OpenUsage: สองหน้าต่างซ้อนกันในความกว้างเดียว
    let top: String
    /// เลขล่าง (7 วัน) — nil เมื่อถังนั้นมีหน้าต่างเดียว แล้ว top จะถูกวาดกลางบรรทัด
    let bottom: String?
    let color: String

    /// เข้ากันได้กับโค้ดเก่าที่อ่านค่าเดียว
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
        ("Codex", "openai", "#67C587"),
    ]
    /// เลขของหน้าต่างเดียว — nil เมื่อไม่มีตัวเลขที่เชื่อได้ (ต่างจาก "0%" ที่เป็นตัวเลขจริง)
    func windowText(_ pct: Double?, _ conf: String?) -> String? {
        guard state != .dead, let pct, certainty(confidence: conf) != .unknown else { return nil }
        return "\(Int(pct.rounded()))%"
    }
    let all: [MenuBarSegment] = definitions.compactMap { group, symbol, color in
        let candidates = snapshot.items.filter {
            $0.group == group && $0.error == nil && $0.local != true && !hidden.contains($0.id)
        }
        guard let item = candidates.max(by: { ($0.displayPct ?? -1) < ($1.displayPct ?? -1) }) else { return nil }
        let session = windowText(item.pct, item.confidence)
        let week = windowText(item.weekPct, item.weekConfidence ?? item.confidence)
        // ไม่มีเลขสักหน้าต่าง = ไม่ต้องกินที่บนแถบ — รายละเอียดยังอยู่ใน popover
        switch (session, week) {
        case (nil, nil):
            return nil
        case let (s?, w?):
            return MenuBarSegment(group: group, assetName: symbol, top: s, bottom: w, color: color)
        case let (s?, nil):
            return MenuBarSegment(group: group, assetName: symbol, top: s, bottom: nil, color: color)
        case let (nil, w?):
            return MenuBarSegment(group: group, assetName: symbol, top: w, bottom: nil, color: color)
        }
    }
    guard !pinned.isEmpty else { return all }
    // หมุดเป็น "ตัวกรอง" ไม่ใช่ "โหมดใหม่" — โลโก้และการจัดวางต้องเหมือนเดิมทุกอย่าง
    let pinnedGroups = pinned.compactMap { id -> String? in
        snapshot.items.first { $0.id == id }?.group
    }
    let filtered = pinnedGroups.compactMap { group in all.first { $0.group == group } }
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
