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
        case .darkGlass: return .cyan
        case .native: return .blue
        case .colorful: return .purple
        }
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
