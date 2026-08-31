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
    /// หน้าตั้งค่าขอให้ติดตั้งโค้ดใหม่ — งานจริงอยู่ที่ AppDelegate เพราะต้องถามยืนยัน
    /// และต้องอยู่รอดหลัง popover ปิดไปแล้ว
    static let aiUsageInstallUpdate = Notification.Name("AIUsage.installUpdate")
}

struct PopoverView: View {
    @ObservedObject var model: UsageModel
    // ต้องผูกตรงนี้ด้วย @ObservedObject แยกจาก model — Preferences เป็น ObservableObject
    // คนละตัว ถ้า view ดูแค่ model ปุ่มหมุดจะกดแล้วค่าบันทึกจริงแต่จอไม่วาดใหม่
    @ObservedObject var prefs: Preferences
    @State private var now = Date()
    // ทุก 20 วิพอ — นับถอยหลังละเอียดระดับนาทีอยู่แล้ว
    // การวาดใหม่ทุกวินาทีทำให้พื้นที่ tooltip ถูกลงทะเบียนใหม่ตลอด
    // hover ค้างอยู่ระหว่างนั้น tooltip จะไปโผล่ผิดที่
    private let tick = Timer.publish(every: 20, on: .main, in: .common).autoconnect()

    private var snapshotAge: TimeInterval? {
        model.snapshot.generated == .distantPast ? nil : now.timeIntervalSince(model.snapshot.generated)
    }

    private var snapshotState: Freshness {
        freshness(snapshotAge: snapshotAge, wokeRecently: model.wokeRecently)
    }

    private var displayItems: [UsageItem] {
        let visible = model.snapshot.items.filter { item in
            guard !prefs.hidden.contains(item.id) else { return false }
            guard item.group != "กรอกเอง" else { return false }
            if item.group == "ยังไม่รู้จัก" {
                return item.tokens > 0 || item.weekTokens > 0 || item.error != nil
            }
            return true
        }
        // ลำดับผู้ใช้ก่อน แล้วถังเปล่าจมลงล่าง — ของที่มีตัวเลขจริงต้องเห็นก่อนโดยไม่ต้องเลื่อน
        // (partition แบบเสถียร ลำดับที่จัดไว้ภายในแต่ละกลุ่มคงอยู่)
        let ordered = applyUserOrder(visible, order: prefs.order) { $0.id }
        return ordered.filter { !isEmptyBucket($0) } + ordered.filter { isEmptyBucket($0) }
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
            if model.showSettings { settingsPane } else { mainPane }
        }
        .frame(width: 380, height: 560)
        .background { panelBackground }
        // accent ของสไตล์คุมสีปุ่ม/ลิงก์ทั้งบาน — ไม่งั้นสลับสไตล์แล้ว "ไม่เห็นต่าง"
        .tint(model.designStyle.accent)
        .preferredColorScheme(model.designStyle == .native ? nil : .dark)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(model.designStyle == .colorful ? 0.16 : 0.09), lineWidth: 1)
        }
        .onReceive(tick) { now = $0 }
        .onAppear { now = Date() }   // เปิด popover แล้วเวลาต้องสดทันที ไม่รอ tick แรก
        .onReceive(model.$snapshot) { _ in now = Date() }   // รีเฟรชสำเร็จ = อายุกลับเป็นศูนย์ให้เห็น
    }


    /// หน้าตั้งค่าอยู่ "ในตัว popover" ไม่ใช่ .sheet
    /// popover เป็น .transient มันปิดตัวเองเมื่อเสียโฟกัส sheet ที่เปิดจากมันจึงพากันหาย
    @ViewBuilder private var settingsPane: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button {
                    model.showSettings = false
                } label: {
                    Image(systemName: "chevron.left")
                    Text("กลับ")
                }
                .buttonStyle(.plain)
                Spacer()
                Text("ตั้งค่า").font(.system(size: 13, weight: .semibold))
                Spacer()
                Color.clear.frame(width: 44, height: 1)
            }
            .font(.system(size: 12))
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(chromeFill)
            Divider()
            SettingsView(model: model, prefs: prefs)
        }
    }

    @ViewBuilder private var mainPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let error = model.engineError {
                strip(icon: "exclamationmark.triangle.fill", text: error, tint: .red)
            } else if snapshotState != .fresh, let age = snapshotAge {
                strip(icon: "arrow.clockwise", text: "อัปเดตล่าสุด \(ageText(age)) ที่แล้ว",
                      tint: snapshotState == .dead ? .red : .orange)
            }
            // สูงคงที่เสมอ — แถบที่โผล่/หายตอนกดหมุดคือสาเหตุที่เนื้อหาเด้งขึ้นลง
            HStack(spacing: 8) {
                if prefs.pinned.isEmpty {
                    Text("แถบเมนู: อัตโนมัติ — ทุกถังที่มีตัวเลข")
                    Spacer()
                } else {
                    Text("แถบเมนู: ปักหมุดไว้ \(prefs.pinned.count)")
                    Spacer()
                    Button("ยกเลิกทั้งหมด → อัตโนมัติ") { prefs.clearPins() }
                        .buttonStyle(.plain)
                        .foregroundStyle(.tint)
                }
            }
            .font(.system(size: 11))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .frame(height: 30)
            ScrollView {
                VStack(alignment: .leading, spacing: 9) {
                    ForEach(displayItems) { item in row(item) }
                    if displayItems.isEmpty {
                        Text("ยังไม่มีข้อมูล").foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center).padding(.vertical, 40)
                    }
                }.padding(14)
            }
            Divider()
            footer
        }
    }

    private var header: some View {
        HStack(spacing: 9) {
            // ไม่มีกล่องรองไอคอน — chrome ยิ่งน้อย กระจกยิ่งเบา
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(model.designStyle.accent)
            VStack(alignment: .leading, spacing: 1) {
                Text("AI Usage").font(.system(size: 13.5, weight: .semibold))
                Text("โควตาตามบัญชีและ provider").font(.system(size: 10)).foregroundStyle(.primary.opacity(0.55))
            }
            Spacer()
            Button { refreshEngine() } label: {
                Image(systemName: "arrow.clockwise")
            }.buttonStyle(.borderless).help("รีเฟรชเดี๋ยวนี้")
            Button { model.showSettings = true } label: {
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
        // ทุกแบบต้องมีชั้นทึบรองเสมอ — vibrancy อย่างเดียวปล่อยให้วอลเปเปอร์
        // ทะลุขึ้นมาจนตัวหนังสืออ่านไม่ออก ความอ่านออกมาก่อนความสวย
        case .darkGlass:
            // hudWindow blur แรงกว่า popover — ชั้นทึบจึงบางลงได้โดยตัวหนังสือยังอ่านออก
            // (บทเรียนเดิมคือ "ห้ามใสสนิท" ไม่ใช่ "ต้องทึบ 90%")
            ZStack {
                VisualEffectBackground(material: .hudWindow)
                Color(red: 0.07, green: 0.07, blue: 0.10).opacity(0.62)
            }
        case .native:
            // native แปลว่าทึบและแบนแบบหน้าต่างระบบ — ไม่มี blur ให้ต่างจาก
            // Liquid Glass ชัดๆ ไม่ใช่มืดพอกันจนสลับแล้วมองไม่ออก
            Color(nsColor: .windowBackgroundColor)
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
        case .darkGlass: return Color.white.opacity(0.02)
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


    /// ถังที่ไม่มีอะไรจะบอกเลย — ไม่มี % ไม่มี token ไม่มี error
    /// การ์ดเปล่าที่สูงเท่าการ์ดข้อมูลจริงทำให้ครึ่งหนึ่งของ popover เป็นขีดกับจุดประ
    private func isEmptyBucket(_ item: UsageItem) -> Bool {
        item.error == nil && item.pct == nil && item.weekPct == nil
            && item.tokens == 0 && item.weekTokens == 0
    }

    @ViewBuilder private func row(_ item: UsageItem) -> some View {
        if item.error == nil && displayableWindows(item).isEmpty {
            compactRow(item)
        } else {
        HStack(alignment: .top, spacing: 8) {
            pinButton(item)
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    providerMark(item.group)
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            Text(item.group).font(.system(size: 12, weight: .semibold))
                                .lineLimit(1).fixedSize()
                            // จุดแดง = ชนลิมิตแล้ว ไม่กินความสูงเหมือนป้ายเดิม
                            if let active = item.activeLimit {
                                Circle().fill(Color.red).frame(width: 5, height: 5)
                                    .help("ชนลิมิต \(active) — รอรีเซ็ตหรือสลับโมเดล")
                            }
                            // ไอคอนจาง = เคยรู้เพดานแต่แคชเก่าไปแล้ว
                            if let age = staleQuotaAge(item) {
                                Image(systemName: "arrow.clockwise")
                                    .font(.system(size: 8))
                                    .foregroundStyle(.secondary.opacity(0.55))
                                    .help("โควตาเก่า \(ageText(age)) — เปิด /usage ใน Claude Code แล้วรอไม่เกิน 60 วินาที")
                            } else if noQuotaSource(item) {
                                // ไม่งั้นแถวจะขึ้น — เปล่าๆ โดยไม่มีอะไรบอกว่าทำไม
                                Image(systemName: "questionmark.circle")
                                    .font(.system(size: 8))
                                    .foregroundStyle(.secondary.opacity(0.55))
                                    .help(item.local == true
                                          ? "รันในเครือข่ายตัวเอง ไม่มีโควตาให้นับ"
                                          : "ผู้ให้บริการนี้ไม่ได้บอกโควตาคงเหลือมาในไฟล์ใดๆ")
                            }
                        }
                        Text(item.label).font(.system(size: 10.5)).foregroundStyle(.primary.opacity(0.66))
                    }
                    if let plan = item.plan { Text(plan).font(.system(size: 9, weight: .medium))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(providerColor(item.group).opacity(0.10)).clipShape(Capsule()) }
                    Spacer()
                    if item.error != nil {
                        Text("พัง").font(.system(size: 10, weight: .semibold)).foregroundStyle(.red)
                    }
                    // ไม่มีตัวเลขใหญ่ตรงนี้ — ตารางข้างล่างบอกครบแล้วว่าหน้าต่างไหนเท่าไหร่
                    // ตัวเลขเดียวที่ไม่บอกว่าเป็นของ 5h หรือ 7d ทำให้สับสนมากกว่าช่วย
                }
                // ตารางสองแถวเสมอ (5h, 7d) — ความยาวคงที่ทำให้ทุกการ์ดสูงเท่ากันและกวาดตาลงคอลัมน์ได้
                ForEach(displayableWindows(item), id: \.label) { window in
                    HStack(spacing: 8) {
                        Text(window.label)
                            .font(.system(size: 10, weight: .semibold, design: .rounded))
                            .foregroundStyle(.primary.opacity(0.62))
                            .lineLimit(1)
                            // 32 พอกับป้ายโมเดลอย่าง "Fable" — 20 เดิมพอแค่ "5h"/"7d"
                            .frame(width: 32, alignment: .leading)
                        bar(window, tint: item.tint)
                        Text(pctText(window.pct, window.sure))
                            .font(.system(size: 10, weight: .medium, design: .rounded))
                            .monospacedDigit()
                            .frame(width: 42, alignment: .trailing)
                        Text(resetColumnText(window.resetAt))
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                            .frame(width: 56, alignment: .trailing)
                    }
                    .frame(height: 16)
                }
                if let note = rowFootnote(item, price: prefs.prices[item.id], now: now) {
                    Text(note).font(.system(size: 10)).foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .fill(model.designStyle == .colorful
                      ? AnyShapeStyle(cardFill(for: item))
                      : AnyShapeStyle(model.designStyle.cardGradient))
        }
        .overlay {
            // ขอบชั้นเดียว + แสงขอบบนจางๆ — สองเส้นหนาซ้อนกันคือสิ่งที่ทำให้ดู "หนา"
            // native ไม่มีแสงขอบเลย: กระจกคือภาษาของสไตล์ A ไม่ใช่ของหน้าต่างระบบ
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(cardStroke(for: item), lineWidth: model.designStyle == .native ? 1 : 0.5)
                .overlay {
                    RoundedRectangle(cornerRadius: 15, style: .continuous)
                        .strokeBorder(model.designStyle.rimHighlight, lineWidth: 1)
                        .opacity(model.designStyle == .colorful ? 0.55
                                 : model.designStyle == .native ? 0 : 0.35)
                }
        }
        .shadow(color: model.designStyle == .native ? Color.black.opacity(0.07) : .clear,
                radius: 7, y: 2)
        }
    }

    /// การ์ดเปล่า — สองบรรทัดสั้นๆ: ชื่อครบไม่พับ · เหตุผล/มูลค่าได้ทั้งแถวไม่โดนตัด
    /// (บรรทัดเดียวเคยลอง: ข้อความท้ายแถวบีบชื่อจนพับ แล้วตัวเลขโดนตัดเป็น "$5…")
    /// ยังกดหมุดและอ่าน tooltip ได้ครบ แค่ไม่กิน 3 บรรทัดเหมือนการ์ดข้อมูล
    @ViewBuilder private func compactRow(_ item: UsageItem) -> some View {
        HStack(spacing: 8) {
            pinButton(item)
            providerMark(item.group)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(item.group).font(.system(size: 12, weight: .semibold))
                        .lineLimit(1).fixedSize()
                    Text(item.label).font(.system(size: 10.5))
                        .foregroundStyle(.primary.opacity(0.66)).lineLimit(1)
                    if let plan = item.plan {
                        Text(plan).font(.system(size: 9, weight: .medium))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(providerColor(item.group).opacity(0.10)).clipShape(Capsule())
                    }
                    // สัญญาณเดียวกับการ์ดเต็ม — ผู้ใช้ยังเห็นว่าทำไมไม่มีเลข
                    if let age = staleQuotaAge(item) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 8)).foregroundStyle(.secondary.opacity(0.55))
                            .help("โควตาเก่า \(ageText(age)) — เปิด /usage ใน Claude Code แล้วรอไม่เกิน 60 วินาที")
                    }
                }
                Text(rowFootnote(item, price: prefs.prices[item.id], now: now)
                     ?? (item.local == true ? "ไม่มีโควตา" : "ยังไม่มีข้อมูล"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .lineLimit(1)
                    .help(item.local == true
                          ? "รันในเครือข่ายตัวเอง ไม่มีโควตาให้นับ"
                          : "ยังไม่มีเลขโควตาที่เชื่อได้ของถังนี้ — ดูไอคอนหน้าชื่อว่าเพราะอะไร")
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 13).padding(.vertical, 8)
        .background(cardFill(for: item).opacity(0.6),
                    in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }


    /// คอลัมน์เวลารีเซ็ต — ว่างเมื่อไม่มีหรือรีเซ็ตผ่านไปแล้ว
    /// "รีเซ็ตแล้ว" ที่ค้างโชว์คือ noise: เลขในแถวนั้นสดกว่าข้อความนี้เสมอ
    private func resetColumnText(_ resetAt: Date?) -> String {
        guard let resetAt, resetAt > now else { return "" }
        return countdownText(to: resetAt, from: now)
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
        case .darkGlass: return Color.white.opacity(0.12)
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
            RoundedRectangle(cornerRadius: 8.5, style: .continuous)
                .fill(providerColor(group).opacity(model.designStyle == .colorful ? 0.18 : 0.10))
            ProviderLogo(group: group, size: 17,
                         tint: model.designStyle == .colorful ? providerColor(group) : .primary)
        }
        .frame(width: 29, height: 29)
    }

    private func pctText(_ pct: Double?, _ certaintyValue: Certainty) -> String {
        guard let pct, certaintyValue != .unknown else { return "—" }
        return String(format: "%.0f%%", pct)
    }


    /// เคยรู้เพดานมาก่อน (มี dataFetchedAt) แต่แคชเก่าจนหน้าต่างหมุนไปแล้ว — nil คือไม่ต้องขึ้นไอคอน
    private func staleQuotaAge(_ item: UsageItem) -> TimeInterval? {
        guard !item.isOfficial else { return nil }
        return item.dataAge(now: now)
    }

    /// ไม่เคยมีแหล่งเพดานเลย (Qwen Cloud, GLM, spark) — คนละเรื่องกับแคชเก่า
    /// ที่เปิด /usage แล้วหาย อันนี้เปิดยังไงก็ไม่มา ต้องบอกให้ต่างกัน
    private func noQuotaSource(_ item: UsageItem) -> Bool {
        item.error == nil && !item.isOfficial && item.dataAge(now: now) == nil
    }

    /// รางกับแถบเปล่าๆ ไม่มีป้ายกับตัวเลข — สองอย่างนั้นกลายเป็นคอลัมน์ของตารางแล้ว
    private func bar(_ window: WindowRow, tint: Color) -> some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.12))
                if let pct = window.pct, window.sure != .unknown {
                    let known = geometry.size.width * min(1, max(0, pct / 100))
                    Capsule().fill(model.designStyle == .colorful ? providerColorForTint(tint) : tint)
                        .frame(width: known)
                    if window.sure == .atLeast {
                        // lower_bound สื่อด้วยโซนจางนี้อย่างเดียว ห้ามเติมเครื่องหมาย ≥ กลับมา
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
        }.frame(height: 4)
    }

    private func providerColorForTint(_ tint: Color) -> Color {
        tint
    }
}

struct WindowRow {
    let label: String
    let pct: Double?
    let sure: Certainty
    let resetAt: Date?
}

/// สองแถวหลัก (5h, 7d) + gauge เฉพาะโมเดลที่ Anthropic แถมมา (เช่น weekly ของ Fable)
func windowRows(_ item: UsageItem) -> [WindowRow] {
    // resetAt คือเวลาของแถว 5h — ถ้า 5h ไม่มีข้อมูล (เช่น Qwen Cloud ที่ weekly เต็ม)
    // เวลานั้นเป็นของ weekly จริงๆ ต้องไปโชว์ที่แถว 7d ไม่ใช่หายไปเฉยๆ
    let resetOnWeek = item.pct == nil && item.weekPct != nil
    return [WindowRow(label: "5h", pct: item.pct,
               sure: certainty(confidence: item.confidence),
               resetAt: resetOnWeek ? nil : item.resetAt),
     WindowRow(label: "7d", pct: item.weekPct,
               sure: certainty(confidence: item.weekConfidence ?? item.confidence),
               // ถังที่บอกเวลารีเซ็ตของสัปดาห์มาด้วย (Codex, Claude Code) ใช้ของตัวเอง
               // ที่เหลือค่อยตกกลับไปใช้ช่องเดียวตามเดิม
               resetAt: item.weekResetAt ?? (resetOnWeek ? item.resetAt : nil))]
    + item.modelWindows.map { mw in
        WindowRow(label: mw.label, pct: mw.pct,
                  sure: certainty(confidence: mw.confidence),
                  resetAt: mw.resetAt)
    }
}


/// เฉพาะหน้าต่างที่มีเลขจริงให้ดู — แถวจุดประกับขีดไม่บอกอะไรและทำให้ popover รก
/// ถังที่ไม่เหลือสักแถวจะถูกวาดแบบบรรทัดเดียวแทน
func displayableWindows(_ item: UsageItem) -> [WindowRow] {
    windowRows(item).filter { $0.pct != nil && $0.sure != .unknown }
}

/// บรรทัดเดียวใต้แถบ — สั้นพอที่จะไม่ตัดบรรทัด nil เมื่อไม่มีอะไรต้องบอก
func rowFootnote(_ item: UsageItem, price: Price?, now: Date) -> String? {
    if let error = item.error { return String(error.prefix(40)) }
    if item.local == true { return nil }
    var parts: [String] = []
    if item.tokens > 0 { parts.append(item.tokensText) }
    if let cost = costLabel(item, price: price) { parts.append(cost) }
    return parts.isEmpty ? nil : parts.joined(separator: " · ")
}

struct ProviderLogo: View {
    let group: String
    let size: CGFloat
    var tint: Color = .primary

    private var asset: String? {
        switch group {
        case "Claude Code": return "claude"
        case "Codex": return "codex"
        case "GLM": return "zai"
        case "Qwen Cloud": return "qwen"
        default: return nil
        }
    }

    /// แคชข้ามทุก instance — เดิมอ่าน SVG จากดิสก์ใหม่ทุกครั้งที่วาด (ทุกแถว ทุก tick)
    private static var cache: [String: NSImage] = [:]
    private static func image(_ asset: String) -> NSImage? {
        if let hit = cache[asset] { return hit }
        guard let url = Bundle.main.url(forResource: asset, withExtension: "svg"),
              let img = NSImage(contentsOf: url) else { return nil }
        cache[asset] = img
        return img
    }

    var body: some View {
        if let asset, let nsImage = Self.image(asset) {
            Image(nsImage: nsImage).renderingMode(.template).resizable().scaledToFit()
                .foregroundStyle(tint).frame(width: size, height: size)
        } else {
            Image(systemName: "circle.dashed").frame(width: size, height: size)
        }
    }
}
