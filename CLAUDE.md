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
App/SettingsView.swift       ซ่อน/แสดงถัง · ใส่ราคาเองสำหรับถังที่ระบบไม่รู้ราคา
Shared/UsageSnapshot.swift   โมเดล Codable
Shared/Freshness.swift       freshness/certainty classification
Shared/Preferences.swift     ปักหมุด/ซ่อน/ราคาที่ผู้ใช้เลือกเอง — UserDefaults ล้วน ไม่ปนกับ snapshot
Shared/Appearance.swift      ธีมของ popover (3 แบบ)
```

ข้อมูลไหลทางเดียว: Python เขียน `~/Library/Application Support/AIUsage/snapshot.json` → Swift อ่านอย่างเดียว

## ข้อควรระวัง

- ห้ามเปิด App Sandbox เพราะ `NSHomeDirectory()` ต้องชี้ไป home จริง
- deployment target คือ macOS 14.0
- แอปเรียก engine เอง ไม่ใช้ launchd และไม่ใช้ WidgetKit
- ห้ามอ่านหรือส่งต่อ `ANTHROPIC_AUTH_TOKEN` / credentials
- ถ้าไม่มีเพดานหรือข้อมูลไม่แน่ใจ ห้ามแสดงแถบทึบเป็นตัวเลข
- ห้ามแสดง `$0.00` เมื่อ `costKnown` เป็น false — ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี" (`PRICES` มีแค่โมเดล Anthropic ถังอื่นต้องคืน `cost: null`)
- ถังกำหนดจาก `ANTHROPIC_BASE_URL` ใน `~/.ccs/*.settings.json` ไม่ใช่ชื่อโมเดล — เช่น `deepseek-v4-flash-0731` คือช่อง Sonnet ของแผน Qwen Cloud ไม่ใช่บัญชี DeepSeek แยกต่างหาก
- `cachedUsageUtilization` คือแหล่ง % ทางการของ Claude รีเฟรชเฉพาะตอนเปิด `/usage` หรือเริ่ม session ใหม่เท่านั้น ไม่รีเฟรชระหว่าง session — พอหน้าต่างหมุนไป (ราว 2 วัน) แอปจะรายงาน "ไม่แน่ใจ" (ไม่มี %) พร้อม token ดิบและคำแนะนำให้เปิด `/usage`

## ตรวจว่าใช้ได้จริง

```bash
python3 -m unittest discover -s engine/tests
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
log stream --predicate 'process == "AIUsage"' --level error
```

## ที่ยังทำไม่เสร็จ

- Qwen Cloud ยังไม่มีแหล่ง % — Alibaba ไม่ประกาศสูตร token → credit และไม่มี API สาธารณะ
- GLM coding plan หมดอายุ — endpoint คืน "ไม่มี coding plan" ตอนนี้ ถ้าต่ออายุต้องรองรับทั้งสองแบบ
- ยังไม่มีโลโก้ provider จริงและการแจ้งเตือนใกล้ชนลิมิต
