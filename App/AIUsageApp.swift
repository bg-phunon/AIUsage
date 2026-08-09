import SwiftUI
import AppKit

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

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.action = #selector(togglePopover)
        statusItem.button?.target = self
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 380, height: 560)
        popover.contentViewController = NSHostingController(rootView: PopoverView(model: model))

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
        let segments = menuBarSegments(snapshot: model.snapshot, now: Date(), wokeRecently: wokeRecently,
                                       visibleGroups: model.visibleGroups)
        guard let button = statusItem.button else { return }
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
    @Published var snapshot: UsageSnapshot = .load()
    @Published var engineError: String?
    @Published var wokeRecently = false
    @Published var settingsPresented = false
    @Published var visibleGroups: Set<String> = Set(UserDefaults.standard.stringArray(forKey: "visibleMenuBarProviders") ?? ["Claude Code", "Qwen Cloud", "GLM", "Codex"])
    @Published var designStyle: DesignStyle = DesignStyle(rawValue: UserDefaults.standard.string(forKey: "designStyle") ?? "darkGlass") ?? .darkGlass
}
