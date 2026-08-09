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
        let pinned = model.prefs.pinned

        // ปักหมุดไว้ = ผู้ใช้เลือกเองว่าจะเห็นถังไหน แทนที่ตัวเลือกอัตโนมัติทั้งหมด
        if !pinned.isEmpty {
            let units = menuBarUnits(snapshot: snapshot, pinned: pinned)
            let alert = hasUnpinnedCritical(snapshot: snapshot, pinned: pinned)
            let snapshotAge = snapshot.generated == .distantPast
                ? nil : Date().timeIntervalSince(snapshot.generated)
            let state = freshness(snapshotAge: snapshotAge, wokeRecently: wokeRecently)

            if units.count <= 1 {
                let text = menuBarText(snapshot: snapshot, now: Date(), wokeRecently: wokeRecently)
                button.attributedTitle = stackedTitle(text.top, text.bottom, alert: alert)
                button.alphaValue = text.dimmed ? 0.55 : 1.0
            } else {
                let line = units.map(compactLine).joined(separator: "  ")
                button.attributedTitle = singleTitle((alert ? "• " : "") + line)
                button.alphaValue = state == .fresh ? 1.0 : 0.55
            }
            button.image = nil
            return
        }

        // ไม่ปักเลย = อัตโนมัติ — โชว์ทุก provider ที่เลือกไว้ ทีละถังแยกไอคอน (ของเดิม)
        let segments = menuBarSegments(snapshot: snapshot, now: Date(), wokeRecently: wokeRecently,
                                       visibleGroups: model.visibleGroups)
        let title = NSMutableAttributedString()
        let font = NSFont.systemFont(ofSize: 11, weight: .medium)
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
        button.attributedTitle = title
        button.image = nil
        button.alphaValue = 1.0
    }

    private func stackedTitle(_ top: String, _ bottom: String,
                              alert: Bool) -> NSAttributedString {
        let para = NSMutableParagraphStyle()
        para.alignment = .right
        para.maximumLineHeight = 10
        return NSAttributedString(
            string: (alert ? "• " : "") + top + "\n" + bottom,
            attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .medium),
                         .paragraphStyle: para,
                         .foregroundColor: NSColor.labelColor])
    }

    private func singleTitle(_ line: String) -> NSAttributedString {
        NSAttributedString(
            string: line,
            attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium),
                         .foregroundColor: NSColor.labelColor])
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
            if let window = popover.contentViewController?.view.window {
                window.isOpaque = false
                window.backgroundColor = .clear
                window.contentView?.wantsLayer = true
                window.contentView?.layer?.backgroundColor = NSColor.clear.cgColor
                window.hasShadow = true
                window.invalidateShadow()
                window.makeKey()
            }
        }
    }

    @objc private func openFromMenu() { togglePopover() }

    @objc private func openSettings() {
        let url = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent(".config/ai-usage/config.json")
        if !FileManager.default.fileExists(atPath: url.path) {
            try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? Data("{}\n".utf8).write(to: url)
        }
        NSWorkspace.shared.open(url)
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
    @Published var settingsPresented = false
    // แยกจาก settingsPresented เพราะเปิดหน้าคนละหน้า — settingsPresented เปิด
    // ProviderSettingsView (รูปแบบหน้าตา + provider บนแถบเมนู) ส่วนตัวนี้เปิด
    // SettingsView (แสดง/ซ่อนถัง + ใส่ราคาเอง)
    @Published var showSettings = false
    @Published var visibleGroups: Set<String> = Set(UserDefaults.standard.stringArray(forKey: "visibleMenuBarProviders") ?? ["Claude Code", "Qwen Cloud", "GLM", "Codex"])
    @Published var designStyle: DesignStyle = DesignStyle(rawValue: UserDefaults.standard.string(forKey: "designStyle") ?? "darkGlass") ?? .darkGlass
}
