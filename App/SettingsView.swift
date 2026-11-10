import SwiftUI

/// ค่าใช้จ่าย 7 วันของถังนี้ — nil แปลว่าไม่รู้ ห้ามแทนด้วย 0
///
/// ราคาที่ผู้ใช้ใส่เองชนะตารางในตัวเสมอ เพราะเขารู้บิลจริงของเขา
func effectiveWeekCost(_ item: UsageItem, price: Price?) -> Double? {
    if let price {
        // snapshot ไม่ได้แยก token เข้า/ออกในระดับสัปดาห์ จึงใช้ค่าเฉลี่ยของสองอัตรา
        let rate = (price.inputPerMillion + price.outputPerMillion) / 2
        return Double(item.weekTokens) / 1_000_000 * rate
    }
    return item.costKnown ? item.weekCost : nil
}

/// ข้อความค่าใช้จ่าย — แยกให้ชัดว่าเป็นมูลค่าหรือเงินที่ไหลจริง
func costLabel(_ item: UsageItem, price: Price?) -> String? {
    guard let cost = effectiveWeekCost(item, price: price) else { return nil }
    let kind = (price == nil && item.costKind == "notional") ? "มูลค่า" : "ใช้ไป"
    return kind + " $" + String(format: "%.2f", cost) + " / 7 วัน"
}

/// สามแท็บแทนหน้ายาวที่ต้องเลื่อน — ผู้ใช้ไม่ชอบ scroll (2026-11-10)
enum SettingsTab: String, CaseIterable, Identifiable {
    case buckets, general, alerts
    var id: String { rawValue }
    var title: String {
        switch self {
        case .buckets: return "ถัง"
        case .general: return "ทั่วไป"
        case .alerts: return "แจ้งเตือน"
        }
    }
}

/// ย้ายถัง `moving` ไปอยู่ตำแหน่งของ `target` — ลากลงทับแถวไหนก็แทรกตรงนั้น
func reorderedIDs(_ ids: [String], moving: String, onto target: String) -> [String] {
    guard moving != target, let from = ids.firstIndex(of: moving),
          let to = ids.firstIndex(of: target) else { return ids }
    var out = ids
    out.remove(at: from)
    out.insert(moving, at: to)
    return out
}

/// หน้าตั้งค่า — กลุ่มแบบ System Settings ไม่มีเส้นกรอบ แยกเป็นแท็บ
///
/// `prefs` แยกจาก `model` เพราะ Preferences เป็น ObservableObject คนละตัว
/// (ดูหมายเหตุใน PopoverView) ถ้าประกาศแค่ @ObservedObject var model แล้วอ่าน
/// model.prefs.xxx เฉยๆ หน้านี้จะไม่วาดใหม่ตอนกดสวิตช์หรือบันทึกราคา
struct SettingsView: View {
    @ObservedObject var model: UsageModel
    @ObservedObject var prefs: Preferences
    @State private var tab: SettingsTab = .buckets
    @State private var editing: String?
    @State private var updateState: UpdateState?
    @State private var inputText = ""
    @State private var outputText = ""
    @State private var dragging: String?
    @Namespace private var tabSpace

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            tabBar
            Group {
                switch tab {
                case .buckets: bucketsTab
                case .general: generalTab
                case .alerts: alertsTab
                }
            }
            .id(tab)
            .transition(.opacity.combined(with: .offset(y: 6)))
        }
        .padding(14)
        .animation(.spring(response: 0.38, dampingFraction: 0.88), value: tab)
        .onAppear { updateState = currentUpdateState() }
    }

    // MARK: แท็บ

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(SettingsTab.allCases) { item in
                Button { tab = item } label: {
                    Text(item.title)
                        .font(.system(size: 12, weight: tab == item ? .semibold : .regular))
                        .foregroundStyle(tab == item ? Color.primary : Color.secondary)
                        .frame(maxWidth: .infinity).padding(.vertical, 5)
                        .background {
                            if tab == item {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(Color.primary.opacity(0.16))
                                    .matchedGeometryEffect(id: "tab", in: tabSpace)
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(3)
        .background(Color.primary.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    // MARK: ถัง

    /// แถวที่ผู้ใช้ตั้งค่าได้จริง — "กรอกเอง" ถูกระบบซ่อนถาวรอยู่แล้ว
    /// เรียงตามลำดับผู้ใช้ — ลำดับในหน้านี้คือลำดับจริงทั้ง popover และแถบเมนู
    private var configurableItems: [UsageItem] {
        applyUserOrder(model.snapshot.items.filter { $0.group != "กรอกเอง" },
                       order: prefs.order) { $0.id }
    }

    private var shown: Int {
        configurableItems.filter { !prefs.hidden.contains($0.id) }.count
    }

    private var bucketsTab: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                caption("แสดงใน popover · \(shown) จาก \(configurableItems.count)")
                Spacer()
                Button("เปิดทั้งหมด") {
                    for item in configurableItems { prefs.setHidden(item.id, false) }
                }
                .buttonStyle(.plain).font(.system(size: 11, weight: .medium)).foregroundStyle(.tint)
                .padding(.bottom, 6)
            }
            group {
                ForEach(Array(configurableItems.enumerated()), id: \.element.id) { index, item in
                    if index > 0 { separator }
                    bucketRow(item)
                }
            }
            Text("ลากเพื่อเรียงลำดับ · คลิกขวาที่แถวเพื่อใส่ราคาเอง")
                .font(.system(size: 10.5)).foregroundStyle(.secondary)
                .padding(.horizontal, 6).padding(.top, 8)
        }
    }

    @ViewBuilder private func bucketRow(_ item: UsageItem) -> some View {
        let isHidden = prefs.hidden.contains(item.id)
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Image(systemName: "line.3.horizontal")
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(.tertiary)
                ProviderLogo(group: item.group, size: 15)
                    .frame(width: 22, height: 22)
                    .background(Color.primary.opacity(0.08), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                VStack(alignment: .leading, spacing: 1) {
                    Text(item.displayLabel).font(.system(size: 12.5)).lineLimit(1)
                    if item.label != item.group {
                        Text(item.displayGroup).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                Spacer(minLength: 4)
                if prefs.prices[item.id] != nil {
                    Text("ราคาเอง").font(.system(size: 10)).foregroundStyle(.orange)
                }
                Text(isHidden ? "ซ่อน" : (item.plan ?? ""))
                    .font(.system(size: 10.5)).foregroundStyle(.secondary).lineLimit(1)
                Toggle("", isOn: Binding(get: { !isHidden }, set: { prefs.setHidden(item.id, !$0) }))
                    .toggleStyle(.switch).controlSize(.small).labelsHidden()
                    .help(isHidden ? "แสดงถังนี้" : "ซ่อนถังนี้")
            }
            .opacity(isHidden ? 0.5 : 1)
            if editing == item.id { editor(item) }
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(dragging == item.id ? Color.primary.opacity(0.06) : .clear)
        .contentShape(Rectangle())
        .draggable(item.id) {
            Text(item.displayLabel).font(.system(size: 12)).padding(6)
                .onAppear { dragging = item.id }
        }
        .dropDestination(for: String.self) { ids, _ in
            guard let moving = ids.first else { return false }
            withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                prefs.setOrder(reorderedIDs(configurableItems.map(\.id), moving: moving, onto: item.id))
            }
            dragging = nil
            return true
        }
        .contextMenu {
            if item.local != true {
                Button(prefs.prices[item.id] == nil ? "ใส่ราคาเอง…" : "แก้ราคา…") { beginEditing(item) }
                if prefs.prices[item.id] != nil {
                    Button("ลบราคาที่ใส่เอง") { prefs.setPrice(item.id, nil) }
                }
                Divider()
            }
            Button("เลื่อนขึ้น") { move(item, up: true) }
            Button("เลื่อนลง") { move(item, up: false) }
        }
        .help(priceHelp(item))
    }

    private func priceHelp(_ item: UsageItem) -> String {
        if item.local == true { return "ในเครือข่ายตัวเอง · ไม่มีค่าใช้จ่าย" }
        if let price = prefs.prices[item.id] {
            return String(format: "ราคาที่ใส่เอง $%.2f / $%.2f ต่อ 1M token", price.inputPerMillion,
                          price.outputPerMillion)
        }
        if item.costKnown {
            return item.costKind == "notional" ? "ตารางของ Anthropic · มูลค่า ไม่ใช่บิล" : "ตารางของ Anthropic"
        }
        return "ยังไม่ได้ตั้งราคา — คลิกขวาเพื่อใส่"
    }

    private func move(_ item: UsageItem, up: Bool) {
        var ids = configurableItems.map(\.id)
        guard let i = ids.firstIndex(of: item.id) else { return }
        let j = up ? i - 1 : i + 1
        guard ids.indices.contains(j) else { return }
        ids.swapAt(i, j)
        prefs.setOrder(ids)
    }

    // MARK: ทั่วไป

    private var generalTab: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 0) {
                caption("หน้าตา")
                HStack(spacing: 8) {
                    ForEach(DesignStyle.allCases) { style in styleThumb(style) }
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                caption("แถบเมนู")
                group {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("ความกะทัดรัด").font(.system(size: 12.5))
                        // จอมีรอยบากเหลือที่ให้ status item ทุกแอปรวมกันแค่ 772 pt — เกินเมื่อไหร่
                        // macOS ซ่อนของเราไว้ใต้รอยบาก ตัวเลือกนี้คือการเลือกว่าจะยอมเสียอะไร
                        Picker("", selection: Binding(get: { prefs.barDensity },
                                                      set: { prefs.setBarDensity($0) })) {
                            ForEach(BarDensity.allCases) { density in Text(density.title).tag(density) }
                        }
                        .pickerStyle(.segmented).labelsHidden()
                        Text(prefs.barDensity.subtitle).font(.system(size: 10.5)).foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 12).padding(.vertical, 10)
                    separator
                    toggleRow("ป้ายบัญชีใต้โลโก้", nil,
                              Binding(get: { prefs.tagBelowLogo }, set: { prefs.setTagBelowLogo($0) }))
                    separator
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("ถังบนแถบเมนู").font(.system(size: 12.5))
                            Text(prefs.pinned.isEmpty ? "อัตโนมัติ — ทุกถังที่มีตัวเลข"
                                                      : "ปักหมุดไว้ \(prefs.pinned.count) · คลิกขวาที่การ์ดเพื่อปัก/ถอด")
                                .font(.system(size: 10.5)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if !prefs.pinned.isEmpty {
                            Button("ล้างหมุด") { prefs.clearPins() }
                                .buttonStyle(.plain).font(.system(size: 11.5)).foregroundStyle(.tint)
                        }
                    }
                    .padding(.horizontal, 12).padding(.vertical, 8)
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                caption("ระบบ")
                group {
                    toggleRow("เปิดเองตอนเข้าเครื่อง", nil,
                              Binding(get: { prefs.launchAtLogin },
                                      set: { prefs.setLaunchAtLogin($0); LaunchAtLogin.set($0) }))
                    separator
                    // ความยินยอมเรื่อง credential — สถานะจริงมาจาก snapshot เพราะเครื่องที่ใช้มาก่อน
                    // เก็บสวิตช์นี้ไว้ใน config.json ของเอนจิน
                    toggleRow("ถาม % สดจาก CLI", "ไม่เสียโควตา · CLI ถือรหัสของมันเอง",
                              Binding(get: { prefs.liveUsage ?? model.snapshot.liveUsage ?? false },
                                      set: { prefs.setLiveUsage($0) }))
                        .help("ถาม Claude Code / Codex CLI ว่าใช้ไปเท่าไหร่ ถ้าถามไม่ได้จะอ่าน OAuth token "
                              + "ของ Claude Code จาก Keychain คุยกับ api.anthropic.com เท่านั้น "
                              + "แล้วเขียน token ที่ระบบหมุนใหม่กลับที่เดิม · ปิดอยู่ยังมี % จาก log ในเครื่อง")
                    separator
                    versionRow
                }
            }
        }
    }

    private func styleThumb(_ style: DesignStyle) -> some View {
        let selected = model.designStyle == style
        return Button {
            model.designStyle = style
            UserDefaults.standard.set(style.rawValue, forKey: "designStyle")
        } label: {
            VStack(spacing: 6) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(style == .darkGlass ? AnyShapeStyle(Color.primary.opacity(0.12))
                              : AnyShapeStyle(style.panelFill))
                    thumbContent(style).padding(8)
                }
                .frame(height: 56)
                .overlay {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(selected ? Color.accentColor : .clear, lineWidth: 2)
                }
                Text(style == .darkGlass ? "Liquid Glass" : style == .native ? "Native" : "Colorful")
                    .font(.system(size: 11, weight: selected ? .semibold : .regular))
                    .foregroundStyle(selected ? Color.primary : Color.secondary)
            }
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(style.subtitle)
    }

    @ViewBuilder private func thumbContent(_ style: DesignStyle) -> some View {
        switch style {
        case .darkGlass:
            HStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 5).fill(Color.primary.opacity(0.2))
                VStack(spacing: 4) {
                    RoundedRectangle(cornerRadius: 4).fill(Color.primary.opacity(0.15))
                    RoundedRectangle(cornerRadius: 4).fill(Color.primary.opacity(0.15))
                }
            }
        case .native:
            VStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { i in
                    RoundedRectangle(cornerRadius: 3).fill(Color.primary.opacity(i == 0 ? 0.22 : 0.14))
                }
            }
        case .colorful:
            VStack(spacing: 4) {
                RoundedRectangle(cornerRadius: 3).fill(Color.orange.opacity(0.85))
                RoundedRectangle(cornerRadius: 3).fill(Color.green.opacity(0.85))
                RoundedRectangle(cornerRadius: 3).fill(Color.indigo.opacity(0.85))
            }
        }
    }

    /// เวอร์ชันที่ติดตั้ง + ทางลัดติดตั้งโค้ดใหม่ · อ่านสถานะตอนเปิดหน้าและตอนกดตรวจเท่านั้น
    /// ไม่ใช่ทุกครั้งที่ body วาดใหม่ — ไม่มีเหตุผลจะไปสแกนไฟล์ซ้ำทุกครั้งที่กดสวิตช์
    private var versionRow: some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text(versionTitle).font(.system(size: 12.5))
                Text(updateState.map { updateMenuTitle($0, now: Date()) } ?? "กำลังตรวจ…")
                    .font(.system(size: 10.5)).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            if updateState?.isActionable == true {
                Button("ติดตั้ง") {
                    NotificationCenter.default.post(name: .aiUsageInstallUpdate, object: nil)
                }
                .buttonStyle(.plain).font(.system(size: 11.5, weight: .semibold)).foregroundStyle(.tint)
            } else {
                Button("ตรวจอีกครั้ง") {
                    withAnimation { updateState = currentUpdateState() }
                }
                .buttonStyle(.plain).font(.system(size: 11.5)).foregroundStyle(.tint)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
    }

    private var versionTitle: String {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "เวอร์ชัน \(version) · \(build)"
    }

    // MARK: แจ้งเตือน

    private var alertsTab: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 0) {
                caption("โควตา")
                group {
                    toggleRow("เตือนตอนใกล้ชนลิมิต", "ครั้งเดียวต่อถัง ที่ 80% และ 95%",
                              Binding(get: { prefs.notifyNearLimit },
                                      set: { prefs.setNotifyNearLimit($0)
                                             if $0 { LimitNotifier().requestPermission() } }))
                    separator
                    toggleRow("ใบรีเซ็ตใกล้หมดอายุ", "ล่วงหน้า 24 ชม. ถ้ายังไม่ได้ใช้",
                              Binding(get: { prefs.notifyResetExpiry },
                                      set: { prefs.setNotifyResetExpiry($0)
                                             if $0 { LimitNotifier().requestPermission() } }))
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                caption("อัปเดตแอป")
                group {
                    toggleRow("ติดตั้งอัปเดตเอง", "โค้ดนิ่ง 10 นาทีแล้วติดตั้งเลย · ไอคอนหาย 1–2 นาที",
                              Binding(get: { prefs.autoInstallUpdate },
                                      set: { prefs.setAutoInstallUpdate($0) }))
                    separator
                    toggleRow("ชวนก่อนติดตั้ง",
                              prefs.autoInstallUpdate ? "ไม่ต้องใช้เมื่อติดตั้งเองอยู่แล้ว"
                                                      : "เด้งใบแจ้งพร้อมปุ่มติดตั้ง",
                              Binding(get: { prefs.notifyOnUpdate },
                                      set: { prefs.setNotifyOnUpdate($0)
                                             if $0 { UpdateNotifier().requestPermission() } }))
                        .opacity(prefs.autoInstallUpdate ? 0.45 : 1)
                        .disabled(prefs.autoInstallUpdate)
                }
            }
        }
    }

    // MARK: ชิ้นส่วนร่วม

    private func caption(_ text: String) -> some View {
        Text(text).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            .padding(.horizontal, 6).padding(.bottom, 6)
    }

    /// กลุ่มแบบ System Settings — แผ่นจางๆ ไม่มีเส้นกรอบ
    private func group<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 0) { content() }
            .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var separator: some View {
        Rectangle().fill(Color.primary.opacity(0.08)).frame(height: 0.5).padding(.leading, 12)
    }

    private func toggleRow(_ title: String, _ subtitle: String?, _ isOn: Binding<Bool>) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 12.5))
                if let subtitle {
                    Text(subtitle).font(.system(size: 10.5)).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 8)
            Toggle("", isOn: isOn).toggleStyle(.switch).controlSize(.small).labelsHidden()
        }
        .padding(.horizontal, 12).padding(.vertical, subtitle == nil ? 9 : 8)
    }

    // MARK: ราคาที่ใส่เอง

    @ViewBuilder
    private func editor(_ item: UsageItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                field("เข้า · USD / 1M", $inputText)
                field("ออก · USD / 1M", $outputText)
            }
            HStack(spacing: 10) {
                Button("บันทึก") { save(item) }.keyboardShortcut(.defaultAction)
                Button("ลบราคา") { prefs.setPrice(item.id, nil); editing = nil }
                Button("ยกเลิก") { editing = nil }
                Spacer()
            }
            Text("ราคาผูกกับถัง ไม่ใช่โมเดล — ทุกโมเดลที่วิ่งผ่าน endpoint นี้กินกระเป๋าใบเดียวกัน")
                .font(.system(size: 10.5)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    @ViewBuilder
    private func field(_ label: String, _ text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
            TextField("0.00", text: text).frame(width: 90).monospaced()
        }
    }

    private func beginEditing(_ item: UsageItem) {
        let existing = prefs.prices[item.id]
        inputText = existing.map { String($0.inputPerMillion) } ?? ""
        outputText = existing.map { String($0.outputPerMillion) } ?? ""
        editing = item.id
    }

    private func save(_ item: UsageItem) {
        guard let input = Double(inputText), let output = Double(outputText),
              input >= 0, output >= 0 else { return }
        prefs.setPrice(item.id, Price(inputPerMillion: input, outputPerMillion: output))
        editing = nil
    }
}
