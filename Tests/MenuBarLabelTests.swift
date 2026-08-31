import XCTest
@testable import AIUsage

final class MenuBarLabelTests: XCTestCase {
    private let now = Date()

    private func snapshot(_ items: [UsageItem], generatedAgo: TimeInterval = 30) -> UsageSnapshot {
        UsageSnapshot(generated: now.addingTimeInterval(-generatedAgo), items: items)
    }

    // MARK: - จุดแดงถังวิกฤตที่ไม่ได้ปัก

    private func named(_ group: String, _ label: String,
                       pct: Double?, weekPct: Double?,
                       severity: String? = "normal") -> UsageItem {
        UsageItem(group: group, label: label, window: "5 ชม.", pct: pct,
                  weekPct: weekPct, pctSource: "official", confidence: "valid",
                  weekConfidence: "valid",
                  dataFetchedAt: now.addingTimeInterval(-60), severity: severity)
    }

    /// ปัก Codex ไว้อย่างเดียวแล้ว Claude weekly พุ่ง 96% ต้องมีอะไรบอก
    func testUnpinnedCriticalIsFlagged() {
        let snap = snapshot([named("Codex", "Codex", pct: 12, weekPct: 30),
                             named("Claude Code", "default", pct: 5, weekPct: 96,
                                   severity: "critical")])
        XCTAssertTrue(hasUnpinnedCritical(snapshot: snap, pinned: ["Codex/Codex"]))
    }

    func testCriticalOnAPinnedBucketIsNotFlagged() {
        let snap = snapshot([named("Claude Code", "default", pct: 5, weekPct: 96,
                                   severity: "critical")])
        XCTAssertFalse(hasUnpinnedCritical(snapshot: snap,
                                           pinned: ["Claude Code/default"]),
                       "ตัวที่เห็นอยู่แล้วไม่ต้องเตือนซ้ำ")
    }

    func testErrorRowsNeverReachTheBar() {
        var broken = named("Claude Code", "work", pct: 96, weekPct: 96)
        broken.error = "OSError"
        let snap = snapshot([broken, named("Codex", "Codex", pct: 12, weekPct: 30)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
    }

    /// snapshot ตาย = เอนจินหยุดเดินไปนานแล้ว — เลขค้างเก่าห้ามแสร้งว่าเป็นปัจจุบัน
    /// และถังมี traffic ก็ห้ามขึ้นเป็นขีดด้วย เพราะขีดตอนตายแปลว่า "ยังเดินอยู่แต่ไม่มีเลข" ซึ่งโกหก
    func testDeadSnapshotDropsAllSegments() {
        var item = named("Codex", "Codex", pct: 99, weekPct: 30)
        item.weekTokens = 1_000_000
        let segments = menuBarSegments(snapshot: snapshot([item], generatedAgo: 2 * 3600),
                                       now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertTrue(segments.isEmpty)
    }

    func testUnsureConfidenceShowsNoNumber() {
        var item = named("Claude Code", "default", pct: 5, weekPct: 96)
        item.confidence = "unsure"
        item.weekConfidence = "unsure"
        let segments = menuBarSegments(snapshot: snapshot([item]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertTrue(segments.isEmpty, "ไม่แน่ใจ = ไม่มีเลข ไม่ใช่เลขมั่วๆ")
    }

    /// บัญชี ccs ที่แคชโควตาเก่าจนไม่มี % — ต้องยังเห็นบนแถบเป็นขีดคู่ ไม่ใช่ล่องหน
    /// เห็นทุกบัญชีคือเหตุผลข้อแรกของแอปนี้
    func testAccountWithTrafficButNoNumbersKeepsItsSlot() {
        var mooz = named("Claude Code", "mooz", pct: nil, weekPct: nil)
        mooz.confidence = "unsure"
        mooz.weekConfidence = "unsure"
        mooz.weekTokens = 60_000_000
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96), mooz])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.id), ["Claude Code/default", "Claude Code/mooz"])
        XCTAssertEqual(segments[1].top, "–")
        XCTAssertNil(segments[1].bottom, "ไม่มีเลขเลย = ขีดเดียว ไม่ใช่ขีดคู่")
        XCTAssertEqual(segments.map(\.tag), ["de", "mo"], "โลโก้ซ้ำต้องมีป้ายบอกบัญชี")
    }

    // MARK: - หมุดต้องไม่ทำให้โลโก้หาย

    private func groupItem(_ group: String, _ label: String, pct: Double) -> UsageItem {
        UsageItem(group: group, label: label, window: "5 ชม.", pct: pct,
                  pctSource: "official", confidence: "valid",
                  dataFetchedAt: now.addingTimeInterval(-60), severity: "normal")
    }

    func testPinsFilterSegmentsAndKeepLogos() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [],
                                       pinned: ["Codex/Codex"])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
        XCTAssertFalse(segments[0].assetName.isEmpty, "โลโก้ต้องไม่หายตอนปักหมุด")
    }

    func testNoPinsShowsEveryVisibleGroup() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [])
        XCTAssertEqual(segments.count, 2, "ไม่ปัก = โชว์ทุกเจ้าที่เปิดไว้")
    }

    func testPinnedOrderDrivesSegmentOrder() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [],
                                       pinned: ["Codex/Codex", "Claude Code/default"])
        XCTAssertEqual(segments.map(\.group), ["Codex", "Claude Code"])
    }

    func testPinToAMissingBucketFallsBackToShowingEverything() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [],
                                       pinned: ["GLM/ที่หายไป"])
        XCTAssertEqual(segments.count, 1, "ปักไปที่ถังที่ไม่มีแล้ว ต้องไม่ได้แถบว่าง")
    }

    // MARK: - เลขซ้อนสองบรรทัดแบบ OpenUsage

    func testSegmentStacksBothWindows() {
        var item = groupItem("Claude Code", "default", pct: 6)
        item.weekPct = 100
        item.weekConfidence = "valid"
        let segments = menuBarSegments(snapshot: snapshot([item]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments[0].top, "6%")
        XCTAssertEqual(segments[0].bottom, "100%")
    }

    /// หน้าต่างเดียว = บรรทัดเดียวตัวใหญ่ — ขีดค้ำบรรทัดที่ไม่มีข้อมูลไม่บอกอะไรใคร
    /// (สองบรรทัดสงวนไว้สำหรับตอนมีเลขครบทั้ง 5h และ 7d เท่านั้น)
    func testSingleWindowCollapsesToOneLine() {
        let codex = groupItem("Codex", "Codex", pct: 99)   // มีแต่ 5h
        let segments = menuBarSegments(snapshot: snapshot([codex]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments[0].top, "99%")
        XCTAssertNil(segments[0].bottom)

        var qwen = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.",
                             weekPct: 100, pctSource: "official", weekConfidence: "valid")
        qwen.resetAt = now.addingTimeInterval(3600)
        let qsegs = menuBarSegments(snapshot: snapshot([qwen]), now: now,
                                    wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(qsegs[0].top, "100%", "มีแต่ weekly ก็ขึ้นเป็นเลขเดี่ยว")
        XCTAssertNil(qsegs[0].bottom)
    }

    /// ขีด — บนแถบเมนูคือที่ที่เสียไปฟรีๆ ถังที่ไม่มีเลขให้ดูใน popover เอา
    func testSegmentWithNoNumbersIsDroppedFromTheBar() {
        let empty = UsageItem(group: "Qwen Cloud", label: "default", window: "5 ชม.")
        let real = groupItem("Codex", "Codex", pct: 99)
        let segments = menuBarSegments(snapshot: snapshot([empty, real]), now: now,
                                       wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.group), ["Codex"])
    }

    /// หลายบัญชี ccs คือเหตุผลข้อแรกของแอปนี้ — แต่ละบัญชีต้องได้ segment ของตัวเอง
    func testEachClaudeAccountGetsItsOwnSegment() {
        var mooz = groupItem("Claude Code", "mooz", pct: 27)
        mooz.weekPct = 27; mooz.weekConfidence = "valid"
        let segments = menuBarSegments(snapshot: snapshot([groupItem("Claude Code", "default", pct: 96), mooz]),
                                       now: now, wokeRecently: false, hidden: [], pinned: [])
        XCTAssertEqual(segments.map(\.id), ["Claude Code/default", "Claude Code/mooz"])
        XCTAssertEqual(segments.map(\.tag), ["de", "mo"], "โลโก้ซ้ำกันต้องมีป้ายบัญชี")
    }

    func testSingleAccountNeedsNoTag() {
        let segments = menuBarSegments(snapshot: snapshot([groupItem("Codex", "Codex", pct: 99)]),
                                       now: now, wokeRecently: false, hidden: [], pinned: [])
        XCTAssertNil(segments[0].tag)
    }

    // MARK: - ลำดับที่ผู้ใช้จัดเอง

    func testUserOrderRearrangesSegments() {
        let snap = snapshot([groupItem("Claude Code", "default", pct: 96),
                             groupItem("Codex", "Codex", pct: 92)])
        let segments = menuBarSegments(snapshot: snap, now: now, wokeRecently: false,
                                       hidden: [], pinned: [],
                                       order: ["Codex/Codex", "Claude Code/default"])
        XCTAssertEqual(segments.map(\.id), ["Codex/Codex", "Claude Code/default"])
    }

    /// ถังใหม่ที่เพิ่งงอก (ยังไม่เคยถูกจัด) ต้องต่อท้าย ไม่แทรกมั่วและไม่หาย
    func testUnknownIdsAppendAfterOrderedOnes() {
        let items = [groupItem("Claude Code", "default", pct: 96),
                     groupItem("Codex", "Codex", pct: 92),
                     groupItem("Qwen Cloud", "default", pct: 50)]
        let ordered = applyUserOrder(items, order: ["Codex/Codex"]) { $0.id }
        XCTAssertEqual(ordered.map(\.id),
                       ["Codex/Codex", "Claude Code/default", "Qwen Cloud/default"])
    }

    // MARK: - ความกะทัดรัดบนแถบเมนู

    /// จอมีรอยบากเหลือที่ให้ status item ทุกแอปรวมกันแค่ 772 pt แต่ของเรากิน 295.6 pt
    /// วัดแล้วสิ่งที่ลดความกว้างได้จริงมีสามอย่าง: ตัดเครื่องหมาย % · บีบช่องไฟ · โชว์น้อยลง
    /// (การตัดป้ายบัญชีกับยุบเหลือบรรทัดเดียว "กว้างขึ้น" เพราะป้ายอยู่ใต้โลโก้และ
    /// บรรทัดเดียวใช้ฟอนต์ใหญ่กว่า — จึงไม่มีอยู่ในทางเลือกไหนเลย)
    private func seg(_ id: String, _ top: String, _ bottom: String? = nil) -> MenuBarSegment {
        MenuBarSegment(id: id, group: "Claude Code", assetName: "claude", tag: nil,
                       top: top, bottom: bottom, color: "#E49A54")
    }

    private var sixSegments: [MenuBarSegment] {
        [seg("a", "23%"), seg("b", "100%"), seg("c", "25%"),
         seg("d", "–"), seg("e", "13%", "53%"), seg("f", "0%", "21%")]
    }

    func testFullDensityChangesNothing() {
        let out = applyDensity(sixSegments, .full)
        XCTAssertEqual(out.segments, sixSegments)
        XCTAssertEqual(out.overflow, 0)
    }

    /// กระชับ = ตัดแค่เครื่องหมาย % ทุกถังยังอยู่ครบและตัวเลขขนาดเดิม
    func testSnugDropsThePercentSignAndKeepsEveryBucket() {
        let out = applyDensity(sixSegments, .snug)
        XCTAssertEqual(out.segments.count, 6)
        XCTAssertEqual(out.overflow, 0)
        XCTAssertEqual(out.segments.map(\.top), ["23", "100", "25", "–", "13", "0"])
        XCTAssertEqual(out.segments.compactMap(\.bottom), ["53", "21"])
    }

    /// ขีดคือ "มีบัญชีแต่ยังไม่มีเลข" ไม่ใช่ตัวเลขที่มีหน่วย ห้ามโดนแปลง
    func testSnugKeepsTheDashPlaceholder() {
        XCTAssertEqual(applyDensity([seg("d", "–")], .snug).segments.first?.top, "–")
    }

    func testSnugKeepsIdentityOfEachBucket() {
        XCTAssertEqual(applyDensity(sixSegments, .snug).segments.map(\.id),
                       sixSegments.map(\.id))
    }

    /// น้อยที่สุด = กระชับ + เหลือ 3 ถังแรกตามลำดับที่ผู้ใช้จัด/ปักไว้
    func testMinimalKeepsThreeBucketsAndCountsTheRest() {
        let out = applyDensity(sixSegments, .minimal)
        XCTAssertEqual(out.segments.map(\.id), ["a", "b", "c"])
        XCTAssertEqual(out.overflow, 3, "ที่เหลือต้องนับได้ ไม่ใช่หายเงียบ")
        XCTAssertEqual(out.segments.map(\.top), ["23", "100", "25"],
                       "น้อยที่สุดต้องกระชับด้วย ไม่ใช่แค่ตัดจำนวน")
    }

    func testMinimalWithFewBucketsHasNothingLeftOver() {
        let out = applyDensity(Array(sixSegments.prefix(2)), .minimal)
        XCTAssertEqual(out.segments.count, 2)
        XCTAssertEqual(out.overflow, 0)
    }

    /// ช่องไฟเป็นส่วนหนึ่งของความกะทัดรัด — เต็ม 10 pt ที่เหลือ 6 pt
    func testGapNarrowsOutsideFullDensity() {
        XCTAssertEqual(BarDensity.full.segmentGap, 10)
        XCTAssertEqual(BarDensity.snug.segmentGap, 6)
        XCTAssertEqual(BarDensity.minimal.segmentGap, 6)
    }

    /// "+3" บอกว่ายังมีของ แต่ไม่ได้บอกว่าของนั้นกำลังจะเต็ม — ต้องมีจุดแดงด้วย
    func testCriticalBucketDroppedByDensityRaisesTheDot() {
        let snap = snapshot([named("Claude Code", "default", pct: 5, weekPct: 10),
                             named("Qwen Cloud", "default", pct: 5, weekPct: 10),
                             named("Codex", "Codex", pct: 5, weekPct: 10),
                             named("Claude Code", "work", pct: 5, weekPct: 96,
                                   severity: "critical")])
        XCTAssertTrue(hasCritical(snapshot: snap, ids: ["Claude Code/work"]))
        XCTAssertFalse(hasCritical(snapshot: snap, ids: ["Codex/Codex"]),
                       "ถังที่ยังอยู่บนแถบไม่ต้องมีจุดแดงซ้ำ")
    }

    func testNothingDroppedMeansNoDot() {
        let snap = snapshot([named("Claude Code", "work", pct: 5, weekPct: 96,
                                   severity: "critical")])
        XCTAssertFalse(hasCritical(snapshot: snap, ids: []))
    }
}

// MARK: - ความกว้างของ status item

import AppKit
import SwiftUI

/// งบความกว้างของแถบ
///
/// หมายเหตุ: เทสต์ในคลาสนี้จับบั๊ก "เลขกลายเป็น …" ไม่ได้ ความกว้างเท่ากันเป๊ะ
/// ทั้งตอนดีและตอนพัง (148.17pt) ตัวที่จับได้อยู่ใน MenuBarInkTests
/// ที่นี่คุมแค่ว่าแถบไม่บวมจนขอที่เกินพอดี
final class MenuBarWidthTests: XCTestCase {

    private func seg(_ id: String, _ top: String, _ bottom: String?,
                     tag: String?) -> MenuBarSegment {
        MenuBarSegment(id: id, group: "Codex", assetName: "codex", tag: tag,
                       top: top, bottom: bottom, color: "#67C587")
    }

    private func width(_ segments: [MenuBarSegment]) -> CGFloat {
        let hosting = NSHostingView(rootView: MenuBarContent(segments: segments,
                                                             alert: false, dimmed: false))
        hosting.layoutSubtreeIfNeeded()
        return hosting.fittingSize.width
    }

    /// แถบจริงของผู้ใช้ตอนเจอบั๊ก — 4 ถัง Codex ไม่มีป้ายบัญชี
    private var realBar: [MenuBarSegment] {
        [seg("Claude Code/mooz", "17", "20", tag: "mo"),
         seg("Claude Code/work", "9", "8", tag: "wo"),
         seg("Codex/Codex", "90", "14", tag: nil),
         seg("Claude Code/default", "6", "14", tag: "de")]
    }

    /// updateBar() ตั้ง statusItem.length จาก fittingSize ทันทีหลังเปลี่ยน rootView
    /// ถ้าค่านั้นเป็นของเนื้อหารอบก่อน ความกว้างจะตามหลังตลอดและเนื้อหาโดนตัด
    func testFittingSizeReflectsNewContentImmediately() {
        let hosting = NSHostingView(rootView: MenuBarContent(
            segments: [seg("Codex/Codex", "0", "1", tag: nil)], alert: false, dimmed: false))
        let narrow = hosting.fittingSize.width

        hosting.rootView = MenuBarContent(segments: [seg("Codex/Codex", "100", "100", tag: nil)],
                                          alert: false, dimmed: false)
        let immediately = hosting.fittingSize.width
        hosting.layoutSubtreeIfNeeded()

        XCTAssertGreaterThan(immediately, narrow, "3 หลักต้องกว้างกว่า 1 หลัก")
        XCTAssertEqual(immediately, hosting.fittingSize.width, accuracy: 0.01,
                       "fittingSize ต้องเป็นของเนื้อหาล่าสุด ไม่ใช่รอบก่อน")
    }

    /// 4 ถังต้องยังพอดี menu bar ที่มีของอื่นอยู่ด้วย — ยิ่งขอกว้าง ยิ่งเสี่ยงโดนบีบ
    func testFourBucketsStayWithinAReasonableWidth() {
        XCTAssertLessThanOrEqual(width(realBar), 200,
                                 "แถบกว้างขึ้นจนระบบให้ไม่ครบ แล้วตัวเลขจะโดนตัด")
    }

    /// เลขหลายหลักต้องได้ที่ของมันจริง — ไม่ใช่กว้างเท่าเลขหลักเดียวแล้วไปตัดเอาตอนวาด
    func testMoreDigitsAskForMoreWidth() {
        XCTAssertGreaterThan(width([seg("Codex/Codex", "100", "100", tag: nil)]),
                             width([seg("Codex/Codex", "9", "9", tag: nil)]))
    }
}

/// เลขบนแถบถูกวาดครบจริงไหม — วัดจากภาพที่เรนเดอร์ ไม่ใช่จากขนาด
///
/// เคสจริง 2026-08-31: Codex อยู่ที่ 90/14 แต่แถบวาด "…" สองบรรทัด ถังอื่นเลขครบ
/// ความกว้างของแถบเท่ากันเป๊ะทั้งตอนดีและตอนพัง (148.17pt) เทสต์ที่วัดขนาดจึงจับไม่ได้
///
/// ค่าคงที่ที่ใช้จับ: แถบที่วาดด้วยขนาดธรรมชาติของตัวเอง ต้องได้ภาพเดียวกับ
/// ตอนถูกวาดในกรอบที่กว้างเหลือเฟือ ถ้าต่างกันแปลว่าขนาดธรรมชาติยังไม่พอ
/// กับเนื้อหาแล้วมีอะไรถูกย่อทิ้ง (นับพิกเซลเข้มบนพื้นขาวเป็นตัวแทนของเนื้อหา)
final class MenuBarInkTests: XCTestCase {

    private func claude(_ label: String, _ tag: String, _ top: String, _ bottom: String) -> MenuBarSegment {
        MenuBarSegment(id: "Claude Code/\(label)", group: "Claude Code", assetName: "claude",
                       tag: tag, top: top, bottom: bottom, color: "#E49A54")
    }

    private func codex(_ top: String, _ bottom: String) -> MenuBarSegment {
        MenuBarSegment(id: "Codex/Codex", group: "Codex", assetName: "codex",
                       tag: nil, top: top, bottom: bottom, color: "#67C587")
    }

    /// จำนวนพิกเซลเข้มบนพื้นขาว — width=nil คือปล่อยให้แถบใช้ขนาดธรรมชาติ
    @MainActor
    private func ink(_ segments: [MenuBarSegment], width: CGFloat? = nil) throws -> Int {
        let bar = MenuBarContent(segments: segments, alert: false, dimmed: false, gap: 6)
        let view = Group {
            if let width { bar.frame(width: width, alignment: .leading) } else { bar }
        }.padding(4).background(Color.white)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.nsImage)
        let rep = try XCTUnwrap(image.tiffRepresentation.flatMap(NSBitmapImageRep.init(data:)))
        var dark = 0
        for y in 0..<rep.pixelsHigh {
            for x in 0..<rep.pixelsWide where (rep.colorAt(x: x, y: y)?.brightnessComponent ?? 1) < 0.5 {
                dark += 1
            }
        }
        return dark
    }

    /// แถบจริงตอนเจอบั๊ก — Codex ไม่มีป้ายบัญชีจึงเป็นช่องที่โดนย่อ
    private var realBar: [MenuBarSegment] {
        [claude("mooz", "mo", "17", "20"), claude("work", "wo", "9", "8"),
         codex("90", "14"), claude("default", "de", "6", "14")]
    }

    /// ที่ขนาดธรรมชาติต้องวาดได้ครบเท่ากับตอนมีที่เหลือเฟือ
    @MainActor
    func testBarDrawsEverythingAtItsNaturalSize() throws {
        let natural = try ink(realBar)
        let roomy = try ink(realBar, width: 400)
        XCTAssertEqual(natural, roomy, accuracy: 20,
                       "ที่ขนาดธรรมชาติวาดได้ไม่ครบ ขาดไป \(roomy - natural) จุด — มีช่องถูกย่อเป็น \"…\"")
    }

    /// ป้ายบัญชีต้องไม่หายเพราะเลขข้างๆ ยาวขึ้น (regression ของ layoutPriority)
    @MainActor
    func testAccountTagSurvivesWideNumbers() throws {
        let bar = [claude("mooz", "mo", "100", "28"), codex("54", "23")]
        let natural = try ink(bar)
        let roomy = try ink(bar, width: 400)
        XCTAssertEqual(natural, roomy, accuracy: 20,
                       "ป้าย mo ถูกย่อเป็นจุดไข่ปลาตอนเลขเป็นสามหลัก")
    }
}
