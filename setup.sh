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

# ผลการติดตั้งครั้งล่าสุด — แอปที่รันอยู่อ่านเพื่อรายงานว่า "รอบที่สั่งไปล้ม"
# สำเร็จหรือล้มก็เขียนทั้งคู่ เงียบหายคือไม่มีใครรู้
note_result() {
  python3 - "$1" <<'PYEOF' 2>/dev/null || true
import json, os, sys, time
path = os.path.expanduser("~/.config/ai-usage/last-update.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump({"at": int(time.time()), "ok": sys.argv[1] == "ok"}, fh)
os.replace(tmp, path)
PYEOF
}
# ตาข่ายกันพลาด — คำสั่งที่ล้มนอกเหนือสาขาที่ดักไว้ข้างล่าง (cp พัง, python พัง)
# ต้องทิ้งร่องรอยไว้ ไม่ใช่ตายเงียบแล้วแอปเก่านั่งรอผลที่ไม่มา
trap 'note_result fail' ERR

echo "▸ 1/4 ตรวจเครื่องมือ"
command -v xcodegen >/dev/null 2>&1 || { echo "  ต้องมี xcodegen"; note_result fail; exit 1; }
command -v xcodebuild >/dev/null 2>&1 || { echo "  ต้องมี Xcode ก่อน"; note_result fail; exit 1; }

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
  build > /tmp/aiusage-build.log 2>&1 || { tail -30 /tmp/aiusage-build.log; note_result fail; exit 1; }

APP="$ROOT/build/Build/Products/Release/${APP_NAME}.app"
[ -d "$APP" ] || { echo "  build ไม่ได้ .app — ดู /tmp/aiusage-build.log"; note_result fail; exit 1; }

# ad-hoc sign — SMAppService (เปิดเองตอนเข้าระบบ) ปฏิเสธแอปที่ไม่มีลายเซ็นเลย
codesign --force --deep -s - "$APP" 2>/dev/null || echo "  (เซ็น ad-hoc ไม่ได้ — login item อาจใช้ไม่ได้)"

echo "▸ 4/4 ติดตั้ง"
quit_app
rm -rf "$INSTALLED"
cp -R "$APP" /Applications/

# แอปใน /Applications ไม่รู้ว่าโค้ดอยู่โฟลเดอร์ไหน — ทิ้งที่อยู่กับเวลาไว้ให้เมนู
# "ติดตั้งอัปเดต" เทียบว่าไฟล์ในโปรเจกต์ใหม่กว่าตัวที่ติดตั้งแล้วหรือยัง
python3 - "$ROOT" "$VERSION" "$BUILD_NUM" <<'PYEOF'
import json, os, sys, time
root, version, build = sys.argv[1], sys.argv[2], sys.argv[3]
path = os.path.expanduser("~/.config/ai-usage/install.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump({"repo": root, "installedAt": int(time.time()),
               "version": version, "build": int(build)}, fh)
os.replace(tmp, path)
PYEOF

# พาขอสิทธิ์ Keychain ต่อบัญชี — engine อ่าน token ด้วย /usr/bin/security
# ถ้าไม่เคยกด "Always Allow" มันจะเด้งถามทุก 60 วิแล้วโดน timeout ฆ่าเงียบๆ
# ทำตรงนี้ทีเดียวให้จบ: เรียกแบบ foreground ค้างรอจนผู้ใช้ตอบครบทุกบัญชี
SERVICES=$(python3 -c "
import json, os, sys
sys.path.insert(0, os.path.join('$ROOT', 'engine'))
from aiusage.liveusage import keychain_service
try:
    cfg = json.load(open(os.path.expanduser('~/.config/ai-usage/config.json')))
except Exception:
    cfg = {}
seen = []
for acc in cfg.get('claude', []):
    if acc.get('enabled', True):
        svc = keychain_service(acc['dir'])
        if svc not in seen:
            seen.append(svc)
print('\n'.join(seen))
" 2>/dev/null || true)
if [ -n "$SERVICES" ]; then
  echo "▸ ขอสิทธิ์ Keychain — ถ้ามีหน้าต่างเด้งถาม ให้กด \"Always Allow\" (อนุญาตเสมอ)"
  while IFS= read -r svc; do
    [ -n "$svc" ] || continue
    if security find-generic-password -s "$svc" -w >/dev/null 2>&1; then
      echo "  ✓ ${svc}"
    else
      echo "  ✗ ${svc} — ไม่ได้สิทธิ์หรือไม่มี token (บัญชีนั้นจะใช้แคชแทน % สด)"
    fi
  done <<< "$SERVICES"
fi

open "$INSTALLED"

echo -n "  รอ snapshot ใหม่"
BEFORE=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('$SNAPSHOT')))['generated'])" 2>/dev/null || echo "")
for _ in $(seq 1 18); do
  sleep 5; echo -n "."
  NOW=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('$SNAPSHOT')))['generated'])" 2>/dev/null || echo "")
  if [ -n "$NOW" ] && [ "$NOW" != "$BEFORE" ]; then
    echo
    echo "เสร็จแล้ว — $VERSION ทำงานอยู่บน menu bar"
    note_result ok
    exit 0
  fi
done
echo
echo "แอปติดตั้งแล้วแต่ยังไม่เขียน snapshot ภายใน 90 วินาที"
echo "ตรวจด้วย: log stream --predicate 'process == \"AIUsage\"' --level error"
note_result fail
exit 1
