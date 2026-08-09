# AI Usage — macOS desktop / Notification Center widget

โควตา AI แยกตามบัญชี วางบน desktop หรือ Notification Center ได้

## สถาปัตยกรรม

```
ai-usage.60s.py --snapshot        launchd รันทุก 60 วิ
        │                          อ่าน ~/.claude, ~/.ccs/instances/*, ~/.codex
        ▼
~/Library/Application Support/AIUsage/snapshot.json
        │
        ▼
AIUsageWidget (WidgetKit)          อ่านไฟล์ วาด ring + แถบ
```

สคริปต์ Python ทำงานหนักทั้งหมด widget แค่อ่าน JSON ไฟล์เดียว จึงเบาและไม่ชนขีดจำกัดเวลาของ widget extension

## 1. ตั้ง launchd ให้เขียน snapshot

```bash
mkdir -p ~/SwiftBarPlugins
cp ai-usage.60s.py ~/SwiftBarPlugins/
chmod +x ~/SwiftBarPlugins/ai-usage.60s.py
python3 ~/SwiftBarPlugins/ai-usage.60s.py --snapshot   # ทดสอบว่าอ่านบัญชีเจอ

sed "s|REPLACE_WITH_HOME|$HOME|g" launchd/com.aiusage.snapshot.plist \
  > ~/Library/LaunchAgents/com.aiusage.snapshot.plist
launchctl load ~/Library/LaunchAgents/com.aiusage.snapshot.plist
```

ตรวจว่าไฟล์เกิดแล้ว:

```bash
cat ~/Library/Application\ Support/AIUsage/snapshot.json | head
```

ถ้าไม่ขึ้น ดู `/tmp/aiusage.err.log`

## 2. สร้างโปรเจกต์ใน Xcode

1. Xcode → New Project → macOS → App
   - Product Name: `AIUsage`
   - Interface: SwiftUI · Language: Swift
2. ลบ `ContentView.swift` และ `AIUsageApp.swift` ที่ Xcode สร้างมา แล้วลาก `App/AIUsageApp.swift` กับ `Shared/UsageSnapshot.swift` เข้าไปแทน
3. File → New → Target → **Widget Extension**
   - ชื่อ `AIUsageWidget`
   - เอาติ๊ก "Include Configuration Intent" ออก
4. ลบไฟล์ตัวอย่างใน target widget แล้วลาก `Widget/AIUsageWidget.swift` เข้าไป
5. เลือก `Shared/UsageSnapshot.swift` → Inspector ขวา → Target Membership ติ๊ก **ทั้งสอง** target

## 3. ปิด App Sandbox (สำคัญ)

widget extension ที่ยัง sandbox อยู่จะอ่าน home จริงไม่ได้ และจะเห็นเป็น "ยังไม่มี snapshot" ตลอด

ทำกับ **ทั้งสอง** target: Signing & Capabilities → กด × ที่การ์ด **App Sandbox**

ถ้ายังไม่มีการ์ดนั้นก็ข้ามได้

## 4. Build แล้ววาง widget

- Signing → Team เลือก Apple ID ของคุณ (บัญชีฟรีใช้ได้)
- Cmd+R เพื่อ run — หน้าต่างแอปจะขึ้นและควรเห็นรายการบัญชี กดปิดได้เลย
- คลิกขวาที่ desktop → Edit Widgets → หา "โควตา AI" → ลากวางขนาดที่ชอบ

ขนาดที่รองรับ: เล็ก (ring บัญชีที่ใกล้เต็มที่สุด), กลาง (3 บัญชีแรก), ใหญ่ (ทุกบัญชีแยกกลุ่ม)

## ข้อจำกัดที่ต้องรู้

**widget รีเฟรชตามใจระบบ** macOS จำกัดจำนวนครั้งที่ widget โหลดข้อมูลใหม่ต่อวัน ปกติได้ราวไม่กี่ครั้งต่อชั่วโมง ไม่ใช่ทุกนาทีแบบ menu bar ตัว provider เลยเตรียม entry ล่วงหน้าทุก 5 นาทีเป็นเวลา 1 ชั่วโมง เพื่อให้ **นาฬิกานับถอยหลังเดินถูกต้องเสมอ** ส่วน % จะค้างอยู่ที่ค่าล่าสุดที่ระบบยอมโหลด — ถ้าหัวเรื่องขึ้นว่า "ข้อมูลค้าง" แปลว่าเกิน 10 นาทีแล้ว

ถ้าต้องการตัวเลขสดทุกนาทีจริง ๆ menu bar คือทางเดียว — ใช้คู่กันได้ ทั้งสองอ่านจากสคริปต์ตัวเดียวกัน

**% ของ Claude ต้องตั้ง budget เอง** ใส่ `budget5h` และ `budgetWeek` ใน `~/.config/ai-usage/config.json` ไม่งั้นจะโชว์เป็นจำนวน token แทน (Codex ได้ % จริงจาก log อยู่แล้ว)
