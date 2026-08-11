import SwiftUI

enum DesignStyle: String, CaseIterable, Identifiable {
    case darkGlass
    case native
    case colorful

    var id: String { rawValue }
    var title: String {
        switch self {
        case .darkGlass: return "A · Liquid Glass"
        case .native: return "B · Native macOS"
        case .colorful: return "C · Colorful"
        }
    }
    var subtitle: String {
        switch self {
        case .darkGlass: return "โปร่ง เบา เส้นบาง แบบกระจกจริง"
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
    /// ไล่สีบางเบา — กระจกจริงไม่ทาสีหนา ความลึกมาจาก blur ของวัสดุข้างหลัง
    var cardGradient: LinearGradient {
        let stops: [Color]
        switch self {
        case .darkGlass:
            stops = [Color.white.opacity(0.055), Color.white.opacity(0.030), Color.white.opacity(0.040)]
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

    /// ขอบสว่างด้านบน — เส้นเดียวที่ทำให้กระจกดูเป็นกระจกจริง (บางๆ พอให้รู้)
    var rimHighlight: LinearGradient {
        let top: Double
        switch self {
        case .darkGlass: top = 0.16
        case .native: top = 0.22
        case .colorful: top = 0.34
        }
        return LinearGradient(colors: [Color.white.opacity(top), Color.white.opacity(0.04), .clear],
                              startPoint: .top, endPoint: .bottom)
    }

    var cardFill: Color {
        switch self {
        case .darkGlass: return Color.white.opacity(0.045)
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
