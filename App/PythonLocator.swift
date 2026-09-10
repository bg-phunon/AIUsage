import Foundation

/// หา python3 ที่รันได้จริง แทนการพึ่ง `/usr/bin/env`
///
/// แอปที่เปิดจาก Finder ได้ PATH สั้นกว่าเทอร์มินัลมาก (ไม่มี `/opt/homebrew/bin`)
/// `env python3` จึงไปลงเอยที่ `/usr/bin/python3` ซึ่งมีอยู่ทุกเครื่องแต่เป็น stub:
/// ถ้ายังไม่ได้ลง Command Line Tools มันจะเด้ง dialog ชวนโหลด ~1 GB แทนที่จะรัน
/// สคริปต์ — คนที่เพิ่ง `brew install --cask` มาจะเจอหน้าต่างนั้นเป็นอย่างแรก
///
/// รายการนี้จึงชี้ไปที่ interpreter ตัวจริงทุกตัว ไม่แตะ stub เลย เรียงตามลำดับที่
/// อยากได้: Homebrew ก่อน (cask ประกาศ depends_on ไว้ มันจะมีเสมอ และใหม่กว่า)
/// แล้วค่อยเป็น python 3.9 ที่มากับ developer tools สำหรับคนที่ build เอง
let pythonSearchPath = [
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/Library/Developer/CommandLineTools/usr/bin/python3",
    "/Applications/Xcode.app/Contents/Developer/usr/bin/python3",
]

/// ตัวแรกในรายการที่รันได้ — nil แปลว่าเครื่องนี้ไม่มี python3 ให้ใช้เลย
func findPython(candidates: [String] = pythonSearchPath,
                fm: FileManager = .default) -> String? {
    candidates.first { fm.isExecutableFile(atPath: $0) }
}
