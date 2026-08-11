import ServiceManagement

/// เปิดแอปเองตอนเข้าระบบ — SMAppService ไม่ต้องมี helper app และถอนได้สะอาด
///
/// ต้องมีลายเซ็นอย่างน้อย ad-hoc (setup.sh เซ็นให้ตอนติดตั้ง) ไม่งั้น register โยน error
/// ซึ่งเรากลืนเป็น false เฉยๆ — ผู้ใช้ยังเพิ่มเองใน System Settings ได้เสมอ
enum LaunchAtLogin {
    static var isEnabled: Bool { SMAppService.mainApp.status == .enabled }

    @discardableResult
    static func set(_ enabled: Bool) -> Bool {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            return true
        } catch {
            return false
        }
    }

    /// ทำสถานะจริงให้ตรงกับที่ผู้ใช้เลือกไว้ — เรียกตอนแอปเปิด
    /// (เช่นเพิ่งติดตั้งใหม่ status ยังไม่ enabled ทั้งที่ผู้ใช้อยากได้)
    static func sync(wanted: Bool) {
        guard wanted != isEnabled else { return }
        set(wanted)
    }
}
