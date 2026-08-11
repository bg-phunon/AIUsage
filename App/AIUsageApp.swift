import SwiftUI
import AppKit
import Combine

@main
struct AIUsageApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene { Settings { EmptyView() } }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSPopoverDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var menuBarHosting: ClickThroughHostingView<MenuBarContent>?
    private var timer: Timer?
    private var runner: EngineRunner?
    private var lastWake = Date.distantPast
    private let model = UsageModel()
    private var prefsObserver: AnyCancellable?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // ย้ายค่าที่เคยตั้งไว้ในกลไกเดิม (visibleMenuBarProviders) มาเป็น prefs.hidden
        // ครั้งเดียวตอนเปิดแอป — model.snapshot โหลดมาแล้วตั้งแต่ตอน UsageModel() ถูกสร้าง
        model.prefs.migrateVisibleGroups(.standard, allItems: model.snapshot.items)

        // เปิดเครื่องแล้วแอปต้องขึ้นเอง — ไม่มีใครจำได้ว่าต้องเปิด widget ทุกเช้า
        LaunchAtLogin.sync(wanted: model.prefs.launchAtLogin)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.action = #selector(togglePopover)
        statusItem.button?.target = self
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        popover = NSPopover()
        popover.behavior = .transient
        popover.delegate = self
        popover.contentSize = NSSize(width: 380, height: 560)
        popover.contentViewController = NSHostingController(
            rootView: PopoverView(model: model, prefs: model.prefs))

        if let script = EngineRunner.bundledScriptURL {
            runner = EngineRunner(scriptURL: script)
        } else {
            model.engineError = "ไม่พบ ai-usage.60s.py ใน bundle"
        }

        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(didWake),
                                                           name: NSWorkspace.didWakeNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(refreshRequested),
                                               name: .aiUsageRefreshRequested, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(settingsChanged),
                                               name: .aiUsageSettingsChanged, object: nil)
        // Preferences เป็น ObservableObject คนละตัวกับ UsageModel — เปลี่ยนหมุดแล้วจะไม่ทำให้
        // updateBar() ถูกเรียกเองจนกว่า timer 60 วิจะครบ ต้องสมัคร objectWillChange ตรงๆ
        // (มันยิง *ก่อน* ค่าเปลี่ยน จึงต้อง async ไปอ่านค่าหลังเปลี่ยนแล้ว)
        prefsObserver = model.prefs.objectWillChange.sink { [weak self] _ in
            DispatchQueue.main.async { self?.updateBar() }
        }
        refresh()
        // ห้ามใช้ scheduledTimer เฉยๆ — มันอยู่ใน mode .default ซึ่ง "หยุดยิง"
        // ระหว่างที่ popover กำลังโต้ตอบ (event tracking) ผลคือยิ่งผู้ใช้เปิดดูอยู่
        // ข้อมูลยิ่งไม่อัปเดต ต้องลงทะเบียนใน .common ให้ยิงได้ทุกสถานการณ์
        let refreshTimer = Timer(timeInterval: 60, repeats: true) { [weak self] _ in self?.refresh() }
        RunLoop.main.add(refreshTimer, forMode: .common)
        timer = refreshTimer
    }

    func popoverDidClose(_ notification: Notification) {
        updateBar()   // apply ความกว้างที่ค้างไว้ระหว่าง popover เปิด
    }

    @objc private func didWake() { lastWake = Date(); refresh() }
    @objc private func refreshRequested() { refresh() }
    @objc private func settingsChanged() { updateBar() }

    private var wokeRecently: Bool { Date().timeIntervalSince(lastWake) < wakeGrace }

    private func refresh() {
        runner?.run { [weak self] result in
            guard let self else { return }
            if case .failure(let error) = result {
                if case .alreadyRunning = error {
                    // มีรอบวิ่งอยู่แล้ว — ไม่ใช่ error และดิสก์อาจมีของใหม่กว่าที่จอถือ
                    self.model.snapshot = .load()
                    self.updateBar()
                    return
                }
                self.model.engineError = EngineRunner.describe(error)
            } else {
                self.model.engineError = nil
            }
            self.model.snapshot = .load()
            self.model.wokeRecently = self.wokeRecently
            self.updateBar()
        }
        updateBar()
    }

    private func updateBar() {
        guard let button = statusItem.button else { return }
        let snapshot = model.snapshot
        let segments = menuBarSegments(snapshot: snapshot, now: Date(),
                                       wokeRecently: wokeRecently,
                                       hidden: model.prefs.hidden,
                                       pinned: model.prefs.pinned)
        let alert = hasUnpinnedCritical(snapshot: snapshot, pinned: model.prefs.pinned)
        let age = snapshot.generated == .distantPast
            ? nil : Date().timeIntervalSince(snapshot.generated)
        let dimmed = freshness(snapshotAge: age, wokeRecently: wokeRecently) != .fresh

        let content = MenuBarContent(segments: segments, alert: alert, dimmed: dimmed,
                                     tagBelowLogo: model.prefs.tagBelowLogo)
        if let hosting = menuBarHosting {
            hosting.rootView = content
        } else {
            let hosting = ClickThroughHostingView(rootView: content)
            hosting.translatesAutoresizingMaskIntoConstraints = false
            button.addSubview(hosting)
            NSLayoutConstraint.activate([
                hosting.centerXAnchor.constraint(equalTo: button.centerXAnchor),
                hosting.centerYAnchor.constraint(equalTo: button.centerYAnchor),
            ])
            menuBarHosting = hosting
            button.attributedTitle = NSAttributedString()   // ห้ามมีข้อความซ้อนใต้ view
        }
        // status item ไม่รู้ขนาดของ subview เอง ต้องบอกความกว้างตรงๆ
        // แต่ห้ามขยับตอน popover เปิดอยู่ — ปุ่มขยับ = popover ที่เกาะอยู่กระโดดตาม
        // ความกว้างใหม่จะถูก apply ตอน popoverDidClose
        if popover?.isShown != true {
            statusItem.length = menuBarHosting?.fittingSize.width ?? NSStatusItem.variableLength
        }
    }


    @objc private func togglePopover() {
        guard let button = statusItem.button else { return }
        if NSApp.currentEvent?.type == .rightMouseUp {
            let menu = NSMenu()
            menu.addItem(withTitle: "เปิดรายละเอียด", action: #selector(openFromMenu), keyEquivalent: "")
            menu.addItem(.separator())
            menu.addItem(withTitle: "ตั้งค่า…", action: #selector(openSettings), keyEquivalent: ",")
            menu.addItem(withTitle: "ออกจาก AI Usage", action: #selector(terminate), keyEquivalent: "q")
            menu.items.forEach { $0.target = self }
            statusItem.menu = menu
            statusItem.button?.performClick(nil)
            statusItem.menu = nil
            return
        }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            model.snapshot = .load()
            refresh()   // เปิดดู = อยากเห็นของสด ยิงรอบใหม่เลย
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            // ห้ามบังคับหน้าต่างให้ใส — เคยตั้ง isOpaque=false + backgroundColor=.clear
            // ไว้ตรงนี้ ทำให้วอลเปเปอร์ทะลุขึ้นมาจนตัวเลขอ่านไม่ออก
            // ปล่อยให้ NSPopover จัดการพื้นหลังเอง แล้ว SwiftUI วาดทับ
            popover.contentViewController?.view.window?.makeKey()
        }
    }

    @objc private func openFromMenu() { togglePopover() }

    /// เดิมเปิด ~/.config/ai-usage/config.json ใน TextEdit ซึ่งเป็นของยุคก่อนมีหน้าตั้งค่า
    /// ผู้ใช้กด "ตั้งค่า…" สองที่แล้วได้คนละอย่างสิ้นเชิง
    @objc private func openSettings() {
        model.showSettings = true
        if !popover.isShown { togglePopover() }
    }

    @objc private func terminate() { NSApplication.shared.terminate(nil) }
}


/// เนื้อหาบนแถบเมนู — วาดด้วย SwiftUI แทน NSAttributedString
///
/// เหตุผลที่ต้องเลิกใช้ attributed string: NSTextAttachment ไม่สน isTemplate
/// โลโก้จึงถูกวาดเป็นสีดำดิบๆ จมหายไปกับวอลเปเปอร์ ในขณะที่ .renderingMode(.template)
/// ของ SwiftUI ปรับสีตามธีมแถบเมนูให้ถูกต้อง
struct MenuBarContent: View {
    let segments: [MenuBarSegment]
    let alert: Bool
    let dimmed: Bool
    var tagBelowLogo: Bool = true

    var body: some View {
        HStack(spacing: 10) {
            if alert {
                Circle().fill(Color.red).frame(width: 4, height: 4)
            }
            if segments.isEmpty {
                Text("AI —").font(.system(size: 11, weight: .medium)).opacity(0.5)
            }
            ForEach(segments, id: \.id) { segment in
                // ขีดคู่ = บัญชีมีอยู่แต่ยังไม่มีเลข — จางกว่าตัวที่มีเลขจริงให้อ่านผ่านตาได้
                HStack(spacing: 3) {
                    // ป้ายบัญชีใต้โลโก้ (ค่าเริ่มต้น) ประหยัดที่แนวนอน — สลับได้ในตั้งค่า
                    VStack(spacing: 0) {
                        if let image = Self.logo(segment.assetName) {
                            Image(nsImage: image)
                                .renderingMode(.template)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: tagBelowLogo && segment.tag != nil ? 11 : 12.5,
                                       height: tagBelowLogo && segment.tag != nil ? 11 : 12.5)
                        }
                        if tagBelowLogo, let tag = segment.tag {
                            Text(tag).font(.system(size: 6.5, weight: .semibold))
                                .opacity(0.55)
                        }
                    }
                    if !tagBelowLogo, let tag = segment.tag {
                        // บัญชีไหนของใคร — โผล่เฉพาะตอน provider เดียวกันมีหลายบัญชี
                        Text(tag).font(.system(size: 7.5, weight: .semibold))
                            .opacity(0.55)
                    }
                    if let bottom = segment.bottom {
                        // สองหน้าต่างซ้อนกันแบบ OpenUsage — 5 ชม. บน 7 วันล่าง
                        VStack(alignment: .leading, spacing: -0.5) {
                            Text(segment.top)
                            Text(bottom)
                        }
                        .font(.system(size: 8, weight: .semibold))
                        .monospacedDigit()
                    } else {
                        Text(segment.top)
                            .font(.system(size: 11, weight: .medium))
                            .monospacedDigit()
                    }
                }
                .opacity(segment.value == "–/–" ? 0.55 : 1)
            }
        }
        .padding(.horizontal, 6)
        .opacity(dimmed ? 0.55 : 1)
        .foregroundStyle(.primary)
    }

    private static var logoCache: [String: NSImage] = [:]
    static func logo(_ name: String) -> NSImage? {
        if let cached = logoCache[name] { return cached }
        guard let url = Bundle.main.url(forResource: name, withExtension: "svg"),
              let image = NSImage(contentsOf: url) else { return nil }
        image.isTemplate = true
        logoCache[name] = image
        return image
    }
}

/// hosting view ที่ปล่อยคลิกทะลุลงไปหาปุ่มของ status item
/// ไม่งั้น SwiftUI จะกินคลิกเองแล้ว popover ไม่เปิด
final class ClickThroughHostingView<Content: View>: NSHostingView<Content> {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

final class UsageModel: ObservableObject {
    // Preferences เป็น ObservableObject แยกต่างหาก จงใจไม่ทำเครื่องหมาย @Published ตรงนี้ —
    // view ที่ต้องวาดใหม่ตามหมุด ต้อง @ObservedObject var prefs: Preferences เอง (ดู PopoverView)
    // และ AppDelegate ต้องสมัคร prefs.objectWillChange เองสำหรับแถบเมนู
    let prefs = Preferences()
    @Published var snapshot: UsageSnapshot = .load()
    @Published var engineError: String?
    @Published var wokeRecently = false
    // หน้าตั้งค่ามีบานเดียว — แสดง/ซ่อนถังใช้ prefs.hidden ทั้งแถบเมนูและ popover
    @Published var showSettings = false
    @Published var designStyle: DesignStyle = DesignStyle(rawValue: UserDefaults.standard.string(forKey: "designStyle") ?? "darkGlass") ?? .darkGlass
}
