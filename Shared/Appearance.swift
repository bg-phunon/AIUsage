import SwiftUI

enum DesignStyle: String, CaseIterable, Identifiable {
    case darkGlass
    case native
    case colorful

    var id: String { rawValue }
    var title: String {
        switch self {
        case .darkGlass: return "A · Dark Glass"
        case .native: return "B · Native macOS"
        case .colorful: return "C · Colorful"
        }
    }
    var subtitle: String {
        switch self {
        case .darkGlass: return "เข้ม โปร่ง และกะทัดรัด"
        case .native: return "เรียบ ปรับตามระบบ"
        case .colorful: return "สี provider ชัดเจน"
        }
    }
    var accent: Color {
        switch self {
        case .darkGlass: return Color(red: 0.66, green: 0.55, blue: 1.0)  // ม่วงตามดีไซน์
        case .native: return .blue
        case .colorful: return .purple
        }
    }
    /// ไล่สี 165° ตามดีไซน์ — การ์ดแบนไม่มีความลึก ดูไม่เป็นกระจก
    var cardGradient: LinearGradient {
        let stops: [Color]
        switch self {
        case .darkGlass:
            stops = [Color.white.opacity(0.10), Color.white.opacity(0.06), Color.white.opacity(0.08)]
        case .native:
            stops = [Color.primary.opacity(0.075), Color.primary.opacity(0.045), Color.primary.opacity(0.06)]
        case .colorful:
            stops = [Color.white.opacity(0.10), Color.white.opacity(0.045), Color.white.opacity(0.075)]
        }
        return LinearGradient(stops: [.init(color: stops[0], location: 0),
                                      .init(color: stops[1], location: 0.55),
                                      .init(color: stops[2], location: 1)],
                              startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    /// ขอบสว่างด้านบน — เส้นเดียวที่ทำให้กระจกดูเป็นกระจกจริง
    var rimHighlight: LinearGradient {
        let top = self == .native ? 0.22 : 0.34
        return LinearGradient(colors: [Color.white.opacity(top), Color.white.opacity(0.06), .clear],
                              startPoint: .top, endPoint: .bottom)
    }

    var cardFill: Color {
        switch self {
        case .darkGlass: return Color.white.opacity(0.075)
        case .native: return Color.primary.opacity(0.06)
        case .colorful: return Color.white.opacity(0.06)
        }
    }
    var panelFill: Color {
        switch self {
        case .darkGlass: return Color(red: 0.04, green: 0.11, blue: 0.15)
        case .native: return Color(nsColor: .windowBackgroundColor)
        case .colorful: return Color(red: 0.05, green: 0.06, blue: 0.14)
        }
    }
}
