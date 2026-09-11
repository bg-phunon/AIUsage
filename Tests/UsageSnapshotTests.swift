import XCTest
@testable import AIUsage

final class UsageSnapshotTests: XCTestCase {
    let json = """
    {"generated":"2026-08-07T06:40:00Z","items":[
      {"group":"Claude Code","label":"default","window":"5 ชม.","pct":5.0,"pctSource":"official","confidence":"valid","dataFetchedAt":"2026-08-07T06:38:06Z","severity":"critical","activeLimit":"Fable","error":null,"local":false,"tokens":123456,"cost":1.5,"calls":20,"resetAt":"2026-08-07T07:10:00Z","weekTokens":999,"weekCost":9.9,"weekPct":96.0,"profile":null,"plan":"Max 20x"},
      {"group":"Claude Code","label":"work","window":"5 ชม.","pct":null,"pctSource":null,"confidence":null,"dataFetchedAt":null,"severity":null,"activeLimit":null,"error":"OSError: permission denied","local":false,"tokens":0,"cost":0,"calls":0,"resetAt":null,"weekTokens":0,"weekCost":0,"weekPct":null,"profile":null,"plan":null}
    ]}
    """.data(using: .utf8)!

    func testDecodesContract() throws {
        let snapshot = try XCTUnwrap(UsageSnapshot.decode(from: json))
        XCTAssertEqual(snapshot.items.count, 2)
        XCTAssertTrue(snapshot.items[0].isOfficial)
        XCTAssertEqual(snapshot.items[0].activeLimit, "Fable")
        XCTAssertEqual(snapshot.items[1].error, "OSError: permission denied")
        XCTAssertNil(snapshot.items[1].pct)
    }

    func testDataAgeUsesFetchTime() throws {
        let snapshot = try XCTUnwrap(UsageSnapshot.decode(from: json))
        let now = ISO8601DateFormatter().date(from: "2026-08-07T06:48:06Z")!
        XCTAssertEqual(snapshot.items[0].dataAge(now: now) ?? 0, 600, accuracy: 1)
        XCTAssertNil(snapshot.items[1].dataAge(now: Date()))
    }

    func testGarbageReturnsNil() {
        XCTAssertNil(UsageSnapshot.decode(from: Data("not json".utf8)))
    }

    /// เอนจินคืน cost: null สำหรับถังที่ไม่รู้ราคา (GLM, Qwen Cloud, Codex)
    /// ถ้า Swift ประกาศเป็น Double แบบไม่ optional decode จะล้ม "ทั้งไฟล์"
    /// แล้วแอปขึ้น .empty คือไม่มีข้อมูลสักแถว — เคยพังมาแล้ว อย่าให้กลับมา
    func testNullCostDoesNotBreakTheWholeSnapshot() throws {
        let json = """
        {"generated":"2026-08-09T04:00:00Z","items":[
          {"group":"Qwen Cloud","label":"default","window":"5 ชม.","pct":null,
           "tokens":123,"cost":null,"calls":4,"resetAt":null,"weekTokens":9,
           "weekCost":null,"weekPct":null,"costKnown":false},
          {"group":"Claude Code","label":"default","window":"5 ชม.","pct":5,
           "tokens":1,"cost":10.16,"calls":1,"resetAt":null,"weekTokens":2,
           "weekCost":1160.38,"weekPct":96,"costKnown":true,"costKind":"notional"}
        ]}
        """.data(using: .utf8)!
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: json))
        XCTAssertEqual(snap.items.count, 2, "แถวที่ราคาเป็น null ต้องไม่ทำให้ทั้งไฟล์ล้ม")
        XCTAssertNil(snap.items[0].cost)
        XCTAssertNil(snap.items[0].weekCost)
        XCTAssertEqual(snap.items[1].weekCost, 1160.38)
        XCTAssertEqual(snap.items[1].costKind, "notional")
    }

    /// ไฟล์จริงบนเครื่องต้อง decode ผ่าน — เทสต์สังเคราะห์อย่างเดียวไม่พอ
    func testRealSnapshotOnDiskDecodes() throws {
        guard let data = try? Data(contentsOf: UsageSnapshot.fileURL) else {
            throw XCTSkip("ยังไม่มี snapshot.json บนเครื่องนี้")
        }
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: data),
                                 "snapshot.json จริงบนเครื่อง decode ไม่ผ่าน")
        XCTAssertFalse(snap.items.isEmpty)
    }

    /// หน้าตั้งค่าต้องรู้ว่าเอนจินเปิด live อยู่จริงไหม ไม่ใช่เดาจาก UserDefaults
    /// ฝั่งเดียว — เครื่องที่ใช้มาก่อนมีสวิตช์ในแอปเก็บค่าไว้ที่ config.json
    func testSnapshotCarriesTheEffectiveLiveUsageState() throws {
        let json = #"{"generated":"2026-09-10T05:00:00Z","liveUsage":true,"items":[]}"#
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: Data(json.utf8)))
        XCTAssertEqual(snap.liveUsage, true)
    }

    func testOlderSnapshotsWithoutTheFieldStillDecode() throws {
        let json = #"{"generated":"2026-09-10T05:00:00Z","items":[]}"#
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: Data(json.utf8)))
        XCTAssertNil(snap.liveUsage, "ไม่มีฟิลด์ = ไม่รู้ ไม่ใช่ปิด")
    }

    /// เครดิต = โควตาที่ใช้ต่อได้หลังชนเพดานแผน · 0 ต้องแยกจาก "ไม่มีแนวคิดนี้"
    func testCreditsDecodeAndZeroIsNotTreatedAsMissing() throws {
        let json = #"{"generated":"2026-09-10T05:00:00Z","items":[{"group":"Codex","label":"Codex","window":"5h","tokens":0,"calls":0,"weekTokens":0,"credits":0,"creditsUnlimited":false}]}"#
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: Data(json.utf8)))
        XCTAssertEqual(snap.items[0].credits, 0)
        XCTAssertEqual(creditsLabel(snap.items[0]), "เครดิต 0")
    }

    func testABucketWithNoCreditConceptSaysNothing() {
        var it = UsageItem(group: "Claude Code", label: "work", window: "5 ชม.")
        it.credits = nil
        XCTAssertNil(creditsLabel(it), "ถังที่ไม่มีเครดิตต้องเงียบ ไม่ใช่ขึ้น 0")
    }

    func testUnlimitedIsSaidInWordsNotAsANumber() {
        var it = UsageItem(group: "Codex", label: "Codex", window: "5 ชม.")
        it.credits = 0
        it.creditsUnlimited = true
        XCTAssertEqual(creditsLabel(it), "เครดิตไม่จำกัด")
    }

    // MARK: - ใบรีเซ็ตลิมิต

    // MARK: - แต่ละใบได้แถวของตัวเอง

    private func codexWith(_ offsets: [TimeInterval], from now: Date) -> UsageItem {
        var it = UsageItem(group: "Codex", label: "Codex", window: "5 ชม.")
        it.limitResetsExpiring = offsets.map { now.addingTimeInterval($0) }
        it.limitResets = offsets.count
        return it
    }

    func testEveryResetGetsItsOwnRow() {
        let now = Date(timeIntervalSince1970: 1_789_000_000)
        let rows = limitResetRows(codexWith([3600 * 24 * 23, 3600 * 24 * 24], from: now))
        XCTAssertEqual(rows.count, 2)
        XCTAssertEqual(rows.map(\.extra), [0, 0])
        XCTAssertEqual(rows[0].expiresAt, now.addingTimeInterval(3600 * 24 * 23))
    }

    // MARK: - หัวข้อที่ยุบได้

    /// หัวข้อต้องบอกเองว่าคืออะไร — ก่อนหน้านี้เขียนแค่ "รีเซ็ต" แล้วไปนั่งอยู่ใน
    /// คอลัมน์ที่แปลว่า "อีกนานแค่ไหนจะรีเซ็ต" คนอ่านเลยเข้าใจเป็นคนละเรื่อง
    func testTheHeaderSaysWhatTheseThingsAre() {
        let now = Date()
        let title = limitResetsTitle(codexWith([86400, 172_800], from: now))
        XCTAssertEqual(title, "ใบรีเซ็ตลิมิต 2 ใบ")
    }

    func testNoResetsHasNoHeader() {
        XCTAssertNil(limitResetsTitle(UsageItem(group: "Codex", label: "Codex", window: "5h")))
    }

    /// เหลือศูนย์ใบยังต้องพูด — แปลว่าชนเพดานแล้วไม่มีทางออก
    func testRunningOutIsStillAnnounced() {
        var it = UsageItem(group: "Codex", label: "Codex", window: "5h")
        it.limitResets = 0
        XCTAssertEqual(limitResetsTitle(it), "ไม่เหลือใบรีเซ็ตลิมิต")
    }

    /// แต่ละบรรทัดต้องอ่านออกว่าเป็น "วันหมดอายุของใบ" ไม่ใช่ "เวลาที่ลิมิตจะรีเซ็ต"
    func testEachLineReadsAsAnExpiryNotAReset() {
        let now = Date(timeIntervalSince1970: 1_789_000_000)
        let line = limitResetLine(ResetRow(expiresAt: now.addingTimeInterval(86400 * 2), extra: 0),
                                  now: now)
        XCTAssertEqual(line, "ใช้ได้อีก 2วัน 0ชม.")
    }

    func testTheCollapsedSummaryLineNamesHowManyAreHidden() {
        let line = limitResetLine(ResetRow(expiresAt: nil, extra: 3), now: Date())
        XCTAssertEqual(line, "และอีก 3 ใบ")
    }

    func testNoResetsMeansNoRows() {
        XCTAssertTrue(limitResetRows(UsageItem(group: "Codex", label: "Codex", window: "5h")).isEmpty)
    }

    func testExactlyTheLimitStillShowsThemAll() {
        let now = Date()
        let rows = limitResetRows(codexWith([1, 2, 3, 4].map { Double($0) * 86400 }, from: now),
                                  limit: 4)
        XCTAssertEqual(rows.count, 4)
        XCTAssertTrue(rows.allSatisfy { $0.extra == 0 })
    }

    /// การ์ดต้องไม่ยาวไม่รู้จบเมื่อมีใบเยอะ — ที่เหลือยุบเป็นแถวสรุป
    func testTooManyResetsCollapseIntoASummaryRow() {
        let now = Date()
        let rows = limitResetRows(codexWith([1, 2, 3, 4, 5, 6].map { Double($0) * 86400 }, from: now),
                                  limit: 4)
        XCTAssertEqual(rows.count, 4)
        XCTAssertEqual(rows.prefix(3).map(\.extra), [0, 0, 0])
        XCTAssertNil(rows[3].expiresAt, "แถวสรุปไม่ผูกกับใบใดใบหนึ่ง")
        XCTAssertEqual(rows[3].extra, 3, "6 ใบ โชว์ 3 ยุบ 3")
    }

    func testLimitResetsDecodeWithTheirSoonestExpiry() throws {
        let json = #"{"generated":"2026-09-10T05:00:00Z","items":[{"group":"Codex","label":"Codex","window":"5h","tokens":0,"calls":0,"weekTokens":0,"limitResets":2,"limitResetExpiresAt":"2026-10-04T01:06:00Z"}]}"#
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: Data(json.utf8)))
        XCTAssertEqual(snap.items[0].limitResets, 2)
        XCTAssertNotNil(snap.items[0].limitResetExpiresAt)
        XCTAssertEqual(limitResetsTitle(snap.items[0]), "ใบรีเซ็ตลิมิต 2 ใบ")
    }

    func testABucketWithoutResetsSaysNothing() {
        let it = UsageItem(group: "Claude Code", label: "work", window: "5 ชม.")
        XCTAssertNil(limitResetsTitle(it))
    }

    /// การ์ดใส่ได้บรรทัดเดียว รายละเอียดว่าใบไหนหมดเมื่อไหร่จึงอยู่ใน tooltip
    func testEachResetExpiryIsAvailableInDetail() throws {
        let now = Date(timeIntervalSince1970: 1_789_000_000)
        var it = UsageItem(group: "Codex", label: "Codex", window: "5 ชม.")
        it.limitResets = 2
        it.limitResetsExpiring = [now.addingTimeInterval(3600 * 24 * 23 + 3600 * 12),
                                  now.addingTimeInterval(3600 * 24 * 24 + 3600 * 9)]
        let detail = try XCTUnwrap(limitResetsDetail(it, now: now))
        XCTAssertTrue(detail.contains("23วัน 12ชม."))
        XCTAssertTrue(detail.contains("24วัน 9ชม."))
        XCTAssertEqual(detail.split(separator: "\n").count, 3, "หัวข้อหนึ่งบรรทัด + ใบละบรรทัด")
    }

    func testNoResetsMeansNoTooltip() {
        let it = UsageItem(group: "Claude Code", label: "work", window: "5 ชม.")
        XCTAssertNil(limitResetsDetail(it, now: Date()))
    }

    func testTheDetailListDecodesFromTheSnapshot() throws {
        let json = #"{"generated":"2026-09-10T05:00:00Z","items":[{"group":"Codex","label":"Codex","window":"5h","tokens":0,"calls":0,"weekTokens":0,"limitResets":2,"limitResetsExpiring":["2026-10-04T01:06:00Z","2026-10-04T22:41:00Z"]}]}"#
        let snap = try XCTUnwrap(UsageSnapshot.decode(from: Data(json.utf8)))
        XCTAssertEqual(snap.items[0].limitResetsExpiring.count, 2)
    }
}
