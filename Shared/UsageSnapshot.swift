import Foundation
import SwiftUI

/// gauge เฉพาะโมเดล (เช่น weekly ของ Fable) — แถวเสริมใต้ 5h/7d ไม่ปนกับตัวรวม
struct ModelWindow: Codable, Hashable {
    var label: String
    var pct: Double?
    var resetAt: Date?
    var confidence: String?
}

struct UsageItem: Codable, Identifiable, Hashable {
    var group: String
    var label: String
    var window: String
    var pct: Double?
    var tokens: Int
    /// nil = ไม่รู้ราคาของถังนี้ · ห้ามแทนด้วย 0 เพราะศูนย์อ่านเป็น "ฟรี"
    var cost: Double?
    var calls: Int
    var resetAt: Date?
    var weekTokens: Int
    var weekCost: Double?
    var weekPct: Double?
    /// เวลารีเซ็ตของหน้าต่างสัปดาห์ — คนละอันกับ resetAt ที่เป็นของ 5h
    /// ถังที่ส่งมาช่องเดียว (Qwen Cloud) ยังปล่อย nil ไว้แล้วให้ UI ตกกลับไปใช้ resetAt
    var weekResetAt: Date?
    var profile: String?
    var plan: String?
    var pctSource: String?
    var confidence: String?
    var weekConfidence: String? = nil
    var dataFetchedAt: Date?
    var severity: String?
    var activeLimit: String?
    var error: String?
    var local: Bool?
    var costKnown: Bool = false
    var costCurrency: String? = nil
    var costSource: String? = nil
    var costEstimated: Bool = false
    /// "notional" = จ่ายเหมาไปแล้ว ตัวเลขคือมูลค่าถ้ายิงผ่าน API ไม่ใช่บิล
    var costKind: String? = nil
    var modelWindows: [ModelWindow] = []
    /// โควตาส่วนที่ใช้ต่อได้หลังชนเพดานแผน — nil = ถังนี้ไม่มีแนวคิดเรื่องเครดิต
    /// ต่างจาก 0 ที่แปลว่ามีแต่หมดแล้ว ซึ่งเป็นข้อมูลที่ต้องบอกผู้ใช้
    var credits: Double? = nil
    var creditsUnlimited: Bool = false
    /// ใบรีเซ็ตลิมิตที่ยังไม่หมดอายุ — ทางออกตอนชนเพดาน มีวันหมดอายุของตัวเอง
    /// nil = ถังนี้ไม่มีแนวคิดนี้ · 0 = เคยมีแต่ใช้หมด/หมดอายุแล้ว ซึ่งต้องบอก
    var limitResets: Int? = nil
    var limitResetExpiresAt: Date? = nil
    /// วันหมดอายุของทุกใบ เรียงใบที่จะหมดก่อน — ใบที่หมดแล้วถูกกรองทิ้งตั้งแต่ฝั่งเอนจิน
    var limitResetsExpiring: [Date] = []

    enum CodingKeys: String, CodingKey {
        case group, label, window, pct, tokens, cost, calls, resetAt, weekTokens, weekCost, weekPct
        case weekResetAt
        case profile, plan, pctSource, confidence, weekConfidence, dataFetchedAt, severity
        case activeLimit, error, local, costKnown, costCurrency, costSource, costEstimated, costKind
        case credits, creditsUnlimited, limitResets, limitResetExpiresAt
        case limitResetsExpiring
        case modelWindows
    }

    /// ตัวสร้างแบบระบุเอง — struct ที่มี init(from:) จะไม่ได้ memberwise init อัตโนมัติ
    /// ใส่ค่าเริ่มต้นให้ฟิลด์ตามสัญญาไว้ เพิ่มฟิลด์ใหม่แล้ว test เดิมจะได้ไม่พัง
    init(group: String, label: String, window: String, pct: Double? = nil,
         tokens: Int = 0, cost: Double? = nil, calls: Int = 0, resetAt: Date? = nil,
         weekTokens: Int = 0, weekCost: Double? = nil, weekPct: Double? = nil,
         weekResetAt: Date? = nil, profile: String? = nil, plan: String? = nil, pctSource: String? = nil,
         confidence: String? = nil, weekConfidence: String? = nil,
         dataFetchedAt: Date? = nil, severity: String? = nil, activeLimit: String? = nil,
         error: String? = nil, local: Bool? = nil, costKnown: Bool = false,
         costCurrency: String? = nil, costSource: String? = nil,
         costEstimated: Bool = false, costKind: String? = nil,
         modelWindows: [ModelWindow] = []) {
        self.group = group; self.label = label; self.window = window; self.pct = pct
        self.tokens = tokens; self.cost = cost; self.calls = calls; self.resetAt = resetAt
        self.weekTokens = weekTokens; self.weekCost = weekCost; self.weekPct = weekPct
        self.weekResetAt = weekResetAt
        self.profile = profile; self.plan = plan; self.pctSource = pctSource
        self.confidence = confidence; self.weekConfidence = weekConfidence
        self.dataFetchedAt = dataFetchedAt; self.severity = severity
        self.activeLimit = activeLimit; self.error = error; self.local = local
        self.costKnown = costKnown; self.costCurrency = costCurrency
        self.costSource = costSource; self.costEstimated = costEstimated
        self.costKind = costKind
        self.modelWindows = modelWindows
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        group = try c.decode(String.self, forKey: .group)
        label = try c.decode(String.self, forKey: .label)
        window = try c.decode(String.self, forKey: .window)
        pct = try c.decodeIfPresent(Double.self, forKey: .pct)
        tokens = try c.decode(Int.self, forKey: .tokens)
        cost = try c.decodeIfPresent(Double.self, forKey: .cost)
        calls = try c.decode(Int.self, forKey: .calls)
        resetAt = try c.decodeIfPresent(Date.self, forKey: .resetAt)
        weekTokens = try c.decode(Int.self, forKey: .weekTokens)
        weekCost = try c.decodeIfPresent(Double.self, forKey: .weekCost)
        weekPct = try c.decodeIfPresent(Double.self, forKey: .weekPct)
        weekResetAt = try c.decodeIfPresent(Date.self, forKey: .weekResetAt)
        profile = try c.decodeIfPresent(String.self, forKey: .profile)
        plan = try c.decodeIfPresent(String.self, forKey: .plan)
        pctSource = try c.decodeIfPresent(String.self, forKey: .pctSource)
        confidence = try c.decodeIfPresent(String.self, forKey: .confidence)
        weekConfidence = try c.decodeIfPresent(String.self, forKey: .weekConfidence)
        dataFetchedAt = try c.decodeIfPresent(Date.self, forKey: .dataFetchedAt)
        severity = try c.decodeIfPresent(String.self, forKey: .severity)
        activeLimit = try c.decodeIfPresent(String.self, forKey: .activeLimit)
        error = try c.decodeIfPresent(String.self, forKey: .error)
        local = try c.decodeIfPresent(Bool.self, forKey: .local)
        costKnown = try c.decodeIfPresent(Bool.self, forKey: .costKnown) ?? false
        costCurrency = try c.decodeIfPresent(String.self, forKey: .costCurrency)
        costSource = try c.decodeIfPresent(String.self, forKey: .costSource)
        costEstimated = try c.decodeIfPresent(Bool.self, forKey: .costEstimated) ?? false
        costKind = try c.decodeIfPresent(String.self, forKey: .costKind)
        modelWindows = try c.decodeIfPresent([ModelWindow].self, forKey: .modelWindows) ?? []
        credits = try c.decodeIfPresent(Double.self, forKey: .credits)
        creditsUnlimited = try c.decodeIfPresent(Bool.self, forKey: .creditsUnlimited) ?? false
        limitResets = try c.decodeIfPresent(Int.self, forKey: .limitResets)
        limitResetExpiresAt = try c.decodeIfPresent(Date.self, forKey: .limitResetExpiresAt)
        limitResetsExpiring = try c.decodeIfPresent([Date].self, forKey: .limitResetsExpiring) ?? []
    }

    var id: String { "\(group)/\(label)" }
    /// เลือกหน้าต่างที่เร่งด่วนกว่าเสมอ (ไม่ใช่แค่ 5h ถ้ามี) —
    /// ถังที่ 5h ต่ำแต่ 7d ใกล้ชนลิมิตต้องขึ้นเป็น "แย่กว่า" ไม่ใช่ถูกกลบด้วยตัวเลข 5h ที่ดูสบายใจ
    var displayPct: Double? {
        switch (pct, weekPct) {
        case let (p?, w?): return max(p, w)
        case let (p?, nil): return p
        case let (nil, w?): return w
        case (nil, nil): return nil
        }
    }
    var isOfficial: Bool { pctSource == "official" }

    func dataAge(now: Date) -> TimeInterval? {
        guard let fetched = dataFetchedAt else { return nil }
        return now.timeIntervalSince(fetched)
    }

    var tokensText: String {
        if tokens >= 1_000_000 { return String(format: "%.2fM", Double(tokens) / 1_000_000) }
        if tokens >= 1_000 { return String(format: "%.0fk", Double(tokens) / 1_000) }
        return "\(tokens)"
    }

    var tint: Color {
        if error != nil { return .secondary }
        guard let p = displayPct else { return .secondary }
        if p >= 90 { return Color(red: 0.90, green: 0.33, blue: 0.29) }
        if p >= 70 { return Color(red: 0.89, green: 0.66, blue: 0.23) }
        return Color(red: 0.30, green: 0.76, blue: 0.54)
    }
}

struct UsageSnapshot: Codable {
    var generated: Date
    var items: [UsageItem]
    /// เอนจินเปิด live usage อยู่จริงหรือเปล่ารอบล่าสุด — สวิตช์อยู่ได้สองที่
    /// (UserDefaults ของแอป กับ config.json ของเอนจิน) หน้าตั้งค่าจึงต้องถาม
    /// ผลลัพธ์จริง ไม่ใช่เดาจากฝั่งเดียว · nil = snapshot เก่าก่อนมีฟิลด์นี้
    var liveUsage: Bool?

    static let empty = UsageSnapshot(generated: .distantPast, items: [])

    static var fileURL: URL {
        URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Application Support/AIUsage/snapshot.json")
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { value in
            let raw = try value.singleValueContainer().decode(String.self)
            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso.date(from: raw) { return date }
            iso.formatOptions = [.withInternetDateTime]
            return iso.date(from: raw) ?? Date()
        }
        return decoder
    }

    static func decode(from data: Data) -> UsageSnapshot? {
        try? decoder().decode(UsageSnapshot.self, from: data)
    }

    static func load() -> UsageSnapshot {
        guard let data = try? Data(contentsOf: fileURL) else { return .empty }
        return decode(from: data) ?? .empty
    }
}

func countdownText(to date: Date?, from now: Date) -> String {
    guard let date else { return "—" }
    let secs = Int(date.timeIntervalSince(now))
    if secs <= 0 { return "รีเซ็ตแล้ว" }
    let d = secs / 86400, h = (secs % 86400) / 3600, m = (secs % 3600) / 60
    if d > 0 { return "\(d)วัน \(h)ชม." }
    if h > 0 { return "\(h)ชม. \(m)น." }
    return "\(m)น."
}
