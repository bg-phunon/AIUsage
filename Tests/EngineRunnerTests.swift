import XCTest
@testable import AIUsage

/// เครื่องที่ไม่มี python3 ต้องบอกให้รู้ว่าต้องทำอะไร ไม่ใช่เงียบหรือขึ้นรหัสข้อผิดพลาด
///
/// เคสจริงที่รออยู่ข้างหน้า: คนที่ `brew install --cask` มาแล้ว Homebrew ยังไม่ได้
/// ลง python ให้ (หรือถอนไปทีหลัง) ถ้าแอปตายเงียบเขาไม่มีทางเดาถูกว่าเพราะอะไร
final class EngineRunnerTests: XCTestCase {
    private let script = URL(fileURLWithPath: "/tmp/aiusage-does-not-exist.py")

    func testNoPythonOnTheMachineIsItsOwnFailure() {
        let runner = EngineRunner(scriptURL: script, python: { nil })
        let done = expectation(description: "engine ตอบกลับ")
        var failure: EngineError?
        runner.run { result in
            if case .failure(let error) = result { failure = error }
            done.fulfill()
        }
        wait(for: [done], timeout: 5)
        guard case .pythonMissing = failure else {
            return XCTFail("ควรได้ .pythonMissing แต่ได้ \(String(describing: failure))")
        }
    }

    func testTheMessageTellsYouHowToFixIt() {
        let text = EngineRunner.describe(.pythonMissing)
        XCTAssertTrue(text.contains("python"),
                      "ข้อความต้องบอกว่าขาด python ไม่ใช่แค่ว่า engine พัง")
        XCTAssertTrue(text.contains("brew install python"),
                      "บอกคำสั่งที่แก้ได้เลย — คนที่ลงผ่าน cask มี brew อยู่แล้วแน่ๆ")
    }

    /// ไม่ได้ถาม findPython ตอนสร้าง แต่ถามตอนรันทุกครั้ง — คนที่เพิ่ง brew install
    /// python เสร็จต้องใช้ได้เลย ไม่ต้องปิดเปิดแอป
    func testPythonIsResolvedOnEveryRunNotOnceAtStartup() {
        var asked = 0
        let runner = EngineRunner(scriptURL: script, python: { asked += 1; return nil })
        for _ in 0..<2 {
            let done = expectation(description: "รอบหนึ่ง")
            runner.run { _ in done.fulfill() }
            wait(for: [done], timeout: 5)
        }
        XCTAssertEqual(asked, 2)
    }

    func testRealMachineStillFindsAnInterpreter() {
        XCTAssertNotNil(EngineRunner(scriptURL: script).resolvedPython())
    }

    // MARK: - ส่งสวิตช์ความยินยอมไปทาง argv

    /// แอปไม่เขียน config.json เพราะเอนจินก็เขียนไฟล์นั้นเองตอนเจอบัญชีใหม่
    /// สองฝั่งเขียนพร้อมกันแล้วฝั่งหนึ่งจะหาย — กับสวิตช์นี้แปลว่าแตะ Keychain เอง
    func testNoOpinionSendsNoFlagSoTheConfigFileDecides() {
        let args = EngineRunner.arguments(script: "/tmp/x.py", liveUsage: nil)
        XCTAssertEqual(args, ["/tmp/x.py", "--snapshot"])
    }

    func testOptingInIsPassedExplicitly() {
        XCTAssertEqual(EngineRunner.arguments(script: "/tmp/x.py", liveUsage: true),
                       ["/tmp/x.py", "--snapshot", "--live-usage=1"])
    }

    func testOptingOutIsPassedExplicitlyToo() {
        XCTAssertEqual(EngineRunner.arguments(script: "/tmp/x.py", liveUsage: false),
                       ["/tmp/x.py", "--snapshot", "--live-usage=0"],
                       "ปิดต้องส่งไปด้วย ไม่ใช่เงียบแล้วปล่อยให้ config เก่าชนะ")
    }

    // MARK: - ห้าม python เขียนอะไรลง bundle

    /// python เขียน __pycache__ ไว้ข้างโมดูลที่ import โดยอัตโนมัติ ซึ่งแปลว่าแอป
    /// แก้ไฟล์ข้างในตัวเองทุกครั้งที่รัน — ลายเซ็นของ bundle เสียและใน /Applications
    /// ก็ไม่ใช่ที่ที่ควรมีของชั่วคราว ย้ายไป Caches แทนการปิด cache ทิ้ง
    /// (ปิดไปเลยแปลว่าคอมไพล์ใหม่ทุก 60 วินาทีตลอดอายุการใช้งาน)
    func testBytecodeCacheIsRedirectedOutOfTheAppBundle() {
        let prefix = EngineRunner.environment()["PYTHONPYCACHEPREFIX"]
        XCTAssertNotNil(prefix)
        XCTAssertTrue(prefix!.contains("Caches"), "ต้องอยู่ใน Caches ไม่ใช่ใน .app")
        XCTAssertFalse(prefix!.contains(".app/"), "ห้ามชี้กลับเข้า bundle")
    }

    func testTheRestOfTheEnvironmentIsInherited() {
        XCTAssertEqual(EngineRunner.environment()["HOME"], ProcessInfo.processInfo.environment["HOME"],
                       "เอนจินอ่าน ~/.claude ผ่าน HOME — ตัดทิ้งแล้วมันหาบัญชีไม่เจอ")
    }
}
