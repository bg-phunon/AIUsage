import Foundation

struct MenuBarText: Equatable {
    let top: String
    let bottom: String
    let dimmed: Bool
}

struct MenuBarSegment: Equatable {
    let group: String
    let assetName: String
    let value: String
    let color: String
}

/// แถบสั้นแบบ provider × เปอร์เซ็นต์ สำหรับพื้นที่ menu bar
/// ไม่มีการสร้างตัวเลขขึ้นเอง: ถ้ายังวัดไม่ได้จะแสดง `—`
func menuBarSegments(snapshot: UsageSnapshot, now: Date, wokeRecently: Bool,
                     visibleGroups: Set<String> = ["Claude Code", "Qwen Cloud", "GLM", "Codex"]) -> [MenuBarSegment] {
    let age = snapshot.generated == .distantPast ? nil : now.timeIntervalSince(snapshot.generated)
    let state = freshness(snapshotAge: age, wokeRecently: wokeRecently)
    let definitions: [(String, String, String)] = [
        ("Claude Code", "claude", "#E49A54"),
        ("Qwen Cloud", "qwen", "#5C9DED"),
        ("GLM", "zai", "#B087E8"),
        ("Codex", "openai", "#67C587"),
    ]
    return definitions.compactMap { group, symbol, color in
        guard visibleGroups.contains(group) else { return nil }
        let candidates = snapshot.items.filter { $0.group == group && $0.error == nil && $0.local != true }
        guard let item = candidates.max(by: { ($0.displayPct ?? -1) < ($1.displayPct ?? -1) }) else { return nil }
        let usesSession = item.pct != nil
        let certaintyValue = certainty(confidence: usesSession ? item.confidence : (item.weekConfidence ?? item.confidence))
        let value: String
        if state == .dead || certaintyValue == .unknown || item.displayPct == nil {
            value = "—"
        } else {
            let prefix = certaintyValue == .atLeast ? "≥" : ""
            value = "\(prefix)\(Int((item.displayPct ?? 0).rounded()))%"
        }
        return MenuBarSegment(group: group, assetName: symbol, value: value, color: color)
    }
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
    let body = certaintyValue == .atLeast ? "≥\(number)%" : "\(number)%"
    return prefix + String(repeating: " ", count: max(1, 7 - prefix.count - body.count)) + body
}
