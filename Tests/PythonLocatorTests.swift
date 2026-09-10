import XCTest
@testable import AIUsage

/// แอปที่เปิดจาก Finder มี PATH สั้นกว่าเทอร์มินัล `/usr/bin/env python3` จึงไม่พอ
///
/// ที่สำคัญกว่านั้น: `/usr/bin/python3` มีอยู่ทุกเครื่องแม้ยังไม่ได้ลง Command Line
/// Tools แต่ตัวที่มีเป็น stub ที่เด้ง dialog ชวนลง CLT ~1 GB แทนที่จะรัน — คนที่
/// `brew install --cask` มาแล้วเจอหน้าต่างนั้นคือคนที่เลิกใช้แอปตั้งแต่นาทีแรก
final class PythonLocatorTests: XCTestCase {
    private var root: URL!

    override func setUp() {
        super.setUp()
        root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aiusage-python-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: root)
        super.tearDown()
    }

    /// ไฟล์ที่รันได้จริง — isExecutableFile ดูบิต x ไม่ได้ดูว่าเป็น python
    @discardableResult
    private func executable(_ name: String) -> String {
        let url = root.appendingPathComponent(name)
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        try? "#!/bin/sh\n".write(to: url, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes([.posixPermissions: 0o755],
                                               ofItemAtPath: url.path)
        return url.path
    }

    private func missing(_ name: String) -> String {
        root.appendingPathComponent(name).path
    }

    func testPicksTheFirstCandidateThatExists() {
        let brew = executable("opt/homebrew/bin/python3")
        XCTAssertEqual(findPython(candidates: [brew, executable("usr/local/bin/python3")]), brew)
    }

    func testSkipsCandidatesThatAreNotThere() {
        let real = executable("usr/local/bin/python3")
        XCTAssertEqual(findPython(candidates: [missing("nope/python3"), real]), real)
    }

    func testSkipsFilesThatAreNotExecutable() {
        let url = root.appendingPathComponent("plain/python3")
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        try? "not runnable".write(to: url, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes([.posixPermissions: 0o644],
                                               ofItemAtPath: url.path)
        let real = executable("usr/local/bin/python3")
        XCTAssertEqual(findPython(candidates: [url.path, real]), real)
    }

    func testNothingFoundIsNilNotAGuess() {
        XCTAssertNil(findPython(candidates: [missing("a/python3"), missing("b/python3")]))
    }

    func testTheStubAtUsrBinIsNeverACandidate() {
        XCTAssertFalse(pythonSearchPath.contains("/usr/bin/python3"),
                       "/usr/bin/python3 เป็น stub ที่เด้ง dialog ลง CLT — ห้ามเรียกเด็ดขาด")
    }

    func testHomebrewComesBeforeDeveloperTools() {
        let brew = pythonSearchPath.firstIndex(of: "/opt/homebrew/bin/python3")
        let clt = pythonSearchPath.firstIndex(
            of: "/Library/Developer/CommandLineTools/usr/bin/python3")
        XCTAssertNotNil(brew)
        XCTAssertNotNil(clt)
        XCTAssertLessThan(brew!, clt!,
                          "cask ลง python ของ Homebrew ให้ ต้องหยิบตัวนั้นก่อน python 3.9 ของ CLT")
    }

    /// เครื่องที่ใช้ build อยู่ตอนนี้ต้องหาเจอ ไม่งั้นเทสต์อื่นก็เชื่อไม่ได้
    func testFindsSomethingOnThisMachine() {
        XCTAssertNotNil(findPython())
    }
}
