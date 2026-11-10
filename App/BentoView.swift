import SwiftUI

// MARK: - กติกาที่เทสต์ได้ (ไม่แตะ view)

/// ตัวเลขหัวของถัง = หน้าต่างที่ใช้ไปมากที่สุด — สิ่งที่จะชนก่อนคือสิ่งที่ต้องเห็นก่อน
func headlinePct(_ item: UsageItem) -> Double? {
    displayableWindows(item).compactMap(\.pct).max()
}

/// หน้าต่างที่ให้ตัวเลขหัว — ใช้บอกว่า "ของหน้าต่างไหน" และ "กลับมาเมื่อไหร่"
func headlineWindow(_ item: UsageItem) -> WindowRow? {
    displayableWindows(item).max { ($0.pct ?? 0) < ($1.pct ?? 0) }
}

/// ถังที่ขึ้นการ์ดใหญ่ — ที่ผู้ใช้กดเลือกไว้ก่อน ไม่งั้นตัวที่ใกล้ชนที่สุด
func heroItem(_ items: [UsageItem], selected: String?) -> UsageItem? {
    let ranked = items.filter { headlinePct($0) != nil }
    if let selected, let hit = ranked.first(where: { $0.id == selected }) { return hit }
    return ranked.max { (headlinePct($0) ?? 0) < (headlinePct($1) ?? 0) }
}

/// สีโผล่เฉพาะที่ต้องรีบดู — ต่ำกว่า 80% เป็นขาวเทา ทั้งบานจึงไม่รก
enum Severity: Equatable { case calm, warn, critical }

func severity(_ pct: Double?) -> Severity {
    guard let pct else { return .calm }
    if pct >= 95 { return .critical }
    if pct >= 80 { return .warn }
    return .calm
}

// MARK: - ชิ้นส่วนที่ขยับ

/// ตัวเลขนับขึ้นจาก 0 ตอนเปิด แล้วหมุนเปลี่ยนเมื่อค่าใหม่มา
struct RollingNumber: View {
    let value: Double
    let size: CGFloat
    var estimated = false
    @State private var shown: Double = 0

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            if estimated {
                Text("~").font(.system(size: size * 0.5, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Text("\(Int(shown.rounded()))")
                .font(.system(size: size, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .contentTransition(.numericText(value: shown))
            Text("%").font(.system(size: size * 0.4, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .onAppear {
            shown = 0
            withAnimation(.spring(response: 0.9, dampingFraction: 0.85).delay(0.05)) { shown = value }
        }
        .onChange(of: value) { _, new in
            withAnimation(.spring(response: 0.6, dampingFraction: 0.85)) { shown = new }
        }
    }
}

/// เกจโค้ง 270° แบบหน้าปัด Apple Watch — กวาดจาก 0 ตอนเปิด
struct ArcGauge: View {
    let pct: Double
    let sev: Severity
    let caption: String
    @State private var progress: Double = 0

    private var gradient: AngularGradient {
        let colors: [Color]
        switch sev {
        case .critical: colors = [Color(red: 1, green: 0.82, blue: 0.48), Color(red: 1, green: 0.54, blue: 0.36),
                                  Color(red: 1, green: 0.31, blue: 0.43)]
        case .warn: colors = [Color(red: 1, green: 0.88, blue: 0.55), .orange]
        case .calm: colors = [Color.accentColor.opacity(0.55), Color.accentColor]
        }
        return AngularGradient(colors: colors, center: .center,
                               startAngle: .degrees(0), endAngle: .degrees(270))
    }

    var body: some View {
        ZStack {
            // หมุนเฉพาะวง — ข้อความต้องตั้งตรง
            ZStack {
                Circle().trim(from: 0, to: 0.75)
                    .stroke(Color.primary.opacity(0.12), style: StrokeStyle(lineWidth: 9, lineCap: .round))
                Circle().trim(from: 0, to: 0.75 * progress)
                    .stroke(gradient, style: StrokeStyle(lineWidth: 9, lineCap: .round))
            }
            .rotationEffect(.degrees(135))
            Text(caption).font(.system(size: 10)).foregroundStyle(.secondary)
                .offset(y: 34)
        }
        .padding(4)
        .frame(width: 108, height: 108)
        .onAppear {
            progress = 0
            withAnimation(.spring(response: 1.1, dampingFraction: 0.9)) { progress = min(pct, 100) / 100 }
        }
        .onChange(of: pct) { _, new in
            withAnimation(.spring(response: 0.7, dampingFraction: 0.9)) { progress = min(new, 100) / 100 }
        }
    }
}

/// แถบบางหนึ่งเส้นต่อหน้าต่าง — เติมไล่ตาม `delay` ให้แต่ละการ์ดไม่ขึ้นพร้อมกันเป๊ะ
struct MiniMeter: View {
    let window: WindowRow?
    let label: String
    let delay: Double
    let now: Date
    @State private var progress: Double = 0

    private var pct: Double? {
        guard let window, window.sure != .unknown else { return nil }
        return window.pct
    }

    private var fill: Color {
        switch severity(pct) {
        case .critical: return Color(red: 1, green: 0.37, blue: 0.34)
        case .warn: return .orange
        case .calm: return Color.primary.opacity(0.85)
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Text(label).lineLimit(1).minimumScaleFactor(0.8).frame(width: 30, alignment: .leading)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.primary.opacity(0.10))
                    Capsule().fill(fill)
                        .frame(width: max(0, geo.size.width * progress))
                }
            }
            .frame(height: 4)
            Text(shortCountdown(window?.resetAt, now: now)).frame(width: 22, alignment: .trailing)
        }
        .font(.system(size: 9.5, weight: .medium, design: .rounded))
        .foregroundStyle(.secondary)
        .onAppear {
            progress = 0
            withAnimation(.spring(response: 0.9, dampingFraction: 0.9).delay(delay)) {
                progress = min(pct ?? 0, 100) / 100
            }
        }
        .onChange(of: pct) { _, new in
            withAnimation(.spring(response: 0.6, dampingFraction: 0.9)) { progress = min(new ?? 0, 100) / 100 }
        }
    }
}

/// รายละเอียดใบรีเซ็ตทีละบรรทัด — บอกเท่าที่รู้จริง และบอกตรงๆ เมื่อไม่รู้
func resetDetailLines(_ item: UsageItem, now: Date) -> [String] {
    let claude = item.group == "Claude Code"
    let use = claude ? "ใช้: พิมพ์ /limit-reset ใน Claude Code" : "ใช้: จากใน \(item.displayGroup) ตอนชนลิมิต"
    guard let count = item.limitResets else {
        return ["Claude Code ไม่ได้จดสถานะใบรีเซ็ตของบัญชีนี้ไว้",
                "ดูจำนวนจริง: พิมพ์ /usage ใน Claude Code ของบัญชีนี้"]
    }
    if count == 0 {
        if let back = item.limitResetAvailableAt, back > now {
            return ["ใช้ไปแล้ว · ได้ใบใหม่ใน \(countdownText(to: back, from: now))"]
        }
        return ["ไม่มีใบให้ใช้ตอนนี้"]
    }
    var lines: [String] = []
    let dates = item.limitResetsExpiring.filter { $0 > now }
    if item.limitResetsAtLeast {
        lines.append("มีอย่างน้อย 1 ใบ — Claude Code ไม่บอกจำนวนและวันหมดอายุ")
        lines.append("ดูจำนวนจริง: พิมพ์ /usage ใน Claude Code")
    } else if dates.isEmpty {
        lines.append("\(count) ใบ · ไม่ทราบวันหมดอายุ")
    } else {
        for (i, date) in dates.prefix(4).enumerated() {
            lines.append("ใบที่ \(i + 1) · ใช้ได้อีก \(countdownText(to: date, from: now))")
        }
        if dates.count > 4 { lines.append("และอีก \(dates.count - 4) ใบ") }
    }
    if let kind = item.limitResetKind {
        lines.append("ใบชนิด \(kind) — คืนเฉพาะโควตาของ \(kind) ไม่ได้รีเซ็ตทั้งสัปดาห์")
    }
    lines.append(use)
    return lines
}

/// นับถอยหลังสั้นสุดสำหรับช่องแคบ: 3ช · 4ว · 12น
func shortCountdown(_ date: Date?, now: Date) -> String {
    guard let date, date > now else { return "—" }
    let secs = Int(date.timeIntervalSince(now))
    if secs >= 86_400 { return "\(secs / 86_400)ว" }
    if secs >= 3_600 { return "\(secs / 3_600)ช" }
    return "\(max(1, secs / 60))น"
}

// MARK: - หน้าตาทั้งบาน

/// สไตล์ A — การ์ดใหญ่หนึ่งใบสำหรับตัวที่ใกล้ชนที่สุด + ช่องเล็ก 2 คอลัมน์ + ถังที่ไม่มี %
struct BentoView: View {
    let items: [UsageItem]
    @ObservedObject var prefs: Preferences
    let now: Date
    /// true = อยู่ในหน้าต่างใส การ์ดเป็นแผ่น Liquid Glass จริง · false = แผ่นจางบนพื้นบาน
    var glass = false
    @State private var selected: String?
    /// การ์ดไหนกางรายละเอียดใบรีเซ็ตอยู่ — ทีละใบพอ
    @State private var detailFor: String?
    @State private var appeared = false

    private var hero: UsageItem? { heroItem(items, selected: selected) }
    private var tiles: [UsageItem] {
        items.filter { headlinePct($0) != nil && $0.id != hero?.id }
    }
    private var others: [UsageItem] { items.filter { headlinePct($0) == nil } }

    var body: some View {
        VStack(spacing: 8) {
            if let hero {
                heroTile(hero)
                    .id(hero.id)
                    .transition(.asymmetric(insertion: .scale(scale: 0.96).combined(with: .opacity),
                                            removal: .opacity))
            }
            // Grid ไม่ใช่ LazyVGrid — lazy วัดความสูงไม่ครบ popover ที่สูงตามเนื้อหาจะเตี้ยเกิน
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)],
                      spacing: 8) {
                ForEach(Array(tiles.enumerated()), id: \.element.id) { index, item in
                    tile(item, index: index)
                        .opacity(appeared ? 1 : 0)
                        .offset(y: appeared ? 0 : 10)
                        .animation(.spring(response: 0.6, dampingFraction: 0.85)
                                    .delay(0.05 * Double(index)), value: appeared)
                }
                if !others.isEmpty { othersTile }
            }
        }
        .animation(.spring(response: 0.5, dampingFraction: 0.86), value: selected)
        .onAppear { appeared = false; DispatchQueue.main.async { appeared = true } }
        .onDisappear { appeared = false; selected = nil }
    }

    // MARK: การ์ดใหญ่

    @ViewBuilder private func heroTile(_ item: UsageItem) -> some View {
        let pct = headlinePct(item) ?? 0
        let sev = severity(pct)
        let window = headlineWindow(item)
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 0) {
                titleRow(item, logo: 16, font: 13)
                Spacer(minLength: 6)
                RollingNumber(value: pct, size: 50, estimated: window?.sure == .estimate)
                Spacer(minLength: 6)
                HStack(spacing: 6) {
                    if sev != .calm {
                        Image(systemName: "circle.fill")
                            .font(.system(size: 6))
                            .foregroundStyle(sev == .critical ? Color(red: 1, green: 0.37, blue: 0.34) : .orange)
                            .symbolEffect(.pulse, options: .repeating)
                    }
                    Text(heroStatus(item, pct: pct, window: window))
                        .font(.system(size: 11.5)).foregroundStyle(.secondary).lineLimit(1)
                }
                // การ์ดใหญ่มักเป็นตัวที่ชนอยู่ — ตอนนั้นแหละที่อยากรู้ว่ามีใบรีเซ็ตไหม
                if let note = resetNote(item) {
                    resetButton(item, note: note, size: 11).padding(.top, 3)
                }
                // หน้าต่างอื่นนอกจากตัวที่ขึ้นเกจใหญ่ — ไม่งั้นการ์ดใหญ่บอกแค่เลขเดียว
                let rest = displayableWindows(item).filter { $0.label != window?.label }
                if !rest.isEmpty {
                    VStack(spacing: 5) {
                        ForEach(Array(rest.enumerated()), id: \.element.label) { i, row in
                            MiniMeter(window: row, label: row.label, delay: 0.1 + 0.04 * Double(i), now: now)
                        }
                    }
                    .padding(.top, 6)
                }
            }
            Spacer(minLength: 0)
            ArcGauge(pct: pct, sev: sev, caption: windowName(window?.label))
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 136)
        .background { tileShape(radius: 22) }
        .help(limitResetsDetail(item, now: now) ?? "")
        .contextMenu { pinMenu(item) }
        if detailFor == item.id {
            resetDetail(item)
                .padding(.horizontal, 16).padding(.vertical, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background { tileShape(radius: 16) }
        }
    }

    private func heroStatus(_ item: UsageItem, pct: Double, window: WindowRow?) -> String {
        let back = window?.resetAt.map { countdownText(to: $0, from: now) }
        if pct >= 99.5 { return back.map { "เต็มแล้ว · กลับมาใน \($0)" } ?? "เต็มแล้ว" }
        return back.map { "รีเซ็ตใน \($0)" } ?? item.label
    }

    private func windowName(_ label: String?) -> String {
        switch label {
        case "5h": return "5 ชม."
        case "7d": return "7 วัน"
        case let other?: return other
        case nil: return ""
        }
    }

    // MARK: ช่องเล็ก

    @ViewBuilder private func tile(_ item: UsageItem, index: Int) -> some View {
        let rows = displayableWindows(item)
        VStack(alignment: .leading, spacing: 6) {
            titleRow(item, logo: 14, font: 12.5)
            RollingNumber(value: headlinePct(item) ?? 0, size: 26,
                          estimated: headlineWindow(item)?.sure == .estimate)
            // ทุกหน้าต่างที่มีเลขจริง — รวมเกจของโมเดล (Fable) และรายเดือน (1mo/30d)
            // เดิมโชว์แค่ 5h/7d ตายตัว เกจที่เหลือหายหมด (ผู้ใช้ทัก 2026-11-10)
            VStack(spacing: 5) {
                ForEach(Array(rows.enumerated()), id: \.element.label) { i, row in
                    MiniMeter(window: row, label: row.label,
                              delay: 0.08 + 0.05 * Double(index) + 0.04 * Double(i), now: now)
                }
            }
            if let note = resetNote(item) {
                resetButton(item, note: note, size: 10)
            } else if let note = rowFootnote(item, price: prefs.prices[item.id], now: now) {
                Text(note).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
            }
            if detailFor == item.id { resetDetail(item) }
        }
        .padding(.horizontal, 13).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background { tileShape(radius: 18) }
        .contentShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .onTapGesture { selected = item.id }
        .help(limitResetsDetail(item, now: now).map { $0 + "\n\n" } .map { $0 + "กดเพื่อขึ้นการ์ดใหญ่" }
              ?? "กดเพื่อขึ้นการ์ดใหญ่ · คลิกขวาเพื่อปักหมุด")
        .contextMenu { pinMenu(item) }
    }

    /// บรรทัดใบรีเซ็ตที่กดได้ — tooltip พึ่งไม่ได้ในหน้าต่างกระจก (ผู้ใช้ดูรายละเอียดไม่ได้
    /// 2026-11-10) รายละเอียดจึงกางออกในการ์ดเลย
    private func resetButton(_ item: UsageItem, note: String, size: CGFloat) -> some View {
        Button {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) {
                detailFor = detailFor == item.id ? nil : item.id
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "arrow.counterclockwise.circle")
                Text(note).lineLimit(1)
                Image(systemName: "chevron.right").font(.system(size: size - 3, weight: .bold))
                    .rotationEffect(.degrees(detailFor == item.id ? 90 : 0))
            }
            .font(.system(size: size)).foregroundStyle(.secondary)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func resetDetail(_ item: UsageItem) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            ForEach(resetDetailLines(item, now: now), id: \.self) { line in
                Text(line).font(.system(size: 10)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 2)
        .transition(.opacity)
    }

    /// ใบรีเซ็ตแบบสั้น + วันหมดอายุใบแรก · ได้คืนเมื่อไหร่ถ้าใช้ไปแล้ว
    private func resetNote(_ item: UsageItem) -> String? {
        if let resets = item.limitResets {
            if resets > 0 {
                let kind = item.limitResetKind.map { " \($0)" } ?? ""
                let head = item.limitResetsAtLeast ? "มีใบรีเซ็ต" : "ใบรีเซ็ต\(kind) \(resets) ใบ"
                if let first = item.limitResetsExpiring.first(where: { $0 > now }) {
                    return head + " · หมดใน " + countdownText(to: first, from: now)
                }
                return head
            }
            if let back = item.limitResetAvailableAt, back > now {
                return "ใช้ใบรีเซ็ตแล้ว · ได้คืนใน " + countdownText(to: back, from: now)
            }
            return "ไม่เหลือใบรีเซ็ต"
        }
        return item.group == "Claude Code" ? "ใบรีเซ็ต · ไม่ทราบ" : nil
    }

    private var othersTile: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("ถังอื่น").font(.system(size: 12.5, weight: .semibold))
            ForEach(others.prefix(4)) { item in
                HStack(spacing: 7) {
                    Circle().fill(Color.primary.opacity(0.35)).frame(width: 5, height: 5)
                    Text(item.label == item.group ? item.group : item.label)
                        .font(.system(size: 11.5)).lineLimit(1)
                    Spacer(minLength: 4)
                    Text(shortNote(item)).font(.system(size: 10)).foregroundStyle(.secondary).lineLimit(1)
                }
                .help(rowFootnote(item, price: prefs.prices[item.id], now: now) ?? item.group)
            }
            if others.count > 4 {
                Text("และอีก \(others.count - 4)").font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
        .background { tileShape(radius: 20) }
    }

    private func shortNote(_ item: UsageItem) -> String {
        if item.error != nil { return "พัง" }
        if item.local == true { return "ในเครื่อง" }
        if item.weekTokens > 0 { return compactTokens(item.weekTokens) }
        return "—"
    }

    // MARK: ส่วนร่วม

    @ViewBuilder private func titleRow(_ item: UsageItem, logo: CGFloat, font: CGFloat) -> some View {
        HStack(spacing: 6) {
            ProviderLogo(group: item.group, size: logo, tint: logoTint(item.group))
            Text(item.displayLabel).font(.system(size: font, weight: .semibold))
                .lineLimit(1).minimumScaleFactor(0.8)
            Spacer(minLength: 4)
            if let plan = item.plan {
                Text(plan).font(.system(size: 10, weight: .medium)).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .help(item.displayGroup)
    }

    @ViewBuilder private func tileShape(radius: CGFloat) -> some View {
        if glass {
            GlassPlate(radius: radius)
        } else {
            // ไม่มีเส้นขอบ — แผ่นจางๆ บนพื้นบานพอแยกช่องได้แล้ว
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(Color.primary.opacity(0.06))
        }
    }

    @ViewBuilder private func pinMenu(_ item: UsageItem) -> some View {
        Button(prefs.pinned.contains(item.id) ? "เอาออกจากแถบเมนู" : "ปักหมุดขึ้นแถบเมนู") {
            prefs.togglePin(item.id)
        }
        .disabled(!prefs.pinned.contains(item.id) && !prefs.canPin(item.id))
    }

    private func logoTint(_ group: String) -> Color {
        switch group {
        case "Claude Code": return Color(red: 0.91, green: 0.57, blue: 0.42)
        case "Muse": return Color(red: 0.60, green: 0.66, blue: 1.0)
        default: return .primary
        }
    }
}

/// 1.2M · 166M · 2.4B — ช่องแคบใส่ตัวเลขเต็มไม่ได้
func compactTokens(_ n: Int) -> String {
    let v = Double(n)
    if v >= 1e9 { return String(format: "%.1fB", v / 1e9) }
    if v >= 1e6 { return String(format: v >= 1e8 ? "%.0fM" : "%.1fM", v / 1e6) }
    if v >= 1e3 { return String(format: "%.0fK", v / 1e3) }
    return "\(n)"
}
