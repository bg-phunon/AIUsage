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

/// หน้าตั้งค่า — แสดง/ซ่อนถัง และใส่ราคาเอง
///
/// `prefs` แยกจาก `model` เพราะ Preferences เป็น ObservableObject คนละตัว
/// (ดูหมายเหตุใน PopoverView) ถ้าประกาศแค่ @ObservedObject var model แล้วอ่าน
/// model.prefs.xxx เฉยๆ หน้านี้จะไม่วาดใหม่ตอนกดสวิตช์หรือบันทึกราคา
struct SettingsView: View {
    @ObservedObject var model: UsageModel
    @ObservedObject var prefs: Preferences
    @State private var editing: String?
    @State private var updateState: UpdateState?
    @State private var inputText = ""
    @State private var outputText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("แสดง \(shown) จาก \(configurableItems.count) ถัง")
                Spacer()
                Button("เปิดทั้งหมด") {
                    for item in configurableItems {
                        prefs.setHidden(item.id, false)
                    }
                }
                .buttonStyle(.plain).foregroundStyle(.tint)
            }
            .font(.system(size: 11)).foregroundStyle(.secondary)
            .padding(.horizontal, 14).padding(.vertical, 10)
            Divider()

            // ทั้งหน้าต้องเลื่อนเป็นก้อนเดียว — เคยให้เฉพาะรายการถังเลื่อนได้ พอส่วนล่าง
            // งอกขึ้นสองบล็อก ช่องรายการเหลือแถวเดียวครึ่งจนอ่านไม่ออก ส่วนที่ตรึงไว้
            // มีได้แค่หัวตารางบรรทัดเดียวเท่านั้น
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(configurableItems) { item in
                        row(item)
                        Divider()
                    }
                    versionRow
                    Divider()
                    barDensityPicker
                    Divider()
                    tagPositionToggle
                    Divider()
                    liveUsageSection
                    Divider()
                    designStylePicker
                }
            }
        }
        // ห้ามตั้งขนาดตายตัว — เคยเป็น 460x620 จากยุคที่เปิดเป็น sheet แยก
        // พอฝังใน popover กว้าง 380 ขอบขวาโดนตัด ปุ่ม "แก้ราคา" กดไม่ได้เลย
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// เวอร์ชันที่ติดตั้ง + ทางลัดติดตั้งโค้ดใหม่
    ///
    /// อ่านสถานะตอนหน้านี้ปรากฏครั้งเดียว ไม่ใช่ทุกครั้งที่ body วาดใหม่ — body
    /// วาดใหม่ทุกครั้งที่กดสวิตช์ไหนก็ได้ในหน้านี้ ไม่มีเหตุผลจะไปสแกนไฟล์ซ้ำ
    @ViewBuilder private var versionRow: some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text("เวอร์ชัน").font(.system(size: 12, weight: .semibold))
                Text(updateState.map { updateMenuTitle($0, now: Date()) } ?? "กำลังตรวจ…")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer()
            if updateState?.isActionable == true {
                Button("ติดตั้ง") {
                    NotificationCenter.default.post(name: .aiUsageInstallUpdate, object: nil)
                }
                .font(.system(size: 11))
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
        .onAppear { updateState = currentUpdateState() }
    }

    /// จอมีรอยบากเหลือที่ให้ status item ทุกแอปรวมกันแค่ 772 pt — ของเราเต็มที่กิน 296
    /// เกินเมื่อไหร่ macOS ซ่อนของเราไว้ใต้รอยบาก ตัวเลือกนี้คือการเลือกว่าจะยอมเสียอะไร
    private var barDensityPicker: some View {
        VStack(alignment: .leading, spacing: 7) {
            VStack(alignment: .leading, spacing: 1) {
                Text("ความกะทัดรัดของแถบเมนู").font(.system(size: 12, weight: .semibold))
                Text("จอมีรอยบากมีที่จำกัด — สลับเองตอนต่อจอนอก")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Picker("", selection: Binding(get: { prefs.barDensity },
                                          set: { prefs.setBarDensity($0) })) {
                ForEach(BarDensity.allCases) { density in
                    Text(density.title).tag(density)
                }
            }
            .pickerStyle(.segmented).labelsHidden()
            Text(prefs.barDensity.subtitle)
                .font(.system(size: 10)).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    /// ป้ายบัญชี (de/mo/wo) บนแถบเมนู — ใต้โลโก้ประหยัดที่ · ข้างโลโก้อ่านง่ายกว่า
    private var tagPositionToggle: some View {
        VStack(spacing: 0) {
            toggleRow(title: "ป้ายบัญชีใต้โลโก้",
                      subtitle: "ปิดแล้วป้ายจะอยู่ข้างโลโก้แทน",
                      isOn: Binding(get: { prefs.tagBelowLogo },
                                    set: { prefs.setTagBelowLogo($0) }))
            toggleRow(title: "เตือนตอนใกล้ชนลิมิต",
                      subtitle: "เด้งครั้งเดียวต่อถังต่อขั้น ที่ 80% และ 95%",
                      isOn: Binding(get: { prefs.notifyNearLimit },
                                    set: { prefs.setNotifyNearLimit($0)
                                             if $0 { LimitNotifier().requestPermission() } }))
            toggleRow(title: "ชวนติดตั้งเมื่อมีโค้ดใหม่",
                      subtitle: "เด้งหลังไฟล์นิ่งเกิน 10 นาที กดติดตั้งจากใบแจ้งได้เลย",
                      isOn: Binding(get: { prefs.notifyOnUpdate },
                                    set: { prefs.setNotifyOnUpdate($0)
                                             if $0 { UpdateNotifier().requestPermission() } }))
            toggleRow(title: "เปิดเองตอนเข้าระบบ",
                      subtitle: "ขึ้นบนแถบเมนูทันทีที่เข้าเครื่อง ไม่ต้องเปิดแอปเอง",
                      isOn: Binding(get: { prefs.launchAtLogin },
                                    set: { prefs.setLaunchAtLogin($0)
                                             LaunchAtLogin.set($0) }))
        }
    }

    /// % ทางการจาก endpoint ของ Anthropic — ปิดไว้เป็นค่าเริ่มต้นสำหรับเครื่องใหม่
    ///
    /// เปิดแล้วเอนจินจะอ่าน OAuth token ของ Claude Code จาก Keychain ยิงไปที่
    /// api.anthropic.com แล้วเขียน token ที่ถูก rotate กลับลง Keychain item เดิม
    /// นั่นคือการแตะ credential ของผู้ใช้ จึงต้องบอกให้ครบก่อน ไม่ใช่เปิดเงียบๆ
    ///
    /// สถานะที่โชว์มาจาก snapshot (ผลจริงรอบล่าสุด) ไม่ใช่จาก UserDefaults ฝั่งเดียว
    /// เพราะเครื่องที่ใช้มาก่อนมีสวิตช์นี้เก็บค่าไว้ใน config.json ของเอนจิน
    private var liveUsageSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            toggleRow(title: "ถาม % ทางการจาก Anthropic",
                      subtitle: "ปิดอยู่ยังมี % ให้ดู แต่มาจาก log ในเครื่องแทน",
                      isOn: Binding(get: { prefs.liveUsage ?? model.snapshot.liveUsage ?? false },
                                    set: { prefs.setLiveUsage($0) }))
            Text("อ่าน OAuth token ของ Claude Code จาก Keychain · คุยกับ "
                 + "api.anthropic.com เท่านั้น · เขียน token ที่ระบบหมุนใหม่กลับที่เดิม")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 14)
        }
        .padding(.bottom, 8)
    }

    private func toggleRow(title: String, subtitle: String, isOn: Binding<Bool>) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 12, weight: .semibold))
                Text(subtitle).font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer()
            Toggle("", isOn: isOn)
                .toggleStyle(.switch).controlSize(.mini).labelsHidden()
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    /// ย้ายมาจากหน้าตั้งค่าเดิมที่ถูกรวมทิ้งไปแล้ว — ยังเป็นฟีเจอร์ที่ต้องเก็บไว้
    private var designStylePicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("รูปแบบหน้าตา").font(.system(size: 12, weight: .semibold))
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
                        if model.designStyle == style {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(style.accent)
                        }
                    }
                    .padding(7)
                    .background(model.designStyle == style ? style.accent.opacity(0.12) : Color.clear,
                                in: RoundedRectangle(cornerRadius: 8))
                }.buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    /// แถวที่ผู้ใช้ตั้งค่าได้จริง — "กรอกเอง" ถูกระบบซ่อนถาวรอยู่แล้ว
    /// เอามานับรวมจะได้เลขอย่าง "แสดง 7 จาก 10" ทั้งที่ตั้งได้แค่ 7
    /// เรียงตามลำดับผู้ใช้ — ลำดับในหน้านี้คือลำดับจริงทั้ง popover และแถบเมนู
    private var configurableItems: [UsageItem] {
        applyUserOrder(model.snapshot.items.filter { $0.group != "กรอกเอง" },
                       order: prefs.order) { $0.id }
    }

    private func move(_ item: UsageItem, up: Bool) {
        var ids = configurableItems.map(\.id)
        guard let i = ids.firstIndex(of: item.id) else { return }
        let j = up ? i - 1 : i + 1
        guard ids.indices.contains(j) else { return }
        ids.swapAt(i, j)
        prefs.setOrder(ids)
    }

    private var shown: Int {
        configurableItems.filter { !prefs.hidden.contains($0.id) }.count
    }

    @ViewBuilder
    private func row(_ item: UsageItem) -> some View {
        let isHidden = prefs.hidden.contains(item.id)
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 10) {
                Toggle("", isOn: Binding(
                    get: { !isHidden },
                    set: { prefs.setHidden(item.id, !$0) }))
                    .labelsHidden()
                    .help(isHidden ? "แสดงถังนี้" : "ซ่อนถังนี้")

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(item.group).font(.system(size: 12.5, weight: .semibold))
                        Text("· \(item.label)").font(.system(size: 11))
                            .foregroundStyle(.secondary)
                        if let plan = item.plan {
                            Text(plan).font(.system(size: 9.5))
                                .padding(.horizontal, 5).padding(.vertical, 1)
                                .background(Color.secondary.opacity(0.15))
                                .clipShape(Capsule())
                        }
                    }
                    priceLine(item)
                }
                Spacer()
                // จัดลำดับ — ลำดับนี้คือลำดับจริงทั้งการ์ดใน popover และ segment บนแถบ
                HStack(spacing: 1) {
                    Button { move(item, up: true) } label: {
                        Image(systemName: "chevron.up").frame(width: 16, height: 14)
                    }.help("เลื่อนขึ้น")
                    Button { move(item, up: false) } label: {
                        Image(systemName: "chevron.down").frame(width: 16, height: 14)
                    }.help("เลื่อนลง")
                }
                .buttonStyle(.plain)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(.secondary)
                if item.local != true {
                    Button(prefs.prices[item.id] == nil ? "ใส่ราคา" : "แก้ราคา") {
                        beginEditing(item)
                    }
                    .font(.system(size: 11))
                }
            }
            if editing == item.id { editor(item) }
        }
        .opacity(isHidden ? 0.5 : 1)
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    @ViewBuilder
    private func priceLine(_ item: UsageItem) -> some View {
        HStack(spacing: 6) {
            if item.local == true {
                Text("ในเครือข่ายตัวเอง · ไม่มีค่าใช้จ่าย").foregroundStyle(.secondary)
            } else if let price = prefs.prices[item.id] {
                Text(String(format: "$%.2f / $%.2f", price.inputPerMillion,
                            price.outputPerMillion)).monospaced()
                badge("ใส่เอง", .orange)
            } else if item.costKnown {
                Text("ตารางของ Anthropic").foregroundStyle(.secondary)
                if item.costKind == "notional" { badge("มูลค่า ไม่ใช่บิล", .secondary) }
            } else {
                Text("ยังไม่ได้ตั้งราคา").italic().foregroundStyle(.secondary)
            }
        }
        .font(.system(size: 11))
    }

    @ViewBuilder
    private func badge(_ text: String, _ tint: Color) -> some View {
        Text(text).font(.system(size: 9.5, weight: .medium))
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background(tint.opacity(0.18)).foregroundStyle(tint)
            .clipShape(Capsule())
    }

    @ViewBuilder
    private func editor(_ item: UsageItem) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                field("เข้า · USD / 1M", $inputText)
                field("ออก · USD / 1M", $outputText)
            }
            HStack(spacing: 10) {
                Button("บันทึก") { save(item) }.keyboardShortcut(.defaultAction)
                Button("ลบราคา") {
                    prefs.setPrice(item.id, nil); editing = nil
                }
                Button("ยกเลิก") { editing = nil }
                Spacer()
            }
            Text("ราคาผูกกับถัง ไม่ใช่โมเดล — ทุกโมเดลที่วิ่งผ่าน endpoint นี้กินกระเป๋าใบเดียวกัน")
                .font(.system(size: 10.5)).foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
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
