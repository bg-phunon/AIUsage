import Foundation
import UserNotifications

/// การแจ้งเตือนหนึ่งใบที่ยังไม่เคยส่ง
struct LimitAlert: Equatable {
    /// กุญแจกันส่งซ้ำ — ผูกกับถัง หน้าต่าง ขั้น และ *เวลารีเซ็ต*
    /// เวลารีเซ็ตทำให้หน้าต่างใหม่กลายเป็นกุญแจใหม่ เตือนได้อีกโดยไม่ต้องล้างอะไร
    let key: String
    let title: String
    let body: String
}

/// สองขั้นพอ — 80% คือ "เริ่มวางแผน" 95% คือ "ใกล้หมดจริง"
/// ถี่กว่านี้กลายเป็นเสียงรบกวนที่ทำให้คนปิดการแจ้งเตือนทิ้งทั้งแอป
let limitThresholds: [Double] = [80, 95]

private func alertKey(_ item: UsageItem, _ window: String,
                      _ threshold: Double, _ reset: Date?) -> String {
    let stamp = reset.map { String(Int($0.timeIntervalSince1970)) } ?? "none"
    return "\(item.group)/\(item.label)|\(window)|\(Int(threshold))|\(stamp)"
}

/// ใบที่ควรส่งตอนนี้ — บริสุทธิ์ ไม่แตะระบบแจ้งเตือน จะได้เทสต์กติกาได้ตรงๆ
///
/// เอนจินรันทุก 60 วินาที ฟังก์ชันนี้จึงถูกเรียกซ้ำด้วยข้อมูลชุดเดิมตลอด กติกากันซ้ำ
/// คือหัวใจ ไม่ใช่ของแถม
func pendingLimitAlerts(items: [UsageItem], alreadySent: Set<String>) -> [LimitAlert] {
    var out: [LimitAlert] = []
    for item in items {
        let windows: [(String, Double?, String?, Date?)] = [
            ("5h", item.pct, item.confidence, item.resetAt),
            ("7d", item.weekPct, item.weekConfidence, item.weekResetAt ?? item.resetAt),
        ]
        for (window, pct, confidence, reset) in windows {
            guard let pct else { continue }
            // "unsure" แปลว่าหน้าต่างหมุนไปแล้วแต่ยังไม่มีเลขใหม่ — เตือนจากมันคือการเดา
            // ส่วน "lower_bound" คือ "อย่างน้อยเท่านี้" ของจริงมีแต่จะสูงกว่า เตือนได้
            guard certainty(confidence: confidence) != .unknown else { continue }
            // ดูเฉพาะขั้นสูงสุดที่ข้ามมาแล้ว — ข้ามจาก 0 ไป 96 ในรอบเดียวต้องได้ใบเดียว
            // และพอขึ้นจาก 82 เป็น 96 ขั้น 95 ยังเป็นกุญแจใหม่ที่ยังไม่เคยส่ง
            guard let crossed = limitThresholds.last(where: { pct >= $0 }) else { continue }
            let key = alertKey(item, window, crossed, reset)
            guard !alreadySent.contains(key) else { continue }
            out.append(LimitAlert(
                key: key,
                title: "\(item.label) ใกล้ชนลิมิต",
                body: "\(item.group) · \(window) ที่ \(Int(pct.rounded()))% (เกิน \(Int(crossed))%)"))
        }
    }
    return out
}

/// ส่งใบที่ยังไม่เคยส่ง แล้วจำไว้ว่าส่งอะไรไปแล้ว
///
/// รายการที่ส่งแล้วอยู่ใน UserDefaults ไม่ใช่หน่วยความจำ — ปิดเปิดแอปแล้วต้องไม่
/// ยิงชุดเดิมซ้ำ และตัดทิ้งเมื่อเกินเพดานเพื่อไม่ให้โตไม่รู้จบ
final class LimitNotifier {
    private static let key = "sentLimitAlerts"
    private static let maxRemembered = 200

    private let defaults: UserDefaults
    private let center: UNUserNotificationCenter?

    init(defaults: UserDefaults = .standard, center: UNUserNotificationCenter? = .current()) {
        self.defaults = defaults
        self.center = center
    }

    func requestPermission() {
        center?.requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// คืนใบที่ส่งไป — ผู้เรียกไม่ต้องใช้ แต่เทสต์กับการดีบักอยากรู้
    @discardableResult
    func notify(items: [UsageItem]) -> [LimitAlert] {
        // เก็บเป็นลำดับ ไม่ใช่ Set — ตอนตัดของเก่าทิ้งต้องรู้ว่าอันไหนเก่า
        var sent = defaults.stringArray(forKey: Self.key) ?? []
        let alerts = pendingLimitAlerts(items: items, alreadySent: Set(sent))
        guard !alerts.isEmpty else { return [] }
        for alert in alerts {
            sent.append(alert.key)
            guard let center else { continue }
            let content = UNMutableNotificationContent()
            content.title = alert.title
            content.body = alert.body
            center.add(UNNotificationRequest(identifier: alert.key,
                                             content: content, trigger: nil))
        }
        // ตัดหัวทิ้ง กุญแจเก่าผูกกับหน้าต่างที่ผ่านไปแล้ว ไม่มีวันถูกถามอีก
        //
        // ต้องห่อด้วย Array() — suffix() คืน ArraySlice ซึ่งไม่ใช่ property-list
        // type แล้ว UserDefaults จะโยน NSInvalidArgumentException ทิ้งทั้งแอป
        // (เคสจริง 2026-09-10: แอปพังวนสามรอบทันทีที่บัญชีแรกแตะ 95%)
        defaults.set(Array(sent.suffix(Self.maxRemembered)), forKey: Self.key)
        return alerts
    }
}
