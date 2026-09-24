# AI Usage — บริบทสำหรับ Claude Code

แอป menu bar แสดงโควตา AI แยกตามบัญชีและถัง endpoint พร้อมตัวเลขทางการของ Claude เมื่อมีข้อมูล

## สิ่งที่ต้องทำ

รัน `./setup.sh` แล้วตรวจว่าไอคอนปรากฏบน menu bar และ popover แสดงข้อมูลจริง

## โครงสร้าง

```
ai-usage.60s.py              เอนจินหลัก — พาร์ส log เขียน snapshot.json
engine/aiusage/              bucket mapping และ utilization parser
engine/aiusage/clilive.py    ถาม Claude Code CLI ผ่าน control request get_usage
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
- Codex ออก `limit_id` ใหม่ทั้งใบเมื่อเปลี่ยนแผน (เคสจริง 2026-09-10: `codex` → `codex_bengalfox`) ถังใหม่บางใบเป็น **ช่องเปล่า** — รายงาน 0% ค้างตลอดและเลื่อน `resets_at` ตามนาฬิกาให้ "เหลืออีก 5 ชม." ทุกครั้งที่ถูกถาม จับด้วย `window_never_elapses()` ที่ถามว่า "มี `resets_at` ค่าไหนอยู่นิ่งเกิน 15 นาทีไหม" แล้วรายงานเป็น `unsure` ไม่ใช่ 0% · **ห้ามกลับไปเทียบเวลาที่ผ่านไปกับเวลาที่เหลือลดลงทั้งช่วง** (กฎเดิม เคสจริง 2026-09-19): หยุดใช้ Codex 5 วันครึ่งแล้วกลับมาตอนหน้าต่างหมุนใหม่ ช่วงที่เฝ้าดูกินเวลาว่างไปด้วยแต่เวลาที่เหลือถูกเติมกลับเต็มตอนรีเซ็ต ถังจริงเลยถูกตีว่าปลอมและ % สัปดาห์หายทุกครั้งที่รีเซ็ต · `seen` ของถังหนึ่งกินหลายรอบหน้าต่าง อย่าคิดว่าทุก record อยู่รอบเดียวกัน · อย่าตัดสินจาก `used_percent` อย่างเดียว ตัวชี้ขาดคือเวลารีเซ็ตนิ่งหรือไหล
- Codex **ไม่เคยรายงาน 100% ผ่าน `rate_limits`** — ตอนชนจริงมันประกาศเป็น event `task_complete` ที่มี `error.codex_error_info: "usage_limit_exceeded"` และ "try again at <เวลาท้องถิ่น>" ซึ่งเท่ากับเวลารีเซ็ตของหน้าต่างที่ชน (เคสจริง 2026-09-11: rate_limits ค้าง 79% อีก 4 ชม.ต่อมาจึงชน) `_apply_limit_hit()` จับคู่เวลานั้นกับหน้าต่างที่รู้แล้วรายงาน 100% จนรีเซ็ต — เลขจริงที่ใหม่กว่าคำประกาศชนะเสมอ (กดใช้ใบรีเซ็ต)
- `codex_bengalfox` (GPT-5.3-Codex-Spark) คือถังของโมเดล Spark ที่ถูกเรียกสลับกับโมเดลหลักทั้งวัน และเป็นช่องเปล่าเสมอ **ไม่เกี่ยวกับเวอร์ชัน CLI** — เคยสรุปผิดว่า 0.153.4 เป็นต้นเหตุ ที่จริงวันนั้นหน้าต่าง 5 ชม. หมด แล้วรีเซ็ตพอดีตอนทดสอบหลังอัปเดต
- session Codex ที่เปิดค้างตอนชนลิมิต (และ subagent ที่มันแตกออกมา) รายงานแต่ถัง Spark หลังใช้ใบรีเซ็ต — เคสจริง 2026-09-11: 116 record จาก session แม่ที่เปิดมาตั้งแต่ 15 ส.ค. (CLI 0.153.4 ค้างในหน่วยความจำ) เป็น bengalfox ทั้งหมด ขณะที่ `codex exec` 0.154.0 ได้ถังจริง 6% · แอปค้างเลขเก่าเพราะล็อกไม่มีเลขจริงให้อ่าน ทางแก้คือปิดแล้วเปิด session ใหม่ — ยังแยกไม่ออกว่าเป็นเพราะเวอร์ชันหรือสถานะของ session (ก่อนชนลิมิต session เดียวกันเคยรายงานถังจริงได้)
- สอง session ที่รันพร้อมกันรายงานคนละถังได้ — `pick_live_window()` เลือกถังที่ยังนับถอยหลังจริงก่อนถังที่ไม่มีวันหมด ไม่ใช่เอาตัวใหม่สุด (session เก่าที่เปิดค้างพ่นช่องเปล่าออกมาเรื่อยๆ record จึงใหม่กว่าเสมอ)
- **เลข Codex หลักมาจาก `codex app-server` → `account/rateLimits/read`** (ดู `fetch_codex_rate_limits()`) — ได้ % สด + ใบรีเซ็ตพร้อม `expiresAt` โดยไม่เรียกโมเดล ไม่เสีย quota และ CLI ใช้ auth ของมันเอง เอนจินไม่แตะ credential · อ่านล็อกอย่างเดียวพึ่งไม่ได้เพราะ session ที่เปิดค้างเขียนแต่ถัง Spark (เคสจริง 2026-09-11: แอปค้าง 6% ขณะของจริง 23%) · cache 120 วิใน `codex-live.json` ถามไม่สำเร็จกลับไปใช้ล็อก · ผูกกับสวิตช์ live usage · **ห้ามส่ง `account/rateLimitResetCredit/consume` เด็ดขาด** — คือการเผาใบรีเซ็ตของผู้ใช้
- ใบรีเซ็ตลิมิต: server เป็นแหล่งหลัก (`rateLimitResetCredits` นับเฉพาะ status `available`) · `codexLimitResets` ใน config เป็นแค่ทางสำรองตอนถาม CLI ไม่ได้ · `[]` จาก server = ยืนยันว่าไม่เหลือ ต่างจาก `None` = ไม่ได้ข้อมูล
- `credits` ในก้อน rate_limits คือโควตาที่ใช้ต่อได้หลังชนเพดานแผน — `0.0` แปลว่า "มีแนวคิดนี้แต่หมดแล้ว" ต่างจาก `None` ที่แปลว่าถังนั้นไม่มีเครดิตเลย ห้ามยุบรวมกัน
- แผน Codex `prolite` ไม่มีหน้าต่าง 5 ชม. — `secondary` เป็น null และ weekly ย้ายไปอยู่ `primary` แถว 5h จึงว่างตามจริง
- ถ้าล็อกตอบ % ไม่ได้จริงๆ ใช้ `codexAnchor` ใน config — `{at, session:{usedPct,resetAt}, weekly:{usedPct,resetAt}}` จดมาจากหน้า usage ของ OpenAI รายงานเป็น `lower_bound` และหมดอายุตอนหน้าต่างรีเซ็ต (พี่น้องกับ `qwenWeeklyAnchor`) · **ห้ามเสกสูตร token → %** อัตราที่วัดจากล็อกแผนเก่าไหลจาก 443k ลงไป 375k ต่อ 1% แปลว่า % ของ OpenAI ไม่ได้ผูกกับ token ตรงๆ
- ถ้าไม่มีเพดานหรือข้อมูลไม่แน่ใจ ห้ามแสดงแถบทึบเป็นตัวเลข
- ห้ามแสดง `$0.00` เมื่อ `costKnown` เป็น false — ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี" (`PRICES` มีแค่โมเดล Anthropic ถังอื่นต้องคืน `cost: null`)
- ถังกำหนดจาก `ANTHROPIC_BASE_URL` ใน `~/.ccs/*.settings.json` ไม่ใช่ชื่อโมเดล — เช่น `deepseek-v4-flash-0731` คือช่อง Sonnet ของแผน Qwen Cloud ไม่ใช่บัญชี DeepSeek แยกต่างหาก
- **% ของ Claude ถาม CLI ก่อนเสมอ** — `clilive.py` สปอว์น `claude -p --input-format stream-json` แล้วส่ง control request `get_usage` ซึ่งคืนก้อน usage ทั้งใบโดยไม่เรียกโมเดล (วัดจริง: total_cost_usd 0) CLI ถือ auth ของมันเอง เอนจินจึงไม่แตะ Keychain เลย · ได้คำตอบแล้วจบตรงนั้น ไม่ยิง endpoint ต่อ · **บัญชี default ต้องไม่ตั้ง `CLAUDE_CONFIG_DIR`** (เคสจริง 2026-09-24: ตั้งเป็น `~/.claude` ซึ่งเป็นค่าปริยายอยู่แล้ว CLI กลับไปหา keychain ชื่อที่ hash จาก path แทน `Claude Code-credentials` แล้วตอบ plan=None rows=0 เหมือนบัญชีที่ไม่ได้ล็อกอิน) · ตัวแยก "ยังไม่พร้อม" กับ "ว่างจริง" คือธง `rate_limits_available` ไม่ใช่จำนวนแถว — บัญชี Team ตอบ available=true พร้อม rows=0 ค้างเป็นนาทีได้ ถามซ้ำก็เท่าเดิม · แคช 180 วิต่อบัญชีใน `claude-live.json` นับจาก `triedAt` ไม่ใช่ `fetchedAt` (บัญชีที่ไม่ได้ล็อกอินตอบไม่ได้เสมอ ถ้านับจากครั้งที่สำเร็จจะถูกสปอว์นใหม่ทุกนาที ครั้งละ 3 วินาที) · `warm()` ถามทุกบัญชีพร้อมกันก่อนเข้าลูป — เรียงกันทีละบัญชีกินเวลา 21 วินาทีจากเพดาน 45
- ถ้า CLI ตอบไม่ได้หรือตอบว่าง ยังมีทางเดิมต่อท้าย: (1) `liveusage.py` ยิง endpoint เองด้วย token จาก Keychain (2) `cachedUsageUtilization` ซึ่งรีเฟรชเฉพาะตอนเปิด `/usage` หรือเริ่ม session ใหม่ — เก่าได้เป็นวัน และจะรายงาน "ไม่แน่ใจ" เมื่อหน้าต่างหมุนไป · ตัวใหม่สุดชนะ
- ใบรีเซ็ตลิมิตของ Claude อยู่ในก้อน usage ชื่อ `juniper_tide` (ใบเดียวต่อสัปดาห์ ใช้ผ่าน `/limit-reset` รีเซ็ตหน้าต่าง 5 ชม. แล้วไปกินโควตารายสัปดาห์) กับ `cedar_ember` (ใบเป็นใบๆ มีวันหมดอายุ แบบเดียวกับ Codex) · ทั้งคู่มี `eligible` — `false` แปลว่า **client นี้ไม่มีสิทธิ์รู้** (เคสจริง 2026-09-24: ineligible_reason "surface" ทั้งที่บัญชีมีสิทธิ์ใช้) ซึ่งต้องเป็น `None` ห้ามกลายเป็น 0 ที่อ่านว่า "ใช้หมดแล้ว" · server ส่งสองก้อนนี้มาเฉพาะเมื่อถูกขอ (`?at_wall=1` / `?cedar_ember=1`) ตอนถามเฉยๆ จะเป็น null · **พิสูจน์แล้วว่าแอปดึงมาไม่ได้จริงๆ** (2026-09-24): บัญชี work ชนเพดาน 100% จริง ยิงด้วย token ใบเดียวกับที่ CLI ใช้ พร้อม `?at_wall=1` ที่เป็นความจริงทุกประการ server ยังตอบ `eligible:false · surface` และ `at_limit:false` — มันไม่ได้ดูสิ่งที่เราบอก ตัดสินจาก header ที่บอกว่าเป็นโปรแกรมอะไร เท่านั้น · control request `get_usage` ของ CLI ไม่เคยแนบสองก้อนนี้มาด้วย และไม่รับพารามิเตอร์ (ส่ง at_wall/cedar_ember เข้าไปก็ยัง null) · **ห้ามปลอม header ให้ดูเหมือน Claude Code** — โค้ดฝั่งเราพร้อมแล้ว ถ้าวันไหน Anthropic เปิดให้ surface อื่นอ่านได้ ตัวเลขจะขึ้นเอง

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
