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
}
