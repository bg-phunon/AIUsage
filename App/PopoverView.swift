import SwiftUI
import AppKit

struct VisualEffectBackground: NSViewRepresentable {
    let material: NSVisualEffectView.Material

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = .behindWindow
        view.state = .active
        view.isEmphasized = true
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = material
        view.blendingMode = .behindWindow
        view.state = .active
    }
}

extension Notification.Name {
    static let aiUsageRefreshRequested = Notification.Name("AIUsage.refreshRequested")
    static let aiUsageSettingsChanged = Notification.Name("AIUsage.settingsChanged")
}

struct PopoverView: View {
    @ObservedObject var model: UsageModel
    @State private var now = Date()
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    private var snapshotAge: TimeInterval? {
        model.snapshot.generated == .distantPast ? nil : now.timeIntervalSince(model.snapshot.generated)
    }

    private var snapshotState: Freshness {
        freshness(snapshotAge: snapshotAge, wokeRecently: model.wokeRecently)
    }

    private var displayItems: [UsageItem] {
        model.snapshot.items.filter { item in
            guard item.group != "กรอกเอง" else { return false }
            if item.group == "ยังไม่รู้จัก" {
                return item.tokens > 0 || item.weekTokens > 0 || item.error != nil
            }
            return true
        }
    }

    private var knownWeeklyCost: Double {
        displayItems.compactMap { $0.costKnown ? $0.weekCost : nil }.reduce(0, +)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let error = model.engineError {
                strip(icon: "exclamationmark.triangle.fill", text: error, tint: .red)
            } else if snapshotState != .fresh, let age = snapshotAge {
                strip(icon: "arrow.clockwise", text: "อัปเดตล่าสุด \(ageText(age)) ที่แล้ว",
                      tint: snapshotState == .dead ? .red : .orange)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(displayItems) { item in row(item) }
                    if displayItems.isEmpty {
                        Text("ยังไม่มีข้อมูล").foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center).padding(.vertical, 40)
                    }
                }.padding(14)
            }
            footer
        }
        .frame(width: 380, height: 560)
        .background { panelBackground }
        .preferredColorScheme(model.designStyle == .native ? nil : .dark)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(model.designStyle == .native ? 0.08 : 0.16), lineWidth: 1)
        }
        .sheet(isPresented: $model.settingsPresented) {
            ProviderSettingsView(model: model)
        }
        .onReceive(tick) { now = $0 }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 19, weight: .semibold))
                .foregroundStyle(model.designStyle.accent)
                .frame(width: 30, height: 30)
                .background(model.designStyle.accent.opacity(0.16), in: RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 1) {
                Text("AI Usage").font(.system(size: 14, weight: .semibold))
                Text("โควตาตามบัญชีและ provider").font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer()
            Button { refreshEngine() } label: {
                Image(systemName: "arrow.clockwise")
            }.buttonStyle(.borderless).help("รีเฟรชเดี๋ยวนี้")
            Button { model.settingsPresented = true } label: {
                Image(systemName: "gearshape")
            }.buttonStyle(.borderless).help("ตั้งค่า")
            Button { NSApplication.shared.terminate(nil) } label: {
                Image(systemName: "power")
            }.buttonStyle(.borderless).help("ออกจากแอป")
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(chromeFill)
    }

    @ViewBuilder private var panelBackground: some View {
        switch model.designStyle {
        case .darkGlass:
            ZStack {
                VisualEffectBackground(material: .hudWindow)
                LinearGradient(colors: [Color.cyan.opacity(0.055), .clear, Color.blue.opacity(0.04)],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
            }
        case .native:
            VisualEffectBackground(material: .popover)
        case .colorful:
            LinearGradient(colors: [Color(red: 0.07, green: 0.05, blue: 0.18),
                                    Color(red: 0.025, green: 0.045, blue: 0.10)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }

    private var footer: some View {
        HStack(spacing: 6) {
            Circle().fill(snapshotState == .fresh ? Color.green : Color.orange)
                .frame(width: 6, height: 6)
            if let age = snapshotAge {
                Text("อัปเดต \(ageText(age)) ที่แล้ว")
            } else {
                Text("ยังไม่เคยอัปเดต")
            }
            Spacer()
            if knownWeeklyCost > 0 {
                Text("ประมาณ $" + String(format: "%.2f", knownWeeklyCost) + " / 7d")
            }
            Text("\(displayItems.count) รายการ")
        }
        .font(.system(size: 10, weight: .medium))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(chromeFill)
    }

    private var chromeFill: Color {
        switch model.designStyle {
        case .darkGlass: return Color.black.opacity(0.10)
        case .native: return Color.primary.opacity(0.035)
        case .colorful: return Color.black.opacity(0.14)
        }
    }

    private func refreshEngine() {
        NotificationCenter.default.post(name: .aiUsageRefreshRequested, object: nil)
    }

    private func openSettings() {
        let url = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent(".config/ai-usage/config.json")
        NSWorkspace.shared.open(url)
    }

    @ViewBuilder private func strip(icon: String, text: String, tint: Color) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
            Text(text).font(.system(size: 11)).lineLimit(2)
            Spacer()
        }.foregroundStyle(tint).padding(.horizontal, 14).padding(.vertical, 8)
            .background(tint.opacity(0.12))
    }

    @ViewBuilder private func row(_ item: UsageItem) -> some View {
        let sessionCertainty = item.error == nil ? certainty(confidence: item.confidence) : .unknown
        let weekCertainty = item.error == nil ? certainty(confidence: item.weekConfidence ?? item.confidence) : .unknown
        let headlineCertainty = item.pct == nil ? weekCertainty : sessionCertainty
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                providerMark(item.group)
                VStack(alignment: .leading, spacing: 1) {
                    Text(item.group).font(.system(size: 12, weight: .semibold))
                    Text(item.label).font(.system(size: 10)).foregroundStyle(.secondary)
                }
                if let plan = item.plan { Text(plan).font(.system(size: 9, weight: .medium))
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(providerColor(item.group).opacity(0.15)).clipShape(Capsule()) }
                Spacer()
                if item.error != nil {
                    Text("พัง").font(.system(size: 10, weight: .semibold)).foregroundStyle(.red)
                } else {
                    Text(pctText(item.pct ?? item.weekPct, headlineCertainty))
                        .font(.system(size: 12, weight: .medium)).monospacedDigit()
                }
            }
            usageBar(label: "5h", pct: item.pct, tint: item.tint, sure: sessionCertainty)
            usageBar(label: "7d", pct: item.weekPct, tint: item.tint, sure: weekCertainty)
            HStack(spacing: 8) {
                if let error = item.error { Text(error).font(.system(size: 10)).foregroundStyle(.red).lineLimit(2) }
                else if item.local == true { Text("ในเครือข่ายตัวเอง · ไม่มีโควตา") }
                else if !item.isOfficial { Text("\(item.tokensText) · ยังไม่รู้เพดาน") }
                else { Text("รีเซ็ต \(countdownText(to: item.resetAt, from: now))") }
                if headlineCertainty == .atLeast { Text("· ใช้ต่อหลังเช็คล่าสุด") }
                if let active = item.activeLimit { Text("· ชนลิมิต \(active)").foregroundStyle(.red) }
                if item.costKnown, let weekCost = item.weekCost {
                    Text("· " + (item.costKind == "notional" ? "มูลค่า" : "ใช้ไป")
                         + " $" + String(format: "%.2f", weekCost) + " / 7d")
                        .foregroundStyle(.secondary)
                } else if item.weekTokens > 0 && item.local != true {
                    Text("· ราคาไม่ทราบ")
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }.font(.system(size: 10)).foregroundStyle(.secondary)
        }
        .padding(13)
        .background(cardFill(for: item), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(cardStroke(for: item), lineWidth: 1)
        }
        .shadow(color: model.designStyle == .native ? Color.black.opacity(0.07) : .clear,
                radius: 7, y: 2)
    }

    private func cardFill(for item: UsageItem) -> Color {
        if model.designStyle == .colorful {
            return providerColor(item.group).opacity(0.14)
        }
        return model.designStyle.cardFill
    }

    private func cardStroke(for item: UsageItem) -> Color {
        switch model.designStyle {
        case .colorful: return providerColor(item.group).opacity(0.32)
        case .native: return Color.primary.opacity(0.09)
        case .darkGlass: return Color.white.opacity(0.09)
        }
    }

    private func providerColor(_ group: String) -> Color {
        switch group {
        case "Claude Code": return .orange
        case "Qwen Cloud": return .blue
        case "GLM": return .purple
        case "Codex": return .green
        default: return .gray
        }
    }

    @ViewBuilder private func providerMark(_ group: String) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(providerColor(group).opacity(model.designStyle == .native ? 0.10 : 0.18))
            ProviderLogo(group: group, size: 18,
                         tint: model.designStyle == .colorful ? providerColor(group) : .primary)
        }
        .frame(width: 30, height: 30)
    }

    private func pctText(_ pct: Double?, _ certaintyValue: Certainty) -> String {
        guard let pct, certaintyValue != .unknown else { return "—" }
        return (certaintyValue == .atLeast ? "≥" : "") + String(format: "%.0f%%", pct)
    }

    private func usageBar(label: String, pct: Double?, tint: Color, sure: Certainty) -> some View {
        HStack(spacing: 8) {
            Text(label).font(.system(size: 9, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary).frame(width: 18, alignment: .leading)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.secondary.opacity(0.16))
                    if let pct, sure != .unknown {
                        let known = geometry.size.width * min(1, max(0, pct / 100))
                        Capsule().fill(model.designStyle == .colorful ? providerColorForTint(tint) : tint)
                            .frame(width: known)
                        if sure == .atLeast {
                            Capsule().fill(tint.opacity(0.20))
                                .frame(width: max(0, geometry.size.width - known)).offset(x: known)
                        }
                    } else {
                        HStack(spacing: 4) {
                            ForEach(0..<max(1, Int(geometry.size.width / 7)), id: \.self) { _ in
                                Circle().fill(Color.secondary.opacity(0.38)).frame(width: 2, height: 2)
                            }
                        }
                    }
                }
            }.frame(height: 6)
            Text(pctText(pct, sure)).font(.system(size: 10, weight: .medium, design: .rounded))
                .monospacedDigit().frame(width: 36, alignment: .trailing)
        }.frame(height: 14)
    }

    private func providerColorForTint(_ tint: Color) -> Color {
        tint
    }
}

struct ProviderSettingsView: View {
    @ObservedObject var model: UsageModel
    private let providers = [
        ("Claude Code", "Claude", "brain.head.profile"),
        ("Qwen Cloud", "Qwen Cloud", "cloud.fill"),
        ("GLM", "GLM", "sparkles"),
        ("Codex", "Codex", "command"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Image(systemName: "gearshape.fill").foregroundStyle(.blue)
                Text("ตั้งค่า menu bar").font(.system(size: 15, weight: .semibold))
                Spacer()
            }
            Text("เลือก provider ที่ต้องการให้แสดงบนแถบด้านบน")
                .font(.system(size: 11)).foregroundStyle(.secondary)
            Text("รูปแบบหน้าตา")
                .font(.system(size: 12, weight: .semibold))
            ForEach(DesignStyle.allCases) { style in
                Button {
                    model.designStyle = style
                    UserDefaults.standard.set(style.rawValue, forKey: "designStyle")
                } label: {
                    HStack(spacing: 10) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 6).fill(style.panelFill)
                            HStack(spacing: 2) {
                                ProviderLogo(group: "Claude Code", size: 11)
                                ProviderLogo(group: "Qwen Cloud", size: 11)
                                ProviderLogo(group: "Codex", size: 11)
                            }
                        }.frame(width: 52, height: 30)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(style.title).font(.system(size: 11, weight: .medium))
                            Text(style.subtitle).font(.system(size: 10)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if model.designStyle == style { Image(systemName: "checkmark.circle.fill").foregroundStyle(style.accent) }
                    }
                    .padding(7)
                    .background(model.designStyle == style ? style.accent.opacity(0.12) : Color.clear,
                                in: RoundedRectangle(cornerRadius: 8))
                }.buttonStyle(.plain)
            }
            Text("provider ที่แสดงบน menu bar")
                .font(.system(size: 12, weight: .semibold))
            ForEach(providers, id: \.0) { provider in
                Toggle(isOn: binding(for: provider.0)) {
                    Label(provider.1, systemImage: provider.2)
                }
                .toggleStyle(.switch)
            }
            Divider()
            HStack {
                Spacer()
                Button("เสร็จแล้ว") { model.settingsPresented = false }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 300)
    }

    private func binding(for group: String) -> Binding<Bool> {
        Binding(
            get: { model.visibleGroups.contains(group) },
            set: { enabled in
                if enabled { model.visibleGroups.insert(group) }
                else { model.visibleGroups.remove(group) }
                UserDefaults.standard.set(Array(model.visibleGroups), forKey: "visibleMenuBarProviders")
                NotificationCenter.default.post(name: .aiUsageSettingsChanged, object: nil)
            })
    }
}

struct ProviderLogo: View {
    let group: String
    let size: CGFloat
    var tint: Color = .primary

    private var asset: String? {
        switch group {
        case "Claude Code": return "claude"
        case "Codex": return "openai"
        case "GLM": return "zai"
        case "Qwen Cloud": return "qwen"
        default: return nil
        }
    }

    var body: some View {
        if let asset, let url = Bundle.main.url(forResource: asset, withExtension: "svg"),
           let nsImage = NSImage(contentsOf: url) {
            Image(nsImage: nsImage).renderingMode(.template).resizable().scaledToFit()
                .foregroundStyle(tint).frame(width: size, height: size)
        } else {
            Image(systemName: "circle.dashed").frame(width: size, height: size)
        }
    }
}
