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
App/SettingsView.swift       ซ่อน/แสดงถัง · ใส่ราคาเอง · สวิตช์ live usage · สวิตช์แจ้งเตือน
App/PythonLocator.swift      หา interpreter จริง — /usr/bin/python3 เป็น stub ห้ามเรียก
App/LimitNotifier.swift      แจ้งเตือน 80%/95% พร้อมกติกากันเด้งซ้ำทุก 60 วินาที
.github/workflows/           ci.yml รันเทสต์ · release.yml ออกรุ่นจาก tag แล้วอัปเดต cask
Casks/aiusage.rb             Homebrew cask — เวอร์ชันกับ sha256 ถูกเขียนโดย release.yml
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
- ห้ามอ่านหรือส่งต่อ `ANTHROPIC_AUTH_TOKEN` / credentials — ข้อยกเว้นเดียว (ผู้ใช้อนุมัติ 2026-08-11 และขยาย 2026-08-12): `engine/aiusage/liveusage.py` อ่าน OAuth token ของ Claude Code จาก Keychain เพื่อเรียก endpoint usage + ต่ออายุผ่าน endpoint token ของ Anthropic (`api.anthropic.com` / `console.anthropic.com` เท่านั้น) และเขียน token ที่ rotate แล้วกลับ Keychain item เดิม — ห้าม log/print/เขียนลงไฟล์อื่น ห้ามส่งไป host อื่นเด็ดขาด และห้ามรีเฟรชโดยไม่ซ้อมเขียน Keychain ให้ผ่านก่อน (refresh token ถูก rotate — เก็บตัวใหม่ไม่ได้ = บัญชีหลุด)
- live usage เป็น opt-in ปิดไว้เป็นค่าเริ่มต้นสำหรับเครื่องใหม่ — สวิตช์อยู่ใน UserDefaults ของแอปแล้วส่งให้เอนจินทาง `--live-usage=0|1` **ห้ามให้ Swift เขียน `config.json`** เพราะเอนจินก็เขียนไฟล์นั้นเองตอนเจอบัญชีใหม่ สองฝั่งเขียนพร้อมกันแล้วสวิตช์ความยินยอมจะหายเงียบๆ · config ที่ไม่มีคีย์ `liveUsage` = เครื่องที่ใช้มาก่อน ต้อง migrate เป็น `true` ไม่ใช่ปิดทิ้ง
- `codex_stats()` อ่าน rollout ย้อนจากท้ายไฟล์แล้วหยุดที่ขอบ 7 วัน — session ที่เปิดค้างไว้เป็นเดือนโตถึงระดับ GB (เคสจริง 2026-09-10: 2.4 GB) การสแกนทั้งไฟล์ทุก 60 วินาทีจะไปชน timeout 45 วินาที
- Codex ออก `limit_id` ใหม่ทั้งใบเมื่อเปลี่ยนแผน — 0% หลัง upgrade คือของจริง ไม่ใช่บั๊ก ก่อนไล่หาบั๊กในเอนจินให้เช็ก `limit_id` ก่อน
- ถ้าไม่มีเพดานหรือข้อมูลไม่แน่ใจ ห้ามแสดงแถบทึบเป็นตัวเลข
- ห้ามแสดง `$0.00` เมื่อ `costKnown` เป็น false — ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี" (`PRICES` มีแค่โมเดล Anthropic ถังอื่นต้องคืน `cost: null`)
- ถังกำหนดจาก `ANTHROPIC_BASE_URL` ใน `~/.ccs/*.settings.json` ไม่ใช่ชื่อโมเดล — เช่น `deepseek-v4-flash-0731` คือช่อง Sonnet ของแผน Qwen Cloud ไม่ใช่บัญชี DeepSeek แยกต่างหาก
- % ทางการของ Claude มาจากสองทาง: (1) `liveusage.py` ถาม endpoint สดทุกรอบ (2) ถ้าล้มเหลว ตกกลับไป `cachedUsageUtilization` ซึ่งรีเฟรชเฉพาะตอนเปิด `/usage` หรือเริ่ม session ใหม่ — เก่าได้เป็นวันและจะรายงาน "ไม่แน่ใจ" เมื่อหน้าต่างหมุนไป

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
- ยังไม่ได้ push ขึ้น GitHub — `Casks/aiusage.rb` กับ README ชี้ไป `bg-phunon/AIUsage` ที่ยังไม่มีจริง
- ยังไม่มี Sparkle — ตอนนี้อัปเดตผ่าน `brew upgrade --cask aiusage` ถ้าจะใส่ต้องประกาศ `auto_updates true` ใน cask ไม่งั้น brew กับ Sparkle จะแย่งกันอัปเดต
- ไม่มี Developer ID/notarization — cask ต้องลงด้วย `--no-quarantine`
