import XCTest
@testable import AIUsage

final class SelfUpdateTests: XCTestCase {
    private var root: URL!

    override func setUp() {
        super.setUp()
        root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aiusage-selfupdate-\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: root)
        super.tearDown()
    }

    @discardableResult
    private func write(_ relative: String, modified: Date) -> URL {
        let url = root.appendingPathComponent(relative)
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        try? "x".write(to: url, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes([.modificationDate: modified],
                                               ofItemAtPath: url.path)
        return url
    }

    // MARK: - ข้อมูลที่ setup.sh ทิ้งไว้

    func testInstallInfoReadsWhatSetupWrote() throws {
        let path = root.appendingPathComponent("install.json")
        try #"{"repo":"/tmp/repo","installedAt":1787000000,"version":"c4f528c","build":47}"#
            .write(to: path, atomically: true, encoding: .utf8)
        let info = try XCTUnwrap(InstallInfo.load(from: path.path))
        XCTAssertEqual(info.repo, "/tmp/repo")
        XCTAssertEqual(info.version, "c4f528c")
        XCTAssertEqual(info.build, 47)
        XCTAssertEqual(info.installedAt, Date(timeIntervalSince1970: 1787000000))
    }

    /// ยังไม่เคยติดตั้งผ่าน setup.sh รุ่นใหม่ = ไม่รู้ว่าโค้ดอยู่ไหน ต้องไม่พัง
    func testMissingInstallFileIsNil() {
        XCTAssertNil(InstallInfo.load(from: root.appendingPathComponent("nope.json").path))
    }

    // MARK: - หาว่าโค้ดถูกแก้ล่าสุดเมื่อไหร่

    func testNewestSourceChangeLooksAtEveryPlaceCodeLives() {
        let old = Date(timeIntervalSince1970: 1_787_000_000)
        let new = old.addingTimeInterval(3600)
        write("App/AIUsageApp.swift", modified: old)
        write("Shared/Preferences.swift", modified: old)
        write("engine/aiusage/liveusage.py", modified: new)
        write("ai-usage.60s.py", modified: old)
        XCTAssertEqual(newestSourceChange(repo: root.path), new,
                       "แก้ที่ engine ก็คือโค้ดใหม่ ไม่ใช่แค่ฝั่ง Swift")
    }

    /// __pycache__ เปลี่ยนทุกครั้งที่รันเทสต์ — นับด้วยจะขึ้น "มีอัปเดต" ทั้งที่ไม่มีใครแก้อะไร
    func testGeneratedFilesDoNotCountAsChanges() {
        let old = Date(timeIntervalSince1970: 1_787_000_000)
        write("App/AIUsageApp.swift", modified: old)
        write("engine/__pycache__/liveusage.cpython-313.pyc",
              modified: old.addingTimeInterval(9999))
        write("engine/aiusage/.DS_Store", modified: old.addingTimeInterval(9999))
        XCTAssertEqual(newestSourceChange(repo: root.path), old)
    }

    func testMovedRepoHasNoSourceAtAll() {
        XCTAssertNil(newestSourceChange(repo: root.appendingPathComponent("gone").path))
    }

    // MARK: - สรุปสถานะให้เมนู

    private func info(installedAt: Date) -> InstallInfo {
        InstallInfo(repo: "/tmp/repo", installedAt: installedAt, version: "c4f528c", build: 47)
    }

    private let installed = Date(timeIntervalSince1970: 1_787_000_000)

    func testSourceOlderThanTheInstalledAppIsUpToDate() {
        let state = updateState(info(installedAt: installed),
                                sourceChangedAt: installed.addingTimeInterval(-60),
                                toolsPresent: true)
        XCTAssertEqual(state, .upToDate(version: "c4f528c", build: 47))
    }

    /// เคสจริงของ repo นี้: งานค้างยังไม่ commit แต่ไฟล์ใหม่กว่าตัวที่ติดตั้งแล้ว
    func testSourceNewerThanTheInstalledAppIsAnUpdate() {
        let changed = installed.addingTimeInterval(7200)
        XCTAssertEqual(updateState(info(installedAt: installed),
                                   sourceChangedAt: changed, toolsPresent: true),
                       .available(since: changed))
    }

    func testWithoutInstallInfoWeDoNotKnowWhereTheCodeIs() {
        guard case .unavailable = updateState(nil, sourceChangedAt: Date(), toolsPresent: true)
        else { return XCTFail("ไม่มี install.json ต้องบอกเหตุผล ไม่ใช่บอกว่าล่าสุดแล้ว") }
    }

    func testMovedRepoReportsWhyInsteadOfPretendingItIsCurrent() {
        guard case .unavailable = updateState(info(installedAt: installed),
                                              sourceChangedAt: nil, toolsPresent: true)
        else { return XCTFail("repo หายต้องบอกเหตุผล") }
    }

    /// ไม่มีเครื่องมือ build = กดแล้วจะเงียบ — ต้องบอกก่อนกด แต่บอกเฉพาะตอนมีของให้ติดตั้ง
    func testMissingBuildToolsOnlyMattersWhenThereIsAnUpdate() {
        guard case .unavailable = updateState(info(installedAt: installed),
                                              sourceChangedAt: installed.addingTimeInterval(60),
                                              toolsPresent: false)
        else { return XCTFail("มีอัปเดตแต่ build ไม่ได้ ต้องบอกเหตุผล") }

        XCTAssertEqual(updateState(info(installedAt: installed),
                                   sourceChangedAt: installed.addingTimeInterval(-60),
                                   toolsPresent: false),
                       .upToDate(version: "c4f528c", build: 47),
                       "ไม่มีอะไรให้ติดตั้ง ก็ไม่ต้องบ่นเรื่องเครื่องมือ")
    }

    func testBuildToolsNeedOneCandidateFromEachGroup() {
        let present = write("bin/xcodegen", modified: Date()).path
        try? FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: present)
        XCTAssertTrue(buildToolsPresent([[present, "/nope/xcodegen"]]))
        XCTAssertFalse(buildToolsPresent([[present], ["/nope/xcodebuild"]]))
    }

    // MARK: - ข้อความในเมนู

    func testMenuSaysWhatWillHappen() {
        let now = Date(timeIntervalSince1970: 1_787_010_000)
        XCTAssertEqual(updateMenuTitle(.upToDate(version: "c4f528c", build: 47), now: now),
                       "ล่าสุดแล้ว (c4f528c · 47)")
        XCTAssertEqual(updateMenuTitle(.available(since: now.addingTimeInterval(-7200)), now: now),
                       "ติดตั้งอัปเดต — โค้ดแก้เมื่อ 2h ที่แล้ว")
        XCTAssertEqual(updateMenuTitle(.unavailable("หา repo ไม่เจอ"), now: now),
                       "หา repo ไม่เจอ")
    }

    func testOnlyAnAvailableUpdateIsClickable() {
        XCTAssertTrue(UpdateState.available(since: Date()).isActionable)
        XCTAssertFalse(UpdateState.upToDate(version: "a", build: 1).isActionable)
        XCTAssertFalse(UpdateState.unavailable("x").isActionable)
    }

    // MARK: - แอปที่ Homebrew เป็นเจ้าของ

    /// คนที่ลงผ่าน `brew install --cask` ไม่มี repo ในเครื่อง เมนูเดิมจะบอกให้เขา
    /// "รัน ./setup.sh หนึ่งครั้ง" ซึ่งเป็นคำแนะนำที่ทำตามไม่ได้เลย
    func testHomebrewInstallIsDetectedFromItsCaskroomEntry() {
        let caskroom = root.appendingPathComponent("Caskroom/aiusage")
        try? FileManager.default.createDirectory(at: caskroom, withIntermediateDirectories: true)
        XCTAssertTrue(installedByHomebrew([caskroom.path]))
        XCTAssertFalse(installedByHomebrew([root.appendingPathComponent("Caskroom/nope").path]))
    }

    func testBrewOwnedAppNeverOffersToBuildFromSource() {
        let state = updateState(nil, sourceChangedAt: nil, toolsPresent: false, brewManaged: true)
        XCTAssertEqual(state, .managedByHomebrew)
        XCTAssertFalse(state.isActionable, "ปุ่มต้องกดไม่ได้ — brew เป็นคนอัปเดต ไม่ใช่เรา")
    }

    /// แม้จะมี repo อยู่ในเครื่องด้วย ถ้า brew เป็นเจ้าของแอปที่ติดตั้งไว้
    /// การ build ทับจะทำให้ brew กับของจริงไม่ตรงกัน
    func testBrewOwnershipWinsOverALocalCheckout() {
        let info = InstallInfo(repo: "/tmp/repo", installedAt: Date(timeIntervalSince1970: 1),
                               version: "abc", build: 1)
        let state = updateState(info, sourceChangedAt: Date(timeIntervalSince1970: 9_999),
                                toolsPresent: true, brewManaged: true)
        XCTAssertEqual(state, .managedByHomebrew)
    }

    func testTheMenuTellsBrewUsersTheExactCommand() {
        let title = updateMenuTitle(.managedByHomebrew, now: Date())
        XCTAssertTrue(title.contains("brew upgrade --cask"), "ต้องบอกคำสั่งที่ใช้ได้จริง")
    }

    func testSourceInstallsAreUntouchedByTheNewCase() {
        let info = InstallInfo(repo: "/tmp/repo", installedAt: Date(timeIntervalSince1970: 1),
                               version: "abc", build: 1)
        let state = updateState(info, sourceChangedAt: Date(timeIntervalSince1970: 9_999),
                                toolsPresent: true, brewManaged: false)
        XCTAssertTrue(state.isActionable)
    }

    // MARK: - แจ้งเตือนชวนอัปเดตอัตโนมัติ

    private let checkTime = Date(timeIntervalSince1970: 1_787_020_000)

    func testSettledUpdateNotifiesOnce() {
        let since = checkTime.addingTimeInterval(-20 * 60)
        XCTAssertEqual(updateNotifySince(state: .available(since: since), now: checkTime,
                                        lastNotifiedAt: nil),
                       since)
    }

    /// ไฟล์เพิ่งขยับ = กำลังแก้อยู่ — เตือนตอนนี้คือชวน build ของที่ยังไม่เสร็จ
    /// แล้วจะเตือนซ้ำทุกครั้งที่กดเซฟ
    func testFreshEditsDoNotNotify() {
        let since = checkTime.addingTimeInterval(-2 * 60)
        XCTAssertNil(updateNotifySince(state: .available(since: since), now: checkTime,
                                       lastNotifiedAt: nil),
                     "เพิ่งแก้เมื่อ 2 นาทีที่แล้ว ต้องรอให้นิ่งก่อน")
    }

    /// ตรวจทุก 60 วินาที — ไม่มีคูลดาวน์จะได้ใบเดิมซ้ำทุกนาทีจนต้องปิดแจ้งเตือนทิ้ง
    func testCooldownSuppressesRepeatNotification() {
        let since = checkTime.addingTimeInterval(-20 * 60)
        XCTAssertNil(updateNotifySince(state: .available(since: since), now: checkTime,
                                       lastNotifiedAt: checkTime.addingTimeInterval(-10 * 60)))
    }

    func testCooldownExpiryNotifiesAgain() {
        let since = checkTime.addingTimeInterval(-3 * 3600)
        XCTAssertEqual(updateNotifySince(state: .available(since: since), now: checkTime,
                                        lastNotifiedAt: checkTime.addingTimeInterval(-2 * 3600)),
                       since, "เตือนเมื่อ 2 ชม.ก่อน ครบชั่วโมงแล้วเตือนซ้ำได้")
    }

    func testNonAvailableStatesNeverNotify() {
        for state in [UpdateState.upToDate(version: "a", build: 1),
                      .unavailable("x"),
                      .managedByHomebrew] {
            XCTAssertNil(updateNotifySince(state: state, now: checkTime, lastNotifiedAt: nil),
                         "brew เป็นเจ้าของต้องไม่ถูกชวน build ทับเด็ดขาด")
        }
    }

    // MARK: - รายงานผลติดตั้งที่ล้มเหลว

    func testUpdateResultReadsWhatSetupWrote() throws {
        let path = root.appendingPathComponent("last-update.json")
        try #"{"at":1787020000,"ok":false}"#.write(to: path, atomically: true, encoding: .utf8)
        let result = try XCTUnwrap(UpdateResult.load(from: path.path))
        XCTAssertEqual(result.at, Date(timeIntervalSince1970: 1787020000))
        XCTAssertFalse(result.ok)
    }

    func testUnreportedFailureReportsOnce() {
        let failed = UpdateResult(at: checkTime, ok: false)
        XCTAssertEqual(unreportedFailure(failed, lastReportedAt: nil), failed)
        XCTAssertNil(unreportedFailure(failed, lastReportedAt: checkTime),
                     "รายงานแล้วต้องไม่ยิงซ้ำทุกรอบตรวจ")
    }

    func testSuccessAndMissingResultsStaySilent() {
        XCTAssertNil(unreportedFailure(UpdateResult(at: checkTime, ok: true),
                                      lastReportedAt: nil),
                     "ติดตั้งสำเร็จไม่ต้องมีใบแจ้ง")
        XCTAssertNil(unreportedFailure(nil, lastReportedAt: nil))
    }
}
