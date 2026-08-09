#!/bin/bash
# ติดตั้งหรืออัปเดต AI Usage menu bar app — รันซ้ำได้
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$PWD"
APP_NAME="AIUsage"
INSTALLED="/Applications/${APP_NAME}.app"
SNAPSHOT="$HOME/Library/Application Support/AIUsage/snapshot.json"

quit_app() {
  osascript -e "quit app \"${APP_NAME}\"" >/dev/null 2>&1 || true
  for _ in $(seq 1 10); do
    pgrep -f "${APP_NAME}.app/Contents/MacOS" >/dev/null || return 0
    sleep 0.5
  done
  pkill -f "${APP_NAME}.app/Contents/MacOS" >/dev/null 2>&1 || true
  sleep 1
}

if [ "${1:-}" = "--uninstall" ]; then
  echo "▸ ถอนการติดตั้ง"
  quit_app
  launchctl bootout "gui/$(id -u)/com.aiusage.snapshot" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/com.aiusage.snapshot.plist"
  rm -rf "$INSTALLED"
  echo "  ลบแอปและ launchd job แล้ว"
  echo "  ข้อมูลยังอยู่ที่ ~/Library/Application Support/AIUsage/"
  exit 0
fi

echo "▸ 1/4 ตรวจเครื่องมือ"
command -v xcodegen >/dev/null 2>&1 || { echo "  ต้องมี xcodegen"; exit 1; }
command -v xcodebuild >/dev/null 2>&1 || { echo "  ต้องมี Xcode ก่อน"; exit 1; }

echo "▸ 2/4 ตั้งเวอร์ชันจาก git"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BUILD_NUM=$(git rev-list --count HEAD)
  VERSION=$(git describe --tags --always 2>/dev/null || echo "dev")
else
  BUILD_NUM=0
  VERSION=dev
fi
echo "  $VERSION ($BUILD_NUM)"

echo "▸ 3/4 build"
xcodegen generate
xcodebuild -project AIUsage.xcodeproj -scheme AIUsage -configuration Release \
  -derivedDataPath build MARKETING_VERSION="$VERSION" CURRENT_PROJECT_VERSION="$BUILD_NUM" \
  CODE_SIGN_IDENTITY="-" CODE_SIGNING_REQUIRED=NO CODE_SIGNING_ALLOWED=NO \
  build > /tmp/aiusage-build.log 2>&1 || { tail -30 /tmp/aiusage-build.log; exit 1; }

APP="$ROOT/build/Build/Products/Release/${APP_NAME}.app"
[ -d "$APP" ] || { echo "  build ไม่ได้ .app — ดู /tmp/aiusage-build.log"; exit 1; }

echo "▸ 4/4 ติดตั้ง"
quit_app
rm -rf "$INSTALLED"
cp -R "$APP" /Applications/
open "$INSTALLED"

echo -n "  รอ snapshot ใหม่"
BEFORE=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('$SNAPSHOT')))['generated'])" 2>/dev/null || echo "")
for _ in $(seq 1 18); do
  sleep 5; echo -n "."
  NOW=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('$SNAPSHOT')))['generated'])" 2>/dev/null || echo "")
  if [ -n "$NOW" ] && [ "$NOW" != "$BEFORE" ]; then
    echo
    echo "เสร็จแล้ว — $VERSION ทำงานอยู่บน menu bar"
    exit 0
  fi
done
echo
echo "แอปติดตั้งแล้วแต่ยังไม่เขียน snapshot ภายใน 90 วินาที"
echo "ตรวจด้วย: log stream --predicate 'process == \"AIUsage\"' --level error"
exit 1
