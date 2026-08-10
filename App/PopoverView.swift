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
    // ต้องผูกตรงนี้ด้วย @ObservedObject แยกจาก model — Preferences เป็น ObservableObject
    // คนละตัว ถ้า view ดูแค่ model ปุ่มหมุดจะกดแล้วค่าบันทึกจริงแต่จอไม่วาดใหม่
    @ObservedObject var prefs: Preferences
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
            guard !prefs.hidden.contains(item.id) else { return false }
            guard item.group != "กรอกเอง" else { return false }
            if item.group == "ยังไม่รู้จัก" {
                return item.tokens > 0 || item.weekTokens > 0 || item.error != nil
            }
            return true
        }
    }

    private var knownWeeklyCost: Double {
        displayItems.compactMap { effectiveWeekCost($0, price: prefs.prices[$0.id]) }.reduce(0, +)
    }

    /// ทุกบาทในยอดรวมมาจากบัญชีที่จ่ายเหมาไปแล้วหรือเปล่า
    private var allNotional: Bool {
        displayItems
            .filter { effectiveWeekCost($0, price: prefs.prices[$0.id]) ?? 0 > 0 }
            .allSatisfy { $0.costKind == "notional" && prefs.prices[$0.id] == nil }
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
            if !prefs.pinned.isEmpty {
                HStack(spacing: 8) {
                    Text("แถบเมนู: ปักหมุดไว้ \(prefs.pinned.count)")
                    Spacer()
                    Button("ยกเลิกทั้งหมด → อัตโนมัติ") { prefs.clearPins() }
                        .buttonStyle(.plain)
                        .foregroundStyle(.tint)
                }
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 14).padding(.vertical, 8)
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
            Divider()
            HStack {
                Button("ตั้งค่า…") { model.showSettings = true }
                    .buttonStyle(.plain).font(.system(size: 11))
                Spacer()
            }
            .padding(.horizontal, 14).padding(.vertical, 8)
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
        .sheet(isPresented: $model.showSettings) {
            VStack(spacing: 0) {
                SettingsView(model: model, prefs: prefs)
                Divider()
                HStack { Spacer(); Button("เสร็จ") { model.showSettings = false } }
                    .padding(10)
            }
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
                ambientLight
                // ม่านทึบทับแสง — SwiftUI ไม่มี backdrop-filter แบบเว็บ
                // ถ้าไม่มีชั้นนี้ ก้อนแสงจะทะลุขึ้นมาเต็มๆ แล้วตัวหนังสืออ่านไม่ออก
                Color.black.opacity(0.62)
            }
        case .native:
            VisualEffectBackground(material: .popover)
        case .colorful:
            LinearGradient(colors: [Color(red: 0.07, green: 0.05, blue: 0.18),
                                    Color(red: 0.025, green: 0.045, blue: 0.10)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
        }
    }


    /// แสงพื้นหลังสี่ก้อน — ถ้าไม่มีอะไรให้หักเห กระจกก็เป็นแค่สีเทาโปร่ง
    private var ambientLight: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            ZStack {
                blob(Color(red: 1.0, green: 0.56, blue: 0.37), w * 0.62)
                    .offset(x: -w * 0.30, y: -h * 0.34)
                blob(Color(red: 0.10, green: 0.81, blue: 0.78), w * 0.68)
                    .offset(x: w * 0.34, y: -h * 0.24)
                blob(Color(red: 0.56, green: 0.38, blue: 1.0), w * 0.66)
                    .offset(x: w * 0.02, y: h * 0.36)
                blob(Color(red: 1.0, green: 0.82, blue: 0.34), w * 0.34)
                    .offset(x: w * 0.28, y: h * 0.44)
                    .opacity(0.6)
            }
            .blur(radius: 72)
            .opacity(0.28)
        }
        .allowsHitTesting(false)
    }

    private func blob(_ color: Color, _ size: CGFloat) -> some View {
        Circle()
            .fill(RadialGradient(colors: [color, color.opacity(0)],
                                 center: .center, startRadius: 0, endRadius: size / 2))
            .frame(width: size, height: size)
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
                // ยอดนี้ส่วนใหญ่มาจากบัญชี subscription ที่จ่ายเหมาไปแล้ว
                // เรียกว่า "ประมาณ" ทำให้อ่านเป็นบิล ทั้งที่ไม่ได้จ่ายเพิ่มสักบาท
                Text((allNotional ? "มูลค่า" : "รวม") + " $"
                     + String(format: "%.2f", knownWeeklyCost) + " / 7d")
                    .help(allNotional
                          ? "มูลค่าถ้ายิงผ่าน API ไม่ใช่เงินที่จ่ายจริง — บัญชี subscription จ่ายเหมาไปแล้ว"
                          : "รวมทั้งมูลค่าของบัญชีเหมาและเงินที่ไหลจริงของถังจ่ายตามใช้")
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
        HStack(alignment: .top, spacing: 8) {
            pinButton(item)
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
                // ข้อเท็จจริงซ้าย · เงินขวา — คนละประเภทกัน อย่าให้ไหลปนกันในประโยคเดียว
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let error = item.error {
                        Text(error).foregroundStyle(.red).lineLimit(2)
                    } else if item.local == true {
                        Text("ในเครือข่ายตัวเอง · ไม่มีโควตา")
                    } else if !item.isOfficial {
                        Text(primaryDetail(item))
                    } else {
                        Text("รีเซ็ต \(countdownText(to: item.resetAt, from: now))")
                    }
                    Spacer(minLength: 8)
                    if let label = costLabel(item, price: prefs.prices[item.id]) {
                        // nil แปลว่าไม่รู้ราคา — ห้ามแทนด้วย $0.00 เด็ดขาด (ดู costLabel)
                        Text(label).monospacedDigit()
                    } else if item.weekTokens > 0 && item.local != true {
                        Text("ราคาไม่ทราบ")
                    }
                }
                .font(.system(size: 10)).foregroundStyle(.secondary)

                // ป้ายสถานะผิดปกติ — เป็นก้อนแยก จะได้ไม่ลากประโยคยาวไปตัดบรรทัดมั่ว
                let flags = statusFlags(item)
                if !flags.isEmpty {
                    HStack(spacing: 5) {
                        ForEach(flags, id: \.text) { flag in
                            Text(flag.text)
                                .font(.system(size: 9.5, weight: .medium))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(flag.tint.opacity(0.16), in: Capsule())
                                .foregroundStyle(flag.tint)
                                .help(flag.hint)
                        }
                        Spacer(minLength: 0)
                    }
                }
            }
        }
        .padding(13)
        .background {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(model.designStyle == .colorful
                      ? AnyShapeStyle(cardFill(for: item))
                      : AnyShapeStyle(model.designStyle.cardGradient))
        }
        .overlay {
            // ขอบนอก + ขอบสว่างด้านบน ซ้อนกันสองชั้นตามดีไซน์
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(cardStroke(for: item), lineWidth: 1)
                .overlay {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(model.designStyle.rimHighlight, lineWidth: 1)
                        .opacity(0.55)
                }
        }
        .shadow(color: model.designStyle == .native ? Color.black.opacity(0.07) : .clear,
                radius: 7, y: 2)
    }

    private func pinButton(_ item: UsageItem) -> some View {
        Button {
            prefs.togglePin(item.id)
        } label: {
            Image(systemName: prefs.pinned.contains(item.id) ? "pin.fill" : "pin")
                .font(.system(size: 11))
                .frame(width: 20, height: 20)
        }
        .buttonStyle(.plain)
        .disabled(!prefs.canPin(item.id))
        .help(prefs.pinned.contains(item.id)
              ? "เอาออกจากแถบเมนู"
              : (prefs.canPin(item.id)
                 ? "ปักหมุดขึ้นแถบเมนู"
                 : "ปักได้สูงสุด \(prefs.maxPins) ถัง"))
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


    /// ข้อความหลักฝั่งซ้าย — สั้นที่สุดที่ยังบอกอะไรได้
    private func primaryDetail(_ item: UsageItem) -> String {
        item.tokens > 0 ? item.tokensText : "ยังไม่เริ่มบล็อกใหม่"
    }

    private struct StatusFlag { let text: String; let tint: Color; let hint: String }

    /// เฉพาะเรื่องที่ผิดปกติ — ปกติแล้วต้องว่าง ถ้าขึ้นทุกแถวผู้ใช้จะเลิกอ่าน
    private func statusFlags(_ item: UsageItem) -> [StatusFlag] {
        var flags: [StatusFlag] = []
        if let active = item.activeLimit {
            flags.append(StatusFlag(text: "ชนลิมิต \(active)", tint: .red,
                                    hint: "โควตานี้เต็มแล้ว รอรีเซ็ตหรือสลับโมเดล"))
        }
        // รู้ว่ามีเพดาน แต่แคชเก่าจนหน้าต่างหมุนไปแล้ว — เปิด /usage ครั้งเดียวก็กลับมามีตัวเลข
        if !item.isOfficial, let age = item.dataAge(now: now) {
            flags.append(StatusFlag(text: "โควตาเก่า \(ageText(age))", tint: .orange,
                                    hint: "เปิด /usage ใน Claude Code แล้วรอไม่เกิน 60 วินาที"))
        } else if !item.isOfficial, item.local != true, item.error == nil {
            flags.append(StatusFlag(text: "ยังไม่รู้เพดาน", tint: .secondary,
                                    hint: "ผู้ให้บริการนี้ไม่ได้บอกโควตาคงเหลือมาในไฟล์ใดๆ"))
        }
        if certainty(confidence: item.confidence) == .atLeast {
            flags.append(StatusFlag(text: "≥ ใช้ต่อหลังเช็ค", tint: .secondary,
                                    hint: "มีการใช้งานหลังตัวเลขล่าสุด ของจริงสูงกว่าที่แสดง"))
        }
        return flags
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
