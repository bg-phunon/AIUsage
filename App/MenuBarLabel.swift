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
            if session == nil && week == nil {
                // เห็นทุกบัญชี ccs คือเหตุผลข้อแรกของแอปนี้ — บัญชีที่มี traffic จริง
                // แต่แคชโควตาเก่าจนไม่มี % ต้องยังได้ที่บนแถบเป็นขีด ไม่ใช่ล่องหน
                // ถังที่เงียบสนิท (ไม่มีเลข ไม่มี traffic) ค่อยไม่กินที่ฟรีๆ
                guard state != .dead, item.weekTokens > 0 else { continue }
            }
            // สองบรรทัดเฉพาะตอนมีเลขครบสองหน้าต่าง (บน 5h ล่าง 7d)
            // มีตัวเดียว = บรรทัดเดียวตัวใหญ่ อ่านง่ายกว่าขีดค้ำที่ไม่บอกอะไร
            let top: String
            let bottom: String?
            switch (session, week) {
            case let (s?, w?): top = s; bottom = w
            case let (s?, nil): top = s; bottom = nil
            case let (nil, w?): top = w; bottom = nil
            case (nil, nil): top = "–"; bottom = nil
            }
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

extension BarDensity {
    /// ช่องไฟระหว่างถัง — 4 pt ที่ต่างกันคือ 20 pt เมื่อมี 6 ถัง
    var segmentGap: CGFloat { self == .full ? 10 : 6 }
}

/// บีบแถบให้พอดีที่ตามระดับที่ผู้ใช้เลือก
///
/// คืนถังที่เหลือ พร้อมจำนวนที่ถูกตัดออก — ที่ถูกตัดต้องนับได้เสมอ ไม่ใช่หายเงียบ
/// (ป้าย "+3" บนแถบคือสัญญาว่ายังมีของอยู่ ให้ไปเปิด popover ดู)
///
/// ลำดับที่เข้ามาคือลำดับที่ผู้ใช้จัดและปักไว้แล้ว ตัวที่รอดจึงเป็นตัวที่เขาเลือกเอง
/// ไม่ใช่ตัวที่เราคิดว่าสำคัญ
func applyDensity(_ segments: [MenuBarSegment],
                  _ density: BarDensity) -> (segments: [MenuBarSegment], overflow: Int) {
    guard density != .full else { return (segments, 0) }
    let kept = density.bucketLimit.map { Array(segments.prefix($0)) } ?? segments
    return (kept.map(withoutPercentSign), segments.count - kept.count)
}

/// "23%" → "23" · ขีดคือ "มีบัญชีแต่ยังไม่มีเลข" ไม่ใช่ตัวเลข ห้ามแตะ
private func withoutPercentSign(_ segment: MenuBarSegment) -> MenuBarSegment {
    func trimmed(_ text: String) -> String {
        text.hasSuffix("%") ? String(text.dropLast()) : text
    }
    return MenuBarSegment(id: segment.id, group: segment.group,
                          assetName: segment.assetName, tag: segment.tag,
                          top: trimmed(segment.top), bottom: segment.bottom.map(trimmed),
                          color: segment.color)
}

/// ถังวิกฤตที่หลุดจากแถบเพราะโหมดกะทัดรัด
///
/// ป้าย "+3" บอกแค่ว่ายังมีของ ไม่ได้บอกว่าของนั้นกำลังจะเต็ม ถ้าไม่มีอะไรเตือน
/// ความกะทัดรัดก็กลายเป็นการปิดตาผู้ใช้ — จุดแดงดวงเดียวกับที่ใช้กับถังที่ไม่ได้ปัก
func hasCritical(snapshot: UsageSnapshot, ids: [String]) -> Bool {
    let dropped = Set(ids)
    return snapshot.items.contains {
        $0.error == nil && $0.severity == "critical" && dropped.contains($0.id)
    }
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
