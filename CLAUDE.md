# AI Usage — บริบทสำหรับ Claude Code

แอป menu bar แสดงโควตา AI แยกตามบัญชีและถัง endpoint พร้อมตัวเลขทางการของ Claude เมื่อมีข้อมูล

## สิ่งที่ต้องทำ

รัน `./setup.sh` แล้วตรวจว่าไอคอนปรากฏบน menu bar และ popover แสดงข้อมูลจริง

## โครงสร้าง

```
ai-usage.60s.py              เอนจินหลัก — พาร์ส log เขียน snapshot.json
engine/aiusage/              bucket mapping และ utilization parser
project.yml                  XcodeGen spec
setup.sh                     xcodegen + xcodebuild + ติดตั้งลง /Applications
App/AIUsageApp.swift         NSStatusItem และ lifecycle ของ menu bar app
App/EngineRunner.swift       เรียก engine ทุก 60 วินาที พร้อม timeout/error
App/MenuBarLabel.swift       ข้อความแถบ menu bar สองบรรทัด
App/PopoverView.swift        รายละเอียดบัญชีและถังโควตา
Shared/UsageSnapshot.swift   โมเดล Codable
Shared/Freshness.swift       freshness/certainty classification
```

ข้อมูลไหลทางเดียว: Python เขียน `~/Library/Application Support/AIUsage/snapshot.json` → Swift อ่านอย่างเดียว

## ข้อควรระวัง

- ห้ามเปิด App Sandbox เพราะ `NSHomeDirectory()` ต้องชี้ไป home จริง
- deployment target คือ macOS 14.0
- แอปเรียก engine เอง ไม่ใช้ launchd และไม่ใช้ WidgetKit
- ห้ามอ่านหรือส่งต่อ `ANTHROPIC_AUTH_TOKEN` / credentials
- ถ้าไม่มีเพดานหรือข้อมูลไม่แน่ใจ ห้ามแสดงแถบทึบเป็นตัวเลข

## ตรวจว่าใช้ได้จริง

```bash
python3 -m unittest discover -s engine/tests
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
log stream --predicate 'process == "AIUsage"' --level error
```

## ที่ยังทำไม่เสร็จ

- Qwen Cloud และ GLM ยังไม่มีแหล่ง % ที่เชื่อถือได้ รอแผน 2
- ยังไม่มีหน้า settings โลโก้ provider และการแจ้งเตือนใกล้ชนลิมิต
