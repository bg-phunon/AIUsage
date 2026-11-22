"""% ของ Antigravity จากจอ `/usage` ของ Antigravity CLI (`agy`) — ไม่เรียกโมเดล

Google ไม่มี API สาธารณะสำหรับโควตา ทางที่เหลือคือ (1) ยิง `GetUserStatus` ของ
language server ในเครื่อง ซึ่งต้องขโมย CSRF token จาก command line ของ process
(แตะ credential) หรือ (2) ล็อกอินด้วย OAuth client ของ Antigravity เอง ซึ่งผิด ToS
ทั้งคู่ห้ามทำ ส่วน CLI ล็อกอินเองผ่าน keyring แล้วดึงโควตามาเองตอนเริ่ม พิมพ์
`/usage` แล้วจอ "Models & Quota" โชว์ (วัดจริง 2026-11-22, agy 1.5.14)

    GEMINI MODELS
      Weekly Limit Remaining
        [████░] 99.65%
        Refreshes in 167h 56m
      Five Hour Limit Remaining
        [████░] 98.76%
        Refreshes in 4h 56m
    CLAUDE AND GPT MODELS
      Weekly Limit Remaining ... 100.00% · Quota available
    GEMINI 4 ARGON
      Gemini 4 Argon Weekly Limit ... 100.00% · Quota available

ตัวเลขบนจอคือ **ที่เหลือ** ต้องกลับเป็นที่ใช้ไป · "Quota available" = หน้าต่างยังไม่เริ่ม
นับ ไม่มีเวลารีเซ็ต · โมเดลในกลุ่มเดียวกันใช้โควตาร่วมกัน

ราคาที่จ่าย: เปิด CLI แต่ละครั้งมันเขียน state/DB/แคช MCP ใต้ `~/.gemini/` หลายสิบไฟล์
และอาจอัปเดตตัวเอง จึงถามให้ห่างแบบ musetui — เฉพาะเมื่อมีการใช้ Antigravity ใหม่
หลังรอบก่อนจบ และไม่ถี่กว่า MIN_INTERVAL

trust: agy ไม่มี flag ข้ามหน้าถาม trust และ trust ไม่สืบทอดลงโฟลเดอร์ลูก เรากด Enter
ให้เฉพาะเมื่อ path บนจอคือ PROBE_DIR ของเราเอง (โฟลเดอร์ว่าง) — path อื่นคือหยุด

ไฟล์นี้ต้องรันเดี่ยวได้ (`python agytui.py --probe`) — ห้าม import แบบ relative
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
# จอสูงพอให้ "Models & Quota" ทั้ง 38 บรรทัดอยู่ในหน้าเดียว — การเลื่อนทำให้ TUI วาดแค่
# ส่วนที่เปลี่ยนแบบไม่เรียงบรรทัด ช่องของกลุ่มหนึ่งไปตกในอีกกลุ่ม (เคสจริงตอนทดสอบ)
ROWS = 120
# ไฟล์ที่การถามของเราเองแตะ (conversation/history ของ CLI) ต้องไม่นับเป็นการใช้งาน
# — ทุกอย่างที่ mtime อยู่ไม่เกินนี้หลัง triedAt ถือเป็นร่องรอยของ probe
PROBE_GRACE = 120
APP_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                       "AIUsage")
CACHE_PATH = os.path.join(APP_DIR, "agy-live.json")
PROBE_DIR = os.path.join(APP_DIR, "agy-probe")
GEMINI_DIR = os.path.join(os.path.expanduser("~"), ".gemini")
CLI_CANDIDATES = (os.path.join(os.path.expanduser("~"), ".local", "bin", "agy"),
                  os.path.join(os.path.expanduser("~"), ".antigravity", "antigravity",
                               "bin", "agy"),
                  "/opt/homebrew/bin/agy", "/usr/local/bin/agy")
# ร่องรอยการใช้งานจริง: บทสนทนาของ IDE และของ CLI
ACTIVITY_DIRS = (("antigravity", "conversations"), ("antigravity", "brain"),
                 ("antigravity-cli", "conversations"), ("antigravity-cli", "brain"))

_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_CSI = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]")
_ESC = re.compile(r"\x1b[()=>][0-9A-Za-z]?")
_HEADING = re.compile(r"^\s*([A-Z][A-Z0-9]*(?:\s+[A-Z0-9&]+)+)\s*$")
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_REFRESH = re.compile(r"Refreshes\s+in\s+((?:\d+\s*[dhm]\s*)+)", re.I)
_UNIT = re.compile(r"(\d+)\s*([dhm])", re.I)
_PLAN = re.compile(r"\(Google\s+(AI\s+[A-Za-z]+)\)")


def strip_ansi(raw: str) -> str:
    """ลำดับควบคุมจอ → ขึ้นบรรทัดใหม่ (การย้ายเคอร์เซอร์คือสิ่งที่คั่นคำบนจอ)"""
    return _ESC.sub("", _CSI.sub("\n", _OSC.sub("", raw))).replace("\r", "\n")


_LINES = re.compile(r"\d+\s*[–-]\s*\d+\s+of\s+\d+\s+lines")


def last_frame(text: str) -> str:
    """ตั้งแต่ "Models & Quota" ครั้งสุดท้าย — วาดซ้ำแต่ละรอบไม่ปนกัน

    บรรทัดหัวที่มีชื่อแผน "(Google AI Pro)" อยู่ก่อนหน้านั้น จึงต่อท้ายให้ parser เห็นด้วย
    """
    at = text.rfind("Models & Quota")
    if at < 0:
        return text
    plan = None
    for plan in _PLAN.finditer(text[:at]):
        pass
    return text[at:] + ("\n" + plan.group(0) if plan else "")


def group_label(heading: str) -> str:
    """หัวกลุ่มบนจอ → ป้ายสั้นที่ใส่แถบได้"""
    words = heading.split()
    if "CLAUDE" in words:
        return "Claude"
    if "ARGON" in words:
        return "Argon"
    if words[0] == "GEMINI":
        return "Gemini"
    return words[0].capitalize()


def _duration(text: str):
    secs = 0
    for n, unit in _UNIT.findall(text):
        secs += int(n) * {"d": 86400, "h": 3600, "m": 60}[unit.lower()]
    return secs


def parse_screen(text: str, now: datetime):
    """จอ `/usage` → {"plan", "groups": [{"label", "session", "weekly"}]}

    session/weekly = {"usedPct", "resetAt"} (resetAt None = "Quota available")
    จอวาดซ้ำและเลื่อนได้หลายรอบ — ค่าที่เห็นทีหลังทับค่าเดิมของกลุ่มเดียวกัน
    ไม่เจออะไรเลย = None (ผู้เรียกห้ามเดา)
    """
    groups = {}
    order = []
    section = kind = None
    pending = None  # (section, kind) ที่เห็น % แล้ว รอบรรทัด Refreshes/Quota available
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        head = _HEADING.match(line)
        if head and "%" not in stripped and "LIMIT" not in stripped.upper().split():
            section, kind, pending = group_label(head.group(1)), None, None
            if section not in groups:
                groups[section] = {}
                order.append(section)
            continue
        low = stripped.lower()
        if "limit" in low and ("weekly" in low or "five hour" in low or "5 hour" in low):
            kind = "weekly" if "weekly" in low else "session"
            pending = None
            continue
        if section is None or kind is None:
            continue
        pct = _PCT.search(stripped)
        if pct and "[" in stripped or (pct and stripped.startswith(pct.group(0))):
            remaining = float(pct.group(1))
            if remaining > 100:
                continue
            groups[section][kind] = {"usedPct": round(100.0 - remaining, 2),
                                     "resetAt": None}
            pending = (section, kind)
            continue
        if pending is not None:
            refresh = _REFRESH.search(stripped)
            if refresh:
                secs = _duration(refresh.group(1))
                win = groups[pending[0]].get(pending[1])
                if win is not None and secs > 0:
                    win["resetAt"] = now + timedelta(seconds=secs)
                pending = None
            elif "quota available" in low:
                pending = None
    out = [{"label": name, **groups[name]} for name in order if groups[name]]
    if not out:
        return None
    plan = None
    for plan in _PLAN.finditer(text):
        pass
    return {"plan": plan.group(1) if plan else None, "groups": out}


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def _ts(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def serialize(reading):
    return {"plan": reading.get("plan"),
            "groups": [{"label": g["label"],
                        **{k: {"usedPct": g[k]["usedPct"], "resetAt": _iso(g[k]["resetAt"])}
                           for k in ("session", "weekly") if k in g}}
                       for g in reading["groups"]]}


def load_reading(raw):
    """อ่านผลที่เก็บไว้กลับเป็น datetime · พังรูป = None"""
    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), list):
        return None
    groups = []
    for g in raw["groups"]:
        if not isinstance(g, dict) or not isinstance(g.get("label"), str):
            continue
        entry = {"label": g["label"]}
        for k in ("session", "weekly"):
            w = g.get(k)
            if isinstance(w, dict) and isinstance(w.get("usedPct"), (int, float)):
                entry[k] = {"usedPct": float(w["usedPct"]), "resetAt": _ts(w.get("resetAt"))}
        if len(entry) > 1:
            groups.append(entry)
    if not groups:
        return None
    plan = raw.get("plan") if isinstance(raw.get("plan"), str) else None
    return {"plan": plan, "groups": groups}


def latest_activity(base=None):
    """mtime ล่าสุดของบทสนทนา IDE/CLI · None = ไม่เคยใช้"""
    base = base or GEMINI_DIR
    latest = None
    for parts in ACTIVITY_DIRS:
        root = os.path.join(base, *parts)
        try:
            entries = list(os.scandir(root))
            candidates = [os.stat(root).st_mtime] + [e.stat().st_mtime for e in entries]
        except OSError:
            continue
        top = max(candidates)
        latest = top if latest is None else max(latest, top)
    return latest


def due(entry, latest_activity_ts, now_ts: float) -> bool:
    """ถามเมื่อมีการใช้ใหม่หลังรอบก่อนจบ และห่างพอ — นับจาก triedAt (กฎ clilive)"""
    if latest_activity_ts is None:
        return False
    tried = (entry or {}).get("triedAt") or 0
    return now_ts - tried >= MIN_INTERVAL and latest_activity_ts > tried + PROBE_GRACE


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


def read_cache(path=None) -> dict:
    return _read_store(path or CACHE_PATH)


def cli_bin():
    """แอปที่เปิดจาก Finder มี PATH สั้น — หาจากที่อยู่จริงก่อน which"""
    for candidate in CLI_CANDIDATES:
        if os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("agy")


def trust_prompt_action(screen: str):
    """จอถาม trust → "accept" เฉพาะเมื่อเป็นโฟลเดอร์ของเราและตัวเลือก Yes ถูกเลือกอยู่

    "abort" = ถาม trust ของที่อื่น (ห้าม Enter) · None = ไม่ได้ถาม
    """
    if "do you trust" not in screen.lower():
        return None
    tail = screen[screen.lower().rfind("accessing workspace"):]
    if PROBE_DIR in tail and "> Yes, I trust this folder" in tail:
        return "accept"
    return "abort"


def fetch_from_tui(timeout: float = 45.0, binary=None, now=None):
    """เปิด agy ใน pty พิมพ์ `/usage` อ่านจอ ปิดจอด้วย Esc แล้ว `/exit` — ล้มคืน None

    ห้ามส่งข้อความอื่นเข้าไปเด็ดขาด: อะไรที่ไม่ขึ้นต้นด้วย `/` คือ prompt ที่เรียกโมเดล
    """
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios

    binary = binary or cli_bin()
    if not binary:
        raise FileNotFoundError("agy")
    os.makedirs(PROBE_DIR, exist_ok=True)
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.chdir(PROBE_DIR)
            os.environ["TERM"] = "xterm-256color"
            os.execv(binary, [binary])
        finally:
            os._exit(127)
    end = time.time() + timeout
    raw = b""

    def screen():
        return strip_ansi(raw.decode("utf-8", "replace"))

    def pump(seconds, until=None):
        nonlocal raw
        stop = min(end, time.time() + seconds)
        while time.time() < stop:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return None
            if not chunk:
                return None
            raw += chunk
            if b"\x1b[6n" in chunk:  # ถามตำแหน่งเคอร์เซอร์ ไม่ตอบมันรอ
                os.write(fd, b"\x1b[1;1R")
            if until is not None:
                got = until()
                if got:
                    return got
        return None

    def type_line(text):
        for ch in text:
            os.write(fd, ch.encode())
            time.sleep(0.04)
        pump(0.8)
        os.write(fd, b"\r")

    ready = lambda: ("for shortcuts" in screen() or trust_prompt_action(screen()))  # noqa: E731
    result = None
    error = None
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, 140, 0, 0))
        pump(15, until=ready)
        action = trust_prompt_action(screen())
        if action == "abort":
            error = "trust_prompt"
        else:
            if action == "accept":
                os.write(fd, b"\r")
                pump(15, until=lambda: "for shortcuts" in screen().split("trust this folder")[-1])
            pump(2)  # ให้ล็อกอิน/ดึงโควตาเสร็จก่อนรับคำสั่ง
            for _ in range(3):
                if time.time() >= end:
                    break
                raw = b""
                type_line("/usage")
                pump(8, until=lambda: _LINES.search(last_frame(screen())))
                pump(0.8)
                result = parse_screen(last_frame(screen()), now or datetime.now(timezone.utc))
                if result is not None:
                    break
                os.write(fd, b"\x1b")
                pump(1)
            os.write(fd, b"\x1b")  # ตอนจอโควตาเปิดอยู่ /exit ถูกกลืน
            pump(1)
            type_line("/exit")
    except OSError:
        pass
    finally:
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
    if result is None and error:
        raise RuntimeError(error)
    return result


def probe(path=None, fetch=None, clock=time.time) -> bool:
    """ถามหนึ่งครั้งแล้วเก็บผล — ล้มต้องจด lastError/lastErrorAt (process นี้ไม่มี stdout)"""
    path = path or CACHE_PATH
    error = None
    try:
        reading = (fetch or fetch_from_tui)()
    except RuntimeError as exc:
        reading, error = None, str(exc)[:40]
    except Exception as exc:  # noqa: BLE001 — จดชนิดไว้ ไม่จดข้อความ (อาจมี path)
        reading, error = None, type(exc).__name__
    store = _read_store(path)
    store["triedAt"] = store.get("triedAt") or clock()
    if reading is not None:
        store["fetchedAt"] = clock()
        store["reading"] = serialize(reading)
        store.pop("lastError", None)
        store.pop("lastErrorAt", None)
    else:
        store["lastError"] = error or "screen_unparsed"
        store["lastErrorAt"] = clock()
    _write_store(path, store)
    return reading is not None


def kick(latest_activity_ts, path=None, clock=time.time, spawn=None, force=False) -> bool:
    """ถึงเวลาก็ปล่อย process แยกไปถาม — จด triedAt ก่อนสปอว์นกันเปิดซ้อน"""
    path = path or CACHE_PATH
    store = _read_store(path)
    if not force and not due(store, latest_activity_ts, clock()):
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
