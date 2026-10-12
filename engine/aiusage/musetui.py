"""% ของ Muse จากจอ TUI ของ Muse Code เอง — ไม่เรียกโมเดล ไม่เสียโควตา

Muse ไม่มีคำสั่งถามโควตา: `muse serve` มี `usage/read` ก็จริง แต่ host ใหม่ตอบว่าง
จนกว่าจะเรียกโมเดลหนึ่งครั้ง (วัดจริง 2026-10-12: 27,230 token ต่อการถาม) ส่วน TUI
ต่ออายุ credential ตอนเริ่ม ซึ่งพาเลข usage มาด้วย พิมพ์ `/upgrade` แล้วจอโชว์

    Current 20% used · Resets at 6:10 PM
    Weekly 6% used · Resets Oct 19 at 7:00 AM

โดย `/status` ยืนยัน 0 tokens · 0 turns · จึงเปิด TUI ใน pty อ่านจอแล้วออกด้วย `/exit`

ราคาที่จ่าย: ทุกครั้งที่ TUI เริ่ม มันเขียน `~/.config/muse/auth.json` ใหม่เอง (เอนจิน
ไม่อ่านไม่แตะไฟล์นั้น) จึงถามให้ห่าง — เฉพาะเมื่อมีการใช้ Muse ใหม่หลังครั้งก่อน และไม่ถี่
กว่า MIN_INTERVAL · ระหว่างนั้นเลขที่อ่านได้ถูกเก็บเป็นจุดรูปเดียวกับ `museAnchor`
ให้ `estimate_muse_pct` ประมาณต่อจาก token เอง

ไฟล์นี้ต้องรันเดี่ยวได้ (`python musetui.py --probe`) เพราะการถามกิน ~15 วินาที
เอนจินจึงปล่อยเป็น process แยกแล้วอ่านผลในรอบถัดไป — ห้าม import แบบ relative
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

MIN_INTERVAL = 900
MAX_POINTS = 30
SAME_WINDOW = 120  # วินาที — จอบอกเวลารีเซ็ตละเอียดแค่นาที
APP_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                       "AIUsage")
CACHE_PATH = os.path.join(APP_DIR, "muse-live.json")
# โฟลเดอร์ว่างของเราเอง — TUI โหลด skill/rule/hook ของ workspace ที่มันยืนอยู่
PROBE_DIR = os.path.join(APP_DIR, "muse-probe")
CLI_CANDIDATES = (os.path.join(os.path.expanduser("~"), ".local", "bin", "muse"),
                  "/opt/homebrew/bin/muse", "/usr/local/bin/muse")
MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"))}

_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[[0-9;?<>=]*[A-Za-z]")
_ESC = re.compile(r"\x1b[()=>][0-9A-Za-z]?")
_RESET = (r"Resets\s+(?:(?P<{p}mon>[A-Za-z]{{3}})[a-z]*\s+(?P<{p}day>\d{{1,2}})\s+)?"
          r"at\s+(?P<{p}h>\d{{1,2}}):(?P<{p}m>\d{{2}})\s*(?P<{p}ap>[AaPp][Mm])?")
_WINDOW = r"{label}\s+(?P<{p}pct>\d{{1,3}})%\s+used\s*·\s*" + _RESET
_CURRENT = re.compile(_WINDOW.format(label="Current", p="c"))
_WEEKLY = re.compile(_WINDOW.format(label="Weekly", p="w"))
_PLAN = re.compile(r"Muse\s+Code\s+(\w+)\s+Usage")


def strip_ansi(raw: str) -> str:
    """ลำดับควบคุมจอ → ขึ้นบรรทัดใหม่ (การย้ายเคอร์เซอร์คือสิ่งที่คั่นคำบนจอ)"""
    return _ESC.sub("", _CSI.sub("\n", _OSC.sub("", raw)))


def _reset_time(m, prefix, now):
    """เวลารีเซ็ตบนจอเป็นเวลาท้องถิ่น ไม่มีปี และหน้าต่าง 5 ชม. ไม่มีวันที่"""
    local = now.astimezone()
    hour, minute = int(m.group(prefix + "h")), int(m.group(prefix + "m"))
    ap = (m.group(prefix + "ap") or "").lower()
    if ap:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ap == "pm" else 0)
    if hour > 23 or minute > 59:
        return None
    mon = m.group(prefix + "mon")
    try:
        if mon is None:
            at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if at < local - timedelta(seconds=SAME_WINDOW):
                at += timedelta(days=1)
        else:
            month = MONTHS.get(mon.lower())
            if month is None:
                return None
            at = local.replace(month=month, day=int(m.group(prefix + "day")),
                               hour=hour, minute=minute, second=0, microsecond=0)
            if at < local - timedelta(days=1):
                at = at.replace(year=at.year + 1)  # ธ.ค. → ม.ค.
    except ValueError:
        return None
    return at.astimezone(timezone.utc)


def parse_screen(text: str, now: datetime):
    """จอ `/upgrade` → {"plan", "session": {usedPct, resetAt}, "weekly": {...}}

    อ่านได้ช่องเดียวก็คืนช่องนั้น · ไม่เจอเลย = None (จอยังไม่ขึ้น หรือ Muse เปลี่ยน
    ข้อความ — ผู้เรียกถอยไปใช้จุดที่จดมือ ห้ามเดา)
    """
    out = {}
    for key, rx, prefix in (("session", _CURRENT, "c"), ("weekly", _WEEKLY, "w")):
        found = None
        for found in rx.finditer(text):
            pass  # จอวาดซ้ำได้หลายรอบ — เอารอบล่าสุด
        if found is None:
            continue
        reset = _reset_time(found, prefix, now)
        if reset is not None:
            out[key] = {"usedPct": int(found.group(prefix + "pct")), "resetAt": reset}
    if not out:
        return None
    plan = _PLAN.search(text)
    out["plan"] = plan.group(1).lower() if plan else None
    return out


def _ts(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def merge_anchor(old, reading, at: datetime) -> dict:
    """เติมเลขที่เพิ่งอ่านเป็นจุดใหม่ ในรูปเดียวกับ config `museAnchor`

    เวลารีเซ็ตเปลี่ยน = หน้าต่างใหม่ ทิ้งจุดเก่าทั้งหมด (กฎเดียวกับตอนจดมือ)
    """
    old = old if isinstance(old, dict) else {}
    plan = reading.get("plan") or old.get("plan") or "everyday"
    out = {"at": _iso(at), "plan": plan}
    for key in ("session", "weekly"):
        new, prev = reading.get(key), old.get(key)
        if new is None:
            # ช่องนี้อ่านไม่ออกรอบนี้ — ของเก่ายังใช้ได้จนกว่าจะรีเซ็ต
            if isinstance(prev, dict):
                out[key] = prev
            continue
        points, reset = [], new["resetAt"]
        if isinstance(prev, dict):
            prev_reset = _ts(prev.get("resetAt"))
            if (prev_reset is not None
                    and abs((prev_reset - reset).total_seconds()) <= SAME_WINDOW):
                reset = prev_reset
                points = [p for p in prev.get("points") or [] if isinstance(p, dict)]
        points.append({"usedPct": new["usedPct"], "at": _iso(at), "plan": plan})
        # จุดแรกคือฐานวัดอัตรา %/token — ตัดจากตรงกลาง ไม่ตัดหัว
        if len(points) > MAX_POINTS:
            points = points[:1] + points[-(MAX_POINTS - 1):]
        out[key] = {"resetAt": _iso(reset), "points": points}
    return out


def newer_anchor(config_anchor, live):
    """จุดจดมือกับจุดที่อ่านจากจอ — ตัวที่ `at` ใหม่กว่าชนะ"""
    live_at = _ts((live or {}).get("at")) if isinstance(live, dict) else None
    if live_at is None:
        return config_anchor
    cfg_at = _ts(config_anchor.get("at")) if isinstance(config_anchor, dict) else None
    return live if cfg_at is None or live_at >= cfg_at else config_anchor


def due(entry, latest_activity_ts, now_ts: float) -> bool:
    """ถึงเวลาถามหรือยัง — ต้องมีการใช้ Muse ใหม่หลังครั้งก่อน และห่างพอ

    นับจาก triedAt ไม่ใช่ fetchedAt (กฎเดียวกับ clilive): ถ้าจออ่านไม่ออกเพราะ Muse
    เปลี่ยนข้อความ จะไม่เปิด TUI ซ้ำทุก 60 วินาที
    """
    if latest_activity_ts is None:
        return False
    tried = (entry or {}).get("triedAt") or 0
    return now_ts - tried >= MIN_INTERVAL and latest_activity_ts > tried


def _read_store(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_store(path: str, store: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(store, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def live_anchor(path=None):
    """จุดล่าสุดที่อ่านจากจอ ในรูป `museAnchor` · None = ยังไม่เคยอ่านได้"""
    anchor = _read_store(path or CACHE_PATH).get("anchor")
    return anchor if isinstance(anchor, dict) else None


def _cli_bin():
    """แอปที่เปิดจาก Finder มี PATH สั้น — หาจากที่อยู่จริงก่อน which"""
    for candidate in CLI_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("muse")


def fetch_from_tui(timeout: float = 30.0, binary=None, now=None):
    """เปิด TUI ใน pty พิมพ์ `/upgrade` อ่านจอ แล้วออกด้วย `/exit` — ล้มคืน None

    ห้ามส่งข้อความอื่นเข้าไปเด็ดขาด: อะไรที่ไม่ขึ้นต้นด้วย `/` คือ prompt ที่เรียกโมเดล
    """
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios

    binary = binary or _cli_bin()
    if not binary:
        return None
    try:
        os.makedirs(PROBE_DIR, exist_ok=True)
        pid, fd = pty.fork()
    except OSError:
        return None
    if pid == 0:
        try:
            os.chdir(PROBE_DIR)
            os.environ["TERM"] = "xterm-256color"
            # launcher อัปเดตตัวเองตอนเปิด — การถามโควตาไม่ควรเปลี่ยนเวอร์ชัน Muse
            os.environ["MUSE_NO_AUTO_UPDATE"] = "1"
            # --trust-workspace ไม่บันทึก trust · ไม่ใส่จะติดหน้าถาม trust แล้ว Enter
            # ของเราไปกด "Trust and continue" ลง trust.json ของผู้ใช้
            os.execv(binary, [binary, "--no-session-log", "--disable-shell",
                              "--disable-write", "--trust-workspace"])
        finally:
            os._exit(127)
    end = time.time() + timeout
    raw = b""

    def pump(seconds, until=None):
        """อ่านจอ seconds วินาที · until คืนค่าจริงเมื่อไรก็หยุด · เงียบ 1.5 วิก็หยุด"""
        nonlocal raw
        stop = min(end, time.time() + seconds)
        quiet = time.time()
        while time.time() < stop:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                if until is None and len(raw) and time.time() - quiet > 1.5:
                    return None
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return None
            if not chunk:
                return None
            quiet = time.time()
            raw += chunk
            if b"\x1b[6n" in chunk:  # TUI ถามตำแหน่งเคอร์เซอร์ ไม่ตอบมันรอ
                os.write(fd, b"\x1b[1;1R")
            if until is not None:
                got = until()
                if got:
                    return got
        return None

    def type_line(text):
        for ch in text:
            os.write(fd, ch.encode())
            time.sleep(0.03)
        pump(0.6, until=lambda: False)
        os.write(fd, b"\r")

    def read_screen():
        got = parse_screen(strip_ansi(raw.decode("utf-8", "replace")),
                           now or datetime.now(timezone.utc))
        return got if got and "session" in got and "weekly" in got else None

    result = None
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
        pump(3, until=lambda: False)  # ต่ออายุ credential + โหลด skill ก่อนรับคีย์
        pump(9)
        raw = b""
        type_line("/upgrade")
        result = pump(8, until=read_screen)
        if result is None:
            result = parse_screen(strip_ansi(raw.decode("utf-8", "replace")),
                                  now or datetime.now(timezone.utc))
        os.write(fd, b"\x1b")
        pump(0.5, until=lambda: False)
        type_line("/exit")
    except OSError:
        pass
    finally:
        # ให้ Muse ปิดเอง — kill กลางทางตอนมันเขียน auth.json = เสี่ยงบัญชีหลุด
        for sig, wait in ((None, 6.0), (signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
            if sig is not None:
                try:
                    os.kill(pid, sig)
                except OSError:
                    break
            stop = time.time() + wait
            done = False
            while time.time() < stop:
                try:
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        done = True
                        break
                except OSError:
                    done = True
                    break
                try:
                    if select.select([fd], [], [], 0.1)[0]:
                        os.read(fd, 65536)
                except OSError:
                    pass
            if done:
                break
        try:
            os.close(fd)
        except OSError:
            pass
    return result


def probe(path=None, fetch=None, clock=time.time) -> bool:
    """ถามหนึ่งครั้งแล้วเก็บผลลงแคช — คืนว่าอ่านเลขได้ไหม"""
    path = path or CACHE_PATH
    reading = (fetch or fetch_from_tui)()
    store = _read_store(path)
    store["triedAt"] = store.get("triedAt") or clock()
    if reading is not None:
        now = clock()
        store["fetchedAt"] = now
        store["anchor"] = merge_anchor(store.get("anchor"), reading,
                                       datetime.fromtimestamp(now, timezone.utc))
    _write_store(path, store)
    return reading is not None


def kick(latest_activity_ts, path=None, clock=time.time, spawn=None) -> bool:
    """ถึงเวลาก็ปล่อย process แยกไปถาม — ไม่รอผล เอนจินอ่านแคชรอบถัดไป

    จด triedAt ก่อนสปอว์น: process ลูกอยู่ได้นานกว่ารอบ 60 วินาทีของเอนจิน
    ถ้ารอให้ลูกจดเอง รอบถัดไปจะเปิด TUI ซ้อนอีกตัว
    """
    path = path or CACHE_PATH
    store = _read_store(path)
    if not due(store, latest_activity_ts, clock()):
        return False
    store["triedAt"] = clock()
    _write_store(path, store)
    (spawn or _spawn_probe)(path)
    return True


def _spawn_probe(path: str) -> None:
    try:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--probe", path],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True,
                         cwd=os.path.expanduser("~"))
    except OSError:
        pass


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--probe":
        sys.exit(0 if probe(sys.argv[2] if len(sys.argv) > 2 else None) else 1)
    sys.exit(2)
