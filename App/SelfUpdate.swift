import Foundation

/// อัปเดตตัวเองจากโค้ดในเครื่อง — repo นี้ไม่มี remote โค้ดใหม่จึงมาจากที่เดียว
/// คือโฟลเดอร์ที่ใช้ build ครั้งล่าสุด
///
/// แอปใน /Applications ไม่รู้จักโฟลเดอร์นั้นด้วยตัวเอง `setup.sh` จึงทิ้งที่อยู่ไว้ใน
/// `~/.config/ai-usage/install.json` ตอนติดตั้ง
///
/// "มีอัปเดต" วัดจาก mtime ของไฟล์ ไม่ใช่ commit เพราะงานในโปรเจกต์นี้ค้างไม่ commit
/// อยู่หลายวันเป็นเรื่องปกติ — เทียบ commit อย่างเดียวจะบอกว่า "ล่าสุดแล้ว" ในเคสที่
/// พบบ่อยที่สุด ข้อแลกคือแตะไฟล์เฉยๆ ก็นับเป็นใหม่ได้ ซึ่งราคาถูกเพราะการติดตั้ง
/// เป็นการกดเองเสมอ ไม่มีอะไรเกิดขึ้นเองจากการนับผิด
struct InstallInfo: Codable, Equatable {
    let repo: String
    let installedAt: Date
    let version: String
    let build: Int

    static let path = NSString(string: "~/.config/ai-usage/install.json").expandingTildeInPath

    static func load(from path: String = InstallInfo.path) -> InstallInfo? {
        guard let data = FileManager.default.contents(atPath: path) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .secondsSince1970
        return try? decoder.decode(InstallInfo.self, from: data)
    }
}

enum UpdateState: Equatable {
    case upToDate(version: String, build: Int)
    case available(since: Date)
    /// Homebrew เป็นเจ้าของแอปนี้ — build ทับเองจะทำให้ brew กับของจริงไม่ตรงกัน
    case managedByHomebrew
    /// เหตุผลที่แสดงต่อผู้ใช้ได้เลย — ทางที่ทำอะไรไม่ได้ต้องบอกว่าทำไม ไม่ใช่เงียบ
    case unavailable(String)

    var isActionable: Bool { if case .available = self { return true } else { return false } }
}

/// ร่องรอยที่ Homebrew ทิ้งไว้ตอนลง cask — โฟลเดอร์นี้อยู่ต่อแม้ตัว .app จะถูกย้าย
/// ไป /Applications แล้ว จึงเป็นสัญญาณที่เชื่อได้กว่าการเดาจากที่อยู่ของ bundle
let caskroomPaths = ["/opt/homebrew/Caskroom/aiusage", "/usr/local/Caskroom/aiusage"]

func installedByHomebrew(_ paths: [String] = caskroomPaths, fm: FileManager = .default) -> Bool {
    paths.contains { fm.fileExists(atPath: $0) }
}

/// ที่ที่โค้ดของแอปอยู่จริง — Tests/ ไม่อยู่ในนี้เพราะแก้เทสต์ไม่ได้เปลี่ยนตัวแอป
private let sourceRoots = ["App", "Shared", "engine", "ai-usage.60s.py",
                           "project.yml", "setup.sh"]

/// ไฟล์ที่ระบบสร้างเอง — mtime ขยับทุกครั้งที่รันเทสต์หรือเปิดโฟลเดอร์ใน Finder
private func isGenerated(_ name: String) -> Bool {
    name.hasPrefix(".") || name == "__pycache__" || name.hasSuffix(".pyc")
}

/// เวลาที่โค้ดถูกแก้ล่าสุด — nil แปลว่าหาโฟลเดอร์โค้ดไม่เจอเลย
func newestSourceChange(repo: String, fm: FileManager = .default) -> Date? {
    var newest: Date?
    func consider(_ path: String) {
        guard let modified = (try? fm.attributesOfItem(atPath: path))?[.modificationDate] as? Date
        else { return }
        if newest == nil || modified > newest! { newest = modified }
    }
    for relative in sourceRoots {
        let path = (repo as NSString).appendingPathComponent(relative)
        var isDirectory: ObjCBool = false
        guard fm.fileExists(atPath: path, isDirectory: &isDirectory) else { continue }
        guard isDirectory.boolValue else { consider(path); continue }
        guard let walker = fm.enumerator(atPath: path) else { continue }
        for case let entry as String in walker {
            let name = (entry as NSString).lastPathComponent
            if isGenerated(name) {
                if name == "__pycache__" { walker.skipDescendants() }
                continue
            }
            // เฉพาะไฟล์จริง — mtime ของโฟลเดอร์ขยับทุกครั้งที่มีไฟล์เพิ่ม/ลบข้างใน
            // รวมทั้งตอน build เขียนของชั่วคราว จะกลายเป็น "มีอัปเดต" ตลอดเวลา
            guard let attributes = walker.fileAttributes,
                  attributes[.type] as? FileAttributeType == .typeRegular,
                  let modified = attributes[.modificationDate] as? Date else { continue }
            if newest == nil || modified > newest! { newest = modified }
        }
    }
    return newest
}

/// เครื่องมือที่ `setup.sh` ต้องใช้ — แอปที่เปิดจาก Finder มี PATH สั้นกว่าเทอร์มินัล
/// จึงหาจากที่อยู่จริงแทนการพึ่ง `command -v`
let buildToolCandidates = [["/opt/homebrew/bin/xcodegen", "/usr/local/bin/xcodegen"],
                           ["/usr/bin/xcodebuild"]]

func buildToolsPresent(_ groups: [[String]] = buildToolCandidates,
                       fm: FileManager = .default) -> Bool {
    groups.allSatisfy { group in group.contains { fm.isExecutableFile(atPath: $0) } }
}

func updateState(_ info: InstallInfo?, sourceChangedAt: Date?,
                 toolsPresent: Bool, brewManaged: Bool = false) -> UpdateState {
    // ถามก่อนทุกข้อ — เครื่องนักพัฒนามี repo อยู่ด้วยได้ แต่ถ้าตัวที่ติดตั้งมาจาก
    // brew การ build ทับจะทำให้ `brew list --versions` โกหกทันที
    if brewManaged { return .managedByHomebrew }
    guard let info else {
        return .unavailable("ยังไม่รู้ว่าโค้ดอยู่ไหน — รัน ./setup.sh หนึ่งครั้ง")
    }
    guard let sourceChangedAt else {
        return .unavailable("หาโฟลเดอร์โค้ดไม่เจอ — ถูกย้ายหรือลบ?")
    }
    guard sourceChangedAt > info.installedAt else {
        return .upToDate(version: info.version, build: info.build)
    }
    // บ่นเรื่องเครื่องมือเฉพาะตอนมีของให้ติดตั้งจริง ไม่งั้นเป็น noise เปล่าๆ
    guard toolsPresent else {
        return .unavailable("มีโค้ดใหม่ แต่ต้องมี xcodegen และ Xcode ก่อน")
    }
    return .available(since: sourceChangedAt)
}

/// สถานะปัจจุบัน อ่านสดทุกครั้งที่ถาม — ไม่กี่สิบไฟล์ ไม่ต้องมี timer มาคอยสแกน
func currentUpdateState() -> UpdateState {
    let info = InstallInfo.load()
    return updateState(info,
                       sourceChangedAt: info.flatMap { newestSourceChange(repo: $0.repo) },
                       toolsPresent: buildToolsPresent(),
                       brewManaged: installedByHomebrew())
}

func updateMenuTitle(_ state: UpdateState, now: Date) -> String {
    switch state {
    case let .upToDate(version, build):
        return "ล่าสุดแล้ว (\(version) · \(build))"
    case let .available(since):
        return "ติดตั้งอัปเดต — โค้ดแก้เมื่อ \(ageText(now.timeIntervalSince(since))) ที่แล้ว"
    case .managedByHomebrew:
        return "อัปเดตด้วย brew upgrade --cask aiusage"
    case let .unavailable(reason):
        return reason
    }
}

/// สั่ง setup.sh แล้วปล่อยมือ
///
/// ต้อง detach จริงๆ เพราะกลางทาง setup.sh จะสั่งปิดแอปนี้ ถ้าสคริปต์ยังเป็นลูกที่
/// ผูกกับเรามันจะตายไปพร้อมกัน แล้วเครื่องจะเหลือ /Applications ที่เพิ่งถูกลบทิ้ง
/// (nohup + & ทำให้ launchd รับไปเลี้ยงต่อ) · PATH ต้องเติมเอง เพราะแอปที่เปิดจาก
/// Finder ไม่มี /opt/homebrew/bin
@discardableResult
func installUpdate(repo: String, fm: FileManager = .default) -> Bool {
    let script = (repo as NSString).appendingPathComponent("setup.sh")
    guard fm.isExecutableFile(atPath: script) else { return false }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/bin/sh")
    process.arguments = [
        "-c",
        "PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; "
            + "nohup \"$0\" > /tmp/aiusage-update.log 2>&1 &",
        script,
    ]
    do {
        try process.run()
        return true
    } catch {
        return false
    }
}
