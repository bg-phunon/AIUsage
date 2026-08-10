import SwiftUI
import AppKit
import Combine

@main
struct AIUsageApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    var body: some Scene { Settings { EmptyView() } }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var timer: Timer?
    private var runner: EngineRunner?
    private var lastWake = Date.distantPast
    private let model = UsageModel()
    private var prefsObserver: AnyCancellable?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // ย้ายค่าที่เคยตั้งไว้ในกลไกเดิม (visibleMenuBarProviders) มาเป็น prefs.hidden
        // ครั้งเดียวตอนเปิดแอป — model.snapshot โหลดมาแล้วตั้งแต่ตอน UsageModel() ถูกสร้าง
        model.prefs.migrateVisibleGroups(.standard, allItems: model.snapshot.items)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.action = #selector(togglePopover)
        statusItem.button?.target = self
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        popover = NSPopover()
        popover.behavior = .transient
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
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in self?.refresh() }
    }

    @objc private func didWake() { lastWake = Date(); refresh() }
    @objc private func refreshRequested() { refresh() }
    @objc private func settingsChanged() { updateBar() }

    private var wokeRecently: Bool { Date().timeIntervalSince(lastWake) < wakeGrace }

    private func refresh() {
        runner?.run { [weak self] result in
            guard let self else { return }
            if case .failure(let error) = result, case .alreadyRunning = error { return }
            if case .failure(let error) = result {
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
        // เส้นทางเดียว — ปักหมุดแค่กรองว่าจะโชว์ตัวไหน ไม่เปลี่ยนวิธีวาด
        let segments = menuBarSegments(snapshot: snapshot, now: Date(),
                                       wokeRecently: wokeRecently,
                                       hidden: model.prefs.hidden,
                                       pinned: model.prefs.pinned)
        let alert = hasUnpinnedCritical(snapshot: snapshot, pinned: model.prefs.pinned)
        button.attributedTitle = segmentTitle(segments, alert: alert)
        let age = snapshot.generated == .distantPast
            ? nil : Date().timeIntervalSince(snapshot.generated)
        button.alphaValue = freshness(snapshotAge: age, wokeRecently: wokeRecently) == .fresh
            ? 1.0 : 0.55
        button.image = nil
    }

    private func segmentTitle(_ segments: [MenuBarSegment], alert: Bool) -> NSAttributedString {
        let title = NSMutableAttributedString()
        let font = NSFont.systemFont(ofSize: 11, weight: .medium)
        if alert {
            title.append(NSAttributedString(string: "• ", attributes: [
                .font: font, .foregroundColor: NSColor.systemRed]))
        }
        for (index, segment) in segments.enumerated() {
            if index > 0 {
                title.append(NSAttributedString(string: "   ", attributes: [.font: font]))
            }
            let imageURL = Bundle.main.url(forResource: segment.assetName, withExtension: "svg")
            if let image = imageURL.flatMap(NSImage.init(contentsOf:)) {
                image.size = NSSize(width: 13, height: 13)
                image.isTemplate = true
                let attachment = NSTextAttachment()
                attachment.image = image
                title.append(NSAttributedString(attachment: attachment))
                title.append(NSAttributedString(string: " ", attributes: [.font: font]))
            }
            title.append(NSAttributedString(string: segment.value,
                                             attributes: [.font: font, .foregroundColor: NSColor.labelColor]))
        }
        if segments.isEmpty {
            title.append(NSAttributedString(string: "AI  —", attributes: [.font: font, .foregroundColor: NSColor.secondaryLabelColor]))
        }
        return title
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
