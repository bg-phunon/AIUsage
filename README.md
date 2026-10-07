# AI Usage

แอป menu bar สำหรับ macOS ที่บอกว่าโควตา AI ของคุณเหลือเท่าไหร่ — แยกตามบัญชีและตามถัง endpoint
อ่านจาก log ในเครื่องเป็นหลัก ไม่กินโควตาโมเดล

รองรับ Claude Code (หลายบัญชีผ่าน [ccs](https://github.com/bg-phunon)), Codex, Muse, Qwen Cloud, GLM
และตัวนับแบบกรอกเองสำหรับบริการที่ไม่มีตัวเลขให้อ่าน (Muse ไม่มีโควตาให้แสดง มีแต่ยอด token)

## ติดตั้ง

```bash
brew tap bg-phunon/aiusage https://github.com/bg-phunon/AIUsage
brew install --cask --no-quarantine aiusage
```

ต้องมี `--no-quarantine` เพราะแอปเซ็นแบบ ad-hoc ไม่ได้ผ่าน notarization ของ Apple
(โปรเจกต์ไม่มี Apple Developer Program) ถ้าลงไปแล้วเปิดไม่ขึ้น:

```bash
xattr -dr com.apple.quarantine /Applications/AIUsage.app
```

อัปเดตด้วย `brew upgrade --cask aiusage` — แอปรู้ว่าตัวเองมาจาก brew และจะไม่เสนอ build ทับตัวเอง

### ต้องมีอะไรบ้าง

- macOS 14 (Sonoma) ขึ้นไป
- python3 — cask ลงให้เอง สำคัญตรงที่ `/usr/bin/python3` ของ macOS เป็นแค่ stub
  ที่เด้ง dialog ชวนลง Command Line Tools ~1 GB แอปจึงมองหา interpreter ตัวจริงตามลำดับ
  Homebrew → `/usr/local` → developer tools

## แอปอ่านอะไรบ้าง

| อ่านจาก | เอาไปทำอะไร |
|---|---|
| `~/.claude`, `~/.ccs/instances/*` | log การใช้งาน Claude Code ต่อบัญชี |
| `~/.codex/sessions/**/*.jsonl` | `rate_limits` ที่ Codex เขียนเป็น % จริงลง rollout log |
| `~/.local/share/muse/sessions/**` | `model_completed` ของ Muse — มีแต่ยอด token ไม่มี % |
| `~/.config/ai-usage/config.json` | ตั้งค่าของเอนจิน สร้างเองอัตโนมัติครั้งแรก |

ทั้งหมดเป็นไฟล์ในเครื่อง ไม่มีอะไรถูกส่งออก

### ข้อยกเว้น: % ทางการจาก Anthropic (ต้องเปิดเอง)

ในหน้าตั้งค่ามีสวิตช์ **"ถาม % ทางการจาก Anthropic"** ซึ่ง **ปิดไว้เป็นค่าเริ่มต้น** เปิดแล้วเอนจินจะ

1. อ่าน OAuth token ของ Claude Code จาก Keychain (`/usr/bin/security`)
2. ยิงไปที่ `api.anthropic.com` / `console.anthropic.com` เท่านั้น เพื่อขอเลข utilization
3. ถ้า token หมดอายุจะต่ออายุ แล้วเขียนตัวใหม่กลับลง Keychain item เดิม
   (ขั้นนี้จำเป็น เพราะ refresh token ถูก rotate — เก็บตัวใหม่ไม่ได้เท่ากับหลุดจากบัญชี)

token ไม่ถูก log ไม่ถูกเขียนลงไฟล์อื่น และไม่ถูกส่งไป host อื่นเด็ดขาด
โค้ดทั้งหมดอยู่ใน [`engine/aiusage/liveusage.py`](engine/aiusage/liveusage.py) ไฟล์เดียว

ไม่เปิดก็ยังใช้งานได้ปกติ — % จะมาจากแคชที่ Claude Code เขียนเองแทน

## build เอง

```bash
brew install xcodegen
git clone https://github.com/bg-phunon/AIUsage
cd AIUsage
./setup.sh          # xcodegen + xcodebuild + ติดตั้งลง /Applications
```

`setup.sh` รันซ้ำได้ และจะทิ้งที่อยู่ repo ไว้ให้แอปเสนอ "ติดตั้งอัปเดต" เมื่อโค้ดในโปรเจกต์ใหม่กว่า
ถอนด้วย `./setup.sh --uninstall`

## สถาปัตยกรรม

```
ai-usage.60s.py --snapshot          แอปเรียกเองทุก 60 วินาที
        │                            พาร์ส log แล้วสรุปเป็น JSON
        ▼
~/Library/Application Support/AIUsage/snapshot.json
        │
        ▼
AIUsage.app (SwiftUI + NSStatusItem)  อ่านอย่างเดียว
```

ข้อมูลไหลทางเดียว — Python เขียน Swift อ่าน ตัวเลือกส่วนตัว (ปักหมุด/ซ่อน/ราคา) อยู่ใน
UserDefaults ฝั่งแอป ไม่ปนกับ snapshot

## พัฒนาต่อ

```bash
python3 -m unittest discover -s engine/tests
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -destination 'platform=macOS' test
```

## License

MIT — ดู [LICENSE](LICENSE)

โลโก้ผู้ให้บริการมาจาก simple-icons (CC0) และ lobe-icons (MIT) รายละเอียดใน
[`Assets/Logos/NOTICE.md`](Assets/Logos/NOTICE.md) เครื่องหมายการค้าทั้งหมดเป็นของเจ้าของ
โปรเจกต์นี้ไม่มีความเกี่ยวข้องกับ Anthropic, OpenAI, Meta หรือ Alibaba
