import AppKit
import SwiftUI

/// แผ่น Liquid Glass ของจริง — `glassEffect` ของ SwiftUI หักเหสิ่งที่อยู่หลังหน้าต่าง
///
/// ต้องอยู่ในหน้าต่างใส (GlassPanelController) ถึงจะเห็นวอลเปเปอร์ผ่านกระจก วางใน
/// NSPopover จะได้แค่กระจกซ้อนบนพื้น popover ที่ทึบอยู่แล้ว
///
/// **ห้ามใช้ NSGlassEffectView ผ่าน NSViewRepresentable เป็นพื้นการ์ด** (เคสจริง 2026-11-10):
/// แผ่น AppKit เป็นสิบแผ่น + หน้าต่างที่ปรับขนาดตามเนื้อหา ทำ Auto Layout ล้น stack
/// แอปพังทันทีที่เปิดดู ("Thread stack size exceeded" ใน NSISEngine)
struct GlassPlate: View {
    let radius: CGFloat

    var body: some View {
        if #available(macOS 26.0, *) {
            // ตัวการ์ดเป็นกระจกเหมือนเดิม — สิ่งที่ผู้ใช้ขอ (2026-11-11) คือ "เงา" ฟุ้งๆ แบบหน้าต่าง
            // macOS ไม่ใช่เบลอที่ตัวการ์ดและไม่ใช่กรอบ · เงาเจาะกลางออก (destinationOut)
            // ไม่งั้นก้อนดำใต้กระจกโปร่งจะทำให้ทั้งการ์ดมืด
            let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
            ZStack {
                ZStack {
                    shape.fill(.black).shadow(color: .black.opacity(0.20), radius: 10, y: 4)
                    shape.fill(.black).blendMode(.destinationOut)
                }
                .compositingGroup()
                Color.clear.glassEffect(.regular, in: .rect(cornerRadius: radius))
            }
        } else {
            RoundedRectangle(cornerRadius: radius, style: .continuous).fill(.ultraThinMaterial)
        }
    }
}

/// พื้นเบลอไร้ขอบแบบ Notification Center — เบลอสิ่งที่อยู่หลังหน้าต่างทั้งบริเวณ แล้วค่อยๆ
/// จางหายที่ขอบ ไม่มีกรอบ ไม่มีเส้น (ผู้ใช้ส่งภาพ Notification Center มาเป็นตัวอย่าง
/// 2026-11-11 หลังเดาผิดสามรอบ: พื้นบานมีกรอบ / เบลอที่ตัวการ์ด / เงาฟุ้ง)
///
/// แผ่นเดียวทั้งบาน — ขอบฟุ้งทำด้วย `maskImage` ที่มี alpha ไล่ระดับ ยืดได้ด้วย capInsets
struct FeatheredBlur: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .hudWindow
        view.blendingMode = .behindWindow
        view.state = .active
        view.maskImage = Self.mask
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {}

    private static let mask: NSImage = {
        let side: CGFloat = 120
        let image = NSImage(size: NSSize(width: side, height: side), flipped: false) { rect in
            // เงาของสี่เหลี่ยมมน = ขอบที่ alpha ไล่จากทึบไปใส
            let shadow = NSShadow()
            shadow.shadowBlurRadius = 12
            shadow.shadowColor = .black
            shadow.set()
            NSColor.black.setFill()
            NSBezierPath(roundedRect: rect.insetBy(dx: 14, dy: 14), xRadius: 26, yRadius: 26).fill()
            return true
        }
        image.capInsets = NSEdgeInsets(top: 50, left: 50, bottom: 50, right: 50)
        image.resizingMode = .stretch
        return image
    }()
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
    private weak var anchorWindow: NSWindow?
    private var anchorMidX: CGFloat = 0
    private var visible: NSRect?
    private var lastSize: CGSize?

    /// กึ่งกลางใต้ไอคอนแถบเมนู แต่ไม่ล้นขอบจอ
    private func originX(width: CGFloat) -> CGFloat {
        let x = anchorMidX - width / 2
        guard let visible else { return x }
        return min(max(x, visible.minX + 8), visible.maxX - width - 8)
    }

    var isShown: Bool { panel.isVisible }

    private let hosting: NSHostingView<AnyView>

    init<Content: View>(root: Content, onClose: @escaping () -> Void) {
        // ขนาดหน้าต่างเราคุมเอง — ปล่อยให้ hosting ปรับหน้าต่างตาม preferredContentSize
        // คือครึ่งหนึ่งของเหตุที่ layout วนจนพัง
        hosting = NSHostingView(rootView: AnyView(EmptyView()))
        hosting.sizingOptions = []
        self.onClose = onClose
        panel = KeyablePanel(contentRect: NSRect(x: 0, y: 0, width: 380, height: 400),
                             styleMask: [.borderless, .nonactivatingPanel],
                             backing: .buffered, defer: true)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .popUpMenu
        panel.collectionBehavior = [.transient, .ignoresCycle, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.contentView = hosting
        hosting.rootView = AnyView(
            VStack(spacing: 0) {
                root.fixedSize(horizontal: false, vertical: true)
                    .onGeometryChange(for: CGSize.self) { $0.size } action: { [weak self] size in
                        // async — ห้ามเปลี่ยนเฟรมหน้าต่างกลางรอบ layout ของ SwiftUI
                        DispatchQueue.main.async { self?.resize(to: size) }
                    }
                Spacer(minLength: 0)
            })
        panel.onCancel = { [weak self] in self?.close() }
    }

    /// เนื้อหาสูงเปลี่ยน (สลับหน้าตั้งค่า) — ตั้งเฟรมเองโดยตรึงขอบบนไว้ใต้แถบเมนู
    private func resize(to size: CGSize) {
        guard size.width > 1, size.height > 1 else { return }
        lastSize = size
        guard panel.isVisible else { return }
        // กว้างเปลี่ยน = จุดกึ่งกลางเลื่อน — คำนวณ x ใหม่ทุกครั้ง ไม่งั้นหน้าต่างขึ้นเยื้องจากไอคอน
        // (เคสจริง 2026-11-10: ขนาดตอนเปิดครั้งแรกยังไม่ใช่ขนาดจริง)
        topLeft.x = originX(width: size.width)
        let frame = NSRect(x: topLeft.x, y: topLeft.y - size.height, width: size.width, height: size.height)
        if abs(panel.frame.height - frame.height) > 0.5 || abs(panel.frame.width - frame.width) > 0.5
            || abs(panel.frame.minX - frame.minX) > 0.5 {
            panel.setFrame(frame, display: true)
        }
    }

    func show(below button: NSStatusBarButton) {
        guard let window = button.window else { return }
        anchorWindow = window
        let anchor = window.convertToScreen(button.convert(button.bounds, to: nil))
        anchorMidX = anchor.midX
        visible = (window.screen ?? NSScreen.main)?.visibleFrame
        // ขนาดจริงมาจาก onGeometryChange ทีหลัง — ตอนนี้ใช้ขนาดล่าสุดที่รู้ไปก่อน
        let size = lastSize ?? hosting.fittingSize
        topLeft = NSPoint(x: originX(width: size.width), y: anchor.minY - 2)
        panel.setFrame(NSRect(x: topLeft.x, y: topLeft.y - size.height,
                              width: size.width, height: size.height), display: false)
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
