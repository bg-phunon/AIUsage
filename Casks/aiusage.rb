cask "aiusage" do
  version "0.0.0"
  # ค่าจริงถูกเขียนทับโดย .github/workflows/release.yml ตอนออกรุ่น
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"

  url "https://github.com/bg-phunon/AIUsage/releases/download/v#{version}/AIUsage.zip"
  name "AI Usage"
  desc "Menu bar quota meter for Claude Code, Codex and other AI coding plans"
  homepage "https://github.com/bg-phunon/AIUsage"

  depends_on macos: :sonoma
  # เอนจินเป็น python stdlib ล้วน แต่ต้องมี interpreter จริง — /usr/bin/python3
  # ของ macOS เป็นแค่ stub ที่เด้ง dialog ชวนลง Command Line Tools ~1 GB
  depends_on formula: "python@3.13"

  app "AIUsage.app"

  uninstall quit: "com.local.aiusage"

  zap trash: [
    "~/.config/ai-usage",
    "~/Library/Application Support/AIUsage",
    "~/Library/Preferences/com.local.aiusage.plist",
  ]

  # แอปเซ็นแบบ ad-hoc ไม่ได้ notarize (โปรเจกต์ไม่มี Apple Developer Program)
  # ต้องลงด้วย --no-quarantine ไม่งั้น Gatekeeper บล็อกตั้งแต่เปิดครั้งแรก
  # cask ไม่ถอด quarantine ให้เอง — การปลดเกราะของระบบควรเป็นสิ่งที่ผู้ใช้สั่งเอง
  caveats <<~CAVEATS
    ลงด้วย: brew install --cask --no-quarantine aiusage
    ถ้าลงไปแล้วเปิดไม่ขึ้น: xattr -dr com.apple.quarantine /Applications/AIUsage.app
  CAVEATS
end
