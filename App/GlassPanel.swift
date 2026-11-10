import AppKit
import SwiftUI

/// แผ่น Liquid Glass ของจริง — `NSGlassEffectView` หักเหสิ่งที่อยู่ *หลังหน้าต่าง*
///
/// ต้องอยู่ในหน้าต่างใส (GlassPanelController) ถึงจะเห็นวอลเปเปอร์ผ่านกระจก วางใน
/// NSPopover จะได้แค่กระจกซ้อนบนพื้น popover ที่ทึบอยู่แล้ว — ซึ่งคือสิ่งที่ผู้ใช้
/// บอกว่า "ไม่ใช่ของแท้" (2026-11-10)
struct GlassPlate: View {
    let radius: CGFloat

    var body: some View {
        if #available(macOS 26.0, *) {
            GlassPlateView(radius: radius)
        } else {
            RoundedRectangle(cornerRadius: radius, style: .continuous).fill(.ultraThinMaterial)
        }
    }
}

@available(macOS 26.0, *)
private struct GlassPlateView: NSViewRepresentable {
    let radius: CGFloat

    func makeNSView(context: Context) -> NSGlassEffectView {
        let view = NSGlassEffectView()
        view.style = .regular
        view.cornerRadius = radius
        return view
    }

    func updateNSView(_ view: NSGlassEffectView, context: Context) {
        view.cornerRadius = radius
    }
}

private final class KeyablePanel: NSPanel {
    var onCancel: (() -> Void)?
    // borderless ปกติรับคีย์ไม่ได้ — ช่องกรอกราคาในหน้าตั้งค่าต้องพิมพ์ได้
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { onCancel?() }
}

/// หน้าต่างใสไร้กรอบแทน NSPopover สำหรับสไตล์ Liquid Glass — แบบ Control Center:
/// ไม่มีพื้นบาน การ์ดแต่ละใบเป็นกระจกลอยเหนือเดสก์ท็อปตรงๆ
///
/// NSPopover มีพื้นของมันเองที่เอาออกไม่ได้ กระจกที่วางข้างในจึงไม่มีวันเห็นวอลเปเปอร์
final class GlassPanelController {
    private let panel: KeyablePanel
    private let onClose: () -> Void
    private var monitors: [Any] = []
    private var topLeft = NSPoint.zero
    private var resizeObserver: NSObjectProtocol?
    private weak var anchorWindow: NSWindow?

    var isShown: Bool { panel.isVisible }

    init(content: NSViewController, onClose: @escaping () -> Void) {
        self.onClose = onClose
        panel = KeyablePanel(contentRect: NSRect(x: 0, y: 0, width: 380, height: 400),
                             styleMask: [.borderless, .nonactivatingPanel],
                             backing: .buffered, defer: true)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false          // กระจกแต่ละแผ่นมีเงาของมันเอง
        panel.level = .popUpMenu
        panel.collectionBehavior = [.transient, .ignoresCycle, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.contentViewController = content
        panel.onCancel = { [weak self] in self?.close() }
        // เนื้อหาสูงเปลี่ยน (สลับหน้าตั้งค่า) หน้าต่างโตจากมุมล่างซ้าย — ตรึงขอบบนไว้ใต้แถบเมนู
        resizeObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.didResizeNotification, object: panel, queue: .main) { [weak self] _ in
                guard let self, self.panel.isVisible else { return }
                self.panel.setFrameTopLeftPoint(self.topLeft)
            }
    }

    deinit {
        if let resizeObserver { NotificationCenter.default.removeObserver(resizeObserver) }
    }

    func show(below button: NSStatusBarButton) {
        guard let window = button.window else { return }
        anchorWindow = window
        let anchor = window.convertToScreen(button.convert(button.bounds, to: nil))
        let size = panel.contentViewController?.view.fittingSize ?? panel.frame.size
        panel.setContentSize(size)
        var x = anchor.midX - size.width / 2
        if let visible = (window.screen ?? NSScreen.main)?.visibleFrame {
            x = min(max(x, visible.minX + 8), visible.maxX - size.width - 8)
        }
        topLeft = NSPoint(x: x, y: anchor.minY - 2)
        panel.setFrameTopLeftPoint(topLeft)
        panel.alphaValue = 0
        panel.makeKeyAndOrderFront(nil)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.14
            panel.animator().alphaValue = 1
        }
        installMonitors()
    }

    func close() {
        guard panel.isVisible else { return }
        monitors.forEach(NSEvent.removeMonitor)
        monitors = []
        panel.orderOut(nil)
        onClose()
    }

    /// คลิกนอกหน้าต่าง = ปิด แบบ popover .transient · คลิกที่ไอคอนแถบเมนูปล่อยให้ toggle จัดการ
    private func installMonitors() {
        let mask: NSEvent.EventTypeMask = [.leftMouseDown, .rightMouseDown]
        if let global = NSEvent.addGlobalMonitorForEvents(matching: mask, handler: { [weak self] _ in
            self?.close()
        }) { monitors.append(global) }
        if let local = NSEvent.addLocalMonitorForEvents(matching: mask, handler: { [weak self] event in
            if let self, event.window !== self.panel, event.window !== self.anchorWindow { self.close() }
            return event
        }) { monitors.append(local) }
    }
}
