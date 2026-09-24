"""เลขโควตาของ Claude จาก Claude Code CLI เอง ไม่ใช่จากการยิง endpoint ด้วย token ของผู้ใช้

`claude -p --input-format stream-json` รับ control request `get_usage` ซึ่งคืนก้อน
rate_limits ทั้งใบโดยไม่เรียกโมเดล (วัดจริง 2026-09-24: total_cost_usd 0,
total_api_duration_ms 0) และ CLI ใช้ auth ของมันเอง เอนจินจึงไม่ต้องแตะ Keychain
ไม่ต้องต่ออายุ refresh token — จุดเสี่ยงที่สุดของโปรเจกต์หายไปทั้งก้อน

หลักการเดียวกับที่ทำกับ Codex (`codex app-server`) ต่างกันแค่ชื่อโปรโตคอล
"""

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from .utilization import Utilization, windows_from_limits

TTL = 180
# สปอว์น CLI หนึ่งครั้งกิน 0.4–1.3 วิ (วัดจริง 4 บัญชี) แพงกว่ายิง HTTP มาก
# เอนจินเดินทุก 60 วิ จึงต้องมีแคชคั่น ไม่งั้นสี่บัญชีกินเวลาไปครึ่งรอบ
CACHE_PATH = os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                          "AIUsage", "claude-live.json")
CLI_CANDIDATES = (os.path.join(os.path.expanduser("~"), ".local", "bin", "claude"),
                  "/opt/homebrew/bin/claude", "/usr/local/bin/claude")
ASK_TRIES = 3
ASK_PAUSE = 1.0


def cli_env(config_dir: str, base=None) -> dict:
    """env สำหรับสปอว์น CLI — บัญชี default ต้องไม่มี CLAUDE_CONFIG_DIR

    เคสจริง 2026-09-24: ตั้ง CLAUDE_CONFIG_DIR=~/.claude ทั้งที่เป็นค่าปริยายอยู่แล้ว
    CLI กลับไปหา keychain ชื่อที่ hash จาก path แทน "Claude Code-credentials"
    แล้วตอบ plan=None rows=0 เหมือนบัญชีที่ยังไม่ได้ล็อกอิน
    """
    env = dict(os.environ if base is None else base)
    path = os.path.abspath(os.path.expanduser(config_dir)).rstrip("/")
    if path == os.path.join(os.path.expanduser("~"), ".claude"):
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = path
    return env


def usage_from_reply(msg) -> Optional[dict]:
    """ก้อน rate_limits จากคำตอบหนึ่งบรรทัด — อย่างอื่นไม่ใช่คำตอบ"""
    if not isinstance(msg, dict) or msg.get("type") != "control_response":
        return None
    resp = msg.get("response")
    if not isinstance(resp, dict) or resp.get("subtype") != "success":
        return None
    inner = resp.get("response")
    if not isinstance(inner, dict):
        return None
    rate_limits = inner.get("rate_limits")
    return rate_limits if isinstance(rate_limits, dict) else None


def reply_is_finished(msg) -> bool:
    """CLI บอกเองว่าได้คำตอบเรื่องโควตามาแล้ว — ว่างก็คือว่างจริง ไม่ต้องรอต่อ"""
    if not isinstance(msg, dict):
        return False
    inner = (msg.get("response") or {}).get("response")
    return bool(isinstance(inner, dict) and inner.get("rate_limits_available"))


def ask(send, tries: int = ASK_TRIES, pause=time.sleep) -> Optional[dict]:
    """ถามจนกว่า CLI จะบอกว่ามีคำตอบแล้ว — มันตอบทันทีด้วยของที่มีในมือ

    เคสจริง 2026-09-24: คำตอบแรกของบางบัญชีมาก่อน CLI ดึง usage เสร็จ ได้ rows=0
    ทั้งที่ถามซ้ำอีกวินาทีเดียวก็ครบ · แต่บัญชี Team ตอบ rate_limits_available
    พร้อม rows=0 ค้างอยู่เป็นนาที ถามซ้ำแปดครั้งก็เท่าเดิม — สองอย่างนี้หน้าตา
    เหมือนกันถ้าดูแต่จำนวนแถว ตัวแยกคือธงที่ CLI ติดมาให้
    """
    for i in range(tries):
        msg = send(str(i + 1))
        rate_limits = usage_from_reply(msg)
        if rate_limits is not None and (rate_limits.get("limits")
                                        or reply_is_finished(msg)):
            return rate_limits
        if i + 1 < tries:
            pause(ASK_PAUSE)
    return None


def _ts(raw) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def reset_state(rate_limits) -> Optional[dict]:
    """ใบรีเซ็ตลิมิตของ Claude · None = ไม่ได้ข้อมูล ต่างจาก count 0 = ยืนยันว่าไม่เหลือ

    สองแบบที่ server รู้จัก:
      cedar_ember  ใบเป็นใบๆ มีวันหมดอายุ (รูปเดียวกับของ Codex)
      juniper_tide ใบเดียวต่อสัปดาห์ — `/limit-reset` รีเซ็ตหน้าต่าง 5 ชม.
                   แล้วไปกินโควตารายสัปดาห์แทน

    `eligible: false` แปลว่า client นี้ไม่มีสิทธิ์รู้ (เคสจริง 2026-09-24:
    ineligible_reason "surface" — server ตอบเรื่องใบรีเซ็ตเฉพาะ Claude Code)
    ซึ่งคนละเรื่องกับ "ไม่เหลือใบ" เอามาแสดงเป็น 0 ไม่ได้เด็ดขาด
    """
    if not isinstance(rate_limits, dict):
        return None
    cedar = rate_limits.get("cedar_ember")
    if isinstance(cedar, dict) and cedar.get("eligible"):
        grants = [g for g in (cedar.get("grants") or []) if isinstance(g, dict)]
        count = 0
        for grant in grants:
            try:
                count += max(0, int(grant.get("resets_left") or 0))
            except (TypeError, ValueError):
                continue
        expiring = sorted(t for t in (_ts(g.get("ends_at")) for g in grants)
                          if t is not None)
        return {"count": count, "expiring": expiring,
                "nextAvailableAt": _ts(cedar.get("weekly_resets_at"))}
    juniper = rate_limits.get("juniper_tide")
    if isinstance(juniper, dict) and juniper.get("eligible"):
        available = bool(juniper.get("available"))
        return {"count": 1 if available else 0, "expiring": [],
                "nextAvailableAt": None if available else
                _ts(juniper.get("next_available_at") or juniper.get("weekly_resets_at"))}
    return None


WALL_PCT = 99.0


def at_wall(util) -> bool:
    """หน้าต่างไหนสักอันแตะเพดานแล้วหรือยัง

    server ส่งก้อนใบรีเซ็ตมาให้เฉพาะเมื่อ client บอกว่าชนเพดาน (`?at_wall=1`)
    เราจึงถามได้เฉพาะตอนที่มันเป็นความจริง — ซึ่งบังเอิญเป็นตอนเดียวที่คนอยากรู้
    """
    return any(w.percent >= WALL_PCT for w in (getattr(util, "windows", None) or []))


def utilization(rate_limits, fetched_at: datetime) -> Optional[Utilization]:
    """ก้อนจาก CLI → Utilization รูปเดียวกับที่ได้จาก endpoint"""
    windows = windows_from_limits((rate_limits or {}).get("limits"))
    if not windows:
        return None
    return Utilization(fetched_at=fetched_at, windows=windows)


def _cli_bin() -> Optional[str]:
    """แอปที่เปิดจาก Finder มี PATH สั้น — หาจากที่อยู่จริงก่อน which"""
    for path in CLI_CANDIDATES:
        if os.access(path, os.X_OK):
            return path
    return shutil.which("claude")


def fetch_from_cli(config_dir: str, timeout: float = 20.0,
                   binary: Optional[str] = None) -> Optional[dict]:
    """สปอว์น CLI หนึ่งตัวแล้วถาม get_usage — ล้มเหลวคืน None ให้ผู้เรียกตกไปทางอื่น"""
    import select

    binary = binary or _cli_bin()
    if not binary:
        return None
    try:
        proc = subprocess.Popen(
            [binary, "-p", "--verbose", "--input-format", "stream-json",
             "--output-format", "stream-json"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
            env=cli_env(config_dir), cwd=os.path.expanduser("~"))
    except OSError:
        return None
    end = time.time() + timeout

    def send(request_id):
        """ส่งคำถามหนึ่งครั้งแล้วรอคำตอบของคำถามนั้น — ข้ามบรรทัด hook/system ทิ้ง"""
        try:
            proc.stdin.write(json.dumps({
                "type": "control_request", "request_id": request_id,
                "request": {"subtype": "get_usage"}}) + "\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            return None
        while time.time() < end:
            ready, _, _ = select.select([proc.stdout], [], [],
                                        max(0.0, end - time.time()))
            if not ready:
                return None
            line = proc.stdout.readline()
            if not line:
                return None
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if (msg.get("type") == "control_response"
                    and (msg.get("response") or {}).get("request_id") == request_id):
                return msg
        return None

    try:
        return ask(send)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            proc.kill()


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


def _stamp(old: dict, result, now: float) -> dict:
    """ได้คำตอบใหม่ก็เปลี่ยนอายุ ไม่ได้ก็เก็บของเก่าพร้อมอายุเดิมไว้ จดแค่ว่าถามแล้ว"""
    if result is None:
        return {"fetchedAt": old.get("fetchedAt"), "result": old.get("result"),
                "triedAt": now}
    return {"fetchedAt": now, "result": result, "triedAt": now}


def warm(config_dirs, fetch=None, path: Optional[str] = None,
         clock=time.time, workers: int = 4) -> dict:
    """ถามทุกบัญชีที่ค้างพร้อมกันแล้วเขียนแคชทีเดียว

    สปอว์นเรียงกันทีละบัญชีกินเวลารวม 20 วินาทีต่อรอบ (วัดจริง 2026-09-24: 4 บัญชี
    21.5 วินาที) ขณะที่เอนจินมีเพดาน 45 วินาทีและยังต้องไปไล่ rollout ของ Codex ต่อ
    """
    path = path or CACHE_PATH
    fetch = fetch or fetch_from_cli
    store = _read_store(path)
    stale = [d for d in config_dirs
             if clock() - ((store.get(d) or {}).get("triedAt") or 0) >= TTL]
    if not stale:
        return store
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(stale)))) as pool:
        answers = list(pool.map(fetch, stale))
    now = clock()
    for config_dir, result in zip(stale, answers):
        store[config_dir] = _stamp(store.get(config_dir) or {}, result, now)
    _write_store(path, store)
    return store


def live(config_dir: str, fetch=None, path: Optional[str] = None,
         clock=time.time) -> Optional[dict]:
    """คำตอบล่าสุดต่อบัญชี — ถามใหม่ไม่ถี่กว่า TTL วินาที

    ถามไม่สำเร็จคืนของเก่าพร้อมอายุเดิม ผู้เรียกจะได้รู้ว่ามันเก่าแค่ไหน
    """
    path = path or CACHE_PATH
    fetch = fetch or fetch_from_cli
    store = _read_store(path)
    entry = store.get(config_dir)
    entry = entry if isinstance(entry, dict) else {}
    # นับจาก "ครั้งล่าสุดที่ถาม" ไม่ใช่ "ครั้งล่าสุดที่ได้คำตอบ" — บัญชีที่ยังไม่ได้
    # ล็อกอินตอบว่างเสมอ ถ้าจำแต่ครั้งที่สำเร็จมันจะถูกสปอว์นใหม่ทุกรอบ 60 วินาที
    # ครั้งละ 3-4 วินาที ตลอดไป
    if clock() - (entry.get("triedAt") or 0) < TTL:
        return entry if entry.get("result") is not None else None
    entry = _stamp(entry, fetch(config_dir), clock())
    store[config_dir] = entry
    _write_store(path, store)
    return entry if entry.get("result") is not None else None
