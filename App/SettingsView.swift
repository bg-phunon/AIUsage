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
    @State private var inputText = ""
    @State private var outputText = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("แสดง \(shown) จาก \(model.snapshot.items.count) ถัง")
                Spacer()
                Button("เปิดทั้งหมด") {
                    for item in model.snapshot.items {
                        prefs.setHidden(item.id, false)
                    }
                }
                .buttonStyle(.plain).foregroundStyle(.tint)
            }
            .font(.system(size: 11)).foregroundStyle(.secondary)
            .padding(.horizontal, 14).padding(.vertical, 10)
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(model.snapshot.items) { item in
                        row(item)
                        Divider()
                    }
                }
            }
            Divider()
            designStylePicker
        }
        .frame(width: 460, height: 620)
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

    private var shown: Int {
        model.snapshot.items.filter { !prefs.hidden.contains($0.id) }.count
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
