"""ดึง % ทางการสดจาก endpoint OAuth ของ Anthropic — ไม่ต้องรอ /usage

แคช cachedUsageUtilization รีเฟรชเฉพาะตอนเปิด /usage หรือเริ่ม session ใหม่
บัญชีที่ไม่ได้เปิดจึงค้างเป็นวันๆ — โมดูลนี้ถามตัวเลขเดียวกันจาก endpoint ตรง
(ผู้ใช้อนุมัติแนวทางนี้เอง 2026-08-11 หลังเทียบข้อแลกทั้งสามทาง)

Claude Code เก็บ OAuth token ใน Keychain ของ macOS:
    ~/.claude              → service "Claude Code-credentials"
    config dir อื่น (ccs)  → service "Claude Code-credentials-" + sha256(path)[:8]
(ยืนยัน scheme กับ entry จริงครบทั้งสามบัญชี ccs ในเครื่องแล้ว)

กติกาความปลอดภัย — ห้ามละเมิดเด็ดขาด:
- token อยู่ในหน่วยความจำเท่านั้น ห้าม print/log/เขียนลงไฟล์ใดๆ
- ปลายทางเดียวที่ส่งได้คือ api.anthropic.com ผ่าน HTTPS (URL ตายตัวข้างล่าง)
- ทุก error จบเป็น None เงียบๆ — ห้ามแนบรายละเอียด request/response ติดออกไป
- สิ่งที่ออกจากโมดูลนี้มีแต่ตัวเลขกับเวลา ไม่มีชิ้นส่วนของ token
"""

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from .utilization import Utilization, windows_from_limits

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# endpoint ต่ออายุ token ของ Anthropic เอง — client_id สาธารณะของ Claude Code
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_BETA = "oauth-2025-04-20"
# รีเฟรชพลาดแล้วอย่าถล่มซ้ำทุก 60 วิ — จดเวลาไว้ (ไม่มี secret ในไฟล์นี้)
BACKOFF_PATH = os.path.join(os.path.expanduser("~"), ".config", "ai-usage",
                            "oauth-backoff.json")
BACKOFF_SECONDS = 900


def keychain_service(config_dir: str) -> str:
    path = os.path.abspath(os.path.expanduser(config_dir)).rstrip("/")
    default_dir = os.path.join(os.path.expanduser("~"), ".claude")
    if path == default_dir:
        return "Claude Code-credentials"
    return "Claude Code-credentials-" + hashlib.sha256(path.encode()).hexdigest()[:8]


def _security(args, stdin: Optional[bytes] = None):
    try:
        return subprocess.run(["security"] + args, input=stdin,
                              capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None


def _read_credentials(service: str) -> Optional[dict]:
    """อ่าน blob เต็มจาก Keychain — ครั้งแรก macOS จะเด้งถามสิทธิ์ต่อ entry
    ผู้ใช้กด "Always Allow" แล้วรอบถัดไปเงียบ กด Deny = ตกกลับแคชเฉยๆ"""
    proc = _security(["find-generic-password", "-s", service, "-w"])
    if proc is None or proc.returncode != 0:
        return None
    try:
        blob = json.loads(proc.stdout.decode("utf-8", "ignore").strip())
    except ValueError:
        return None
    return blob if isinstance(blob, dict) else None


def _keychain_account(service: str) -> Optional[str]:
    """ชื่อ account ของ entry — จำเป็นตอนเขียนกลับ ไม่งั้น -U จะงอก item ใหม่ซ้อน"""
    proc = _security(["find-generic-password", "-s", service])
    if proc is None or proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", "ignore") + proc.stderr.decode("utf-8", "ignore")
    m = re.search(r'"acct"<blob>="([^"]*)"', text)
    return m.group(1) if m else None


def _write_credentials(service: str, account: str, blob: dict) -> bool:
    """เขียน blob กลับ Keychain item เดิม — ส่งผ่าน stdin ของ `security -i`
    เพื่อไม่ให้ token โผล่ใน argv (ps เห็น argv ของ process อื่นได้)"""
    payload = json.dumps(blob, separators=(",", ":"))
    if any(ch in payload + account + service for ch in ("'", "\n", "\r")):
        return False  # อักขระที่ quoting ของ security -i รับไม่ได้ — ยอมแพ้ดีกว่าเขียนพัง
    cmd = "add-generic-password -U -a '%s' -s '%s' -w '%s'\n" % (account, service, payload)
    proc = _security(["-i"], stdin=cmd.encode("utf-8"))
    return proc is not None and proc.returncode == 0


def merged_credentials(blob: dict, token_response: dict, now_ms: int) -> dict:
    """รวม response จาก endpoint ต่ออายุเข้า blob เดิม — field อื่นต้องรอดครบ"""
    oauth = dict((blob or {}).get("claudeAiOauth") or {})
    oauth["accessToken"] = token_response["access_token"]
    if token_response.get("refresh_token"):
        oauth["refreshToken"] = token_response["refresh_token"]
    expires_in = token_response.get("expires_in")
    if isinstance(expires_in, (int, float)):
        # เผื่อขอบ 60 วิ — token ที่ "เกือบหมดอายุ" อันตรายกว่า token ที่รีเฟรชเร็วไปนิด
        oauth["expiresAt"] = now_ms + int(expires_in) * 1000 - 60_000
    out = dict(blob or {})
    out["claudeAiOauth"] = oauth
    return out


def _read_backoff() -> dict:
    try:
        with open(BACKOFF_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _mark_backoff(service: str, step: str) -> None:
    """จดเวลาที่พลาด + ขั้นที่พลาด (ชื่อขั้นล้วนๆ ไม่มี secret) ไว้ไล่ปัญหา"""
    data = _read_backoff()
    data[service] = {"ts": time.time(), "step": step}
    try:
        os.makedirs(os.path.dirname(BACKOFF_PATH), exist_ok=True)
        with open(BACKOFF_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def should_attempt_refresh(backoff: dict, service: str, now: float) -> bool:
    entry = backoff.get(service)
    last = entry.get("ts") if isinstance(entry, dict) else entry
    return not isinstance(last, (int, float)) or now - last >= BACKOFF_SECONDS


def _oauth_refresh(refresh_token: str, timeout: float = 10.0) -> Optional[dict]:
    body = json.dumps({"grant_type": "refresh_token",
                       "refresh_token": refresh_token,
                       "client_id": CLIENT_ID}).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:  # noqa: BLE001 — ห้ามให้รายละเอียด request หลุดออกไป
        return None
    if not isinstance(data, dict) or not data.get("access_token"):
        return None
    return data


def _refreshed_token(service: str, blob: dict) -> Optional[str]:
    """ต่ออายุ access token แล้วเขียน token ชุดใหม่กลับ Keychain

    Anthropic หมุน refresh token ทุกครั้ง (ตัวเก่าถูกยกเลิก) — จึงต้อง
    "ซ้อมเขียนค่าเดิมกลับ" ให้ผ่านก่อนค่อยรีเฟรชจริง ถ้าซ้อมไม่ผ่านให้เลิก
    ไม่งั้นได้ token ใหม่มาแต่เก็บไม่ได้ = บัญชีนั้นหลุดจาก Claude Code
    """
    oauth = (blob or {}).get("claudeAiOauth") or {}
    refresh_token = oauth.get("refreshToken")
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    if not should_attempt_refresh(_read_backoff(), service, time.time()):
        return None
    account = _keychain_account(service)
    if account is None:
        _mark_backoff(service, "account-attribute")
        return None
    if not _write_credentials(service, account, blob):
        _mark_backoff(service, "write-rehearsal")
        return None
    resp = _oauth_refresh(refresh_token)
    if resp is None:
        _mark_backoff(service, "oauth-refresh")
        return None
    merged = merged_credentials(blob, resp, int(time.time() * 1000))
    _write_credentials(service, account, merged)
    # เขียนรอบจริงพลาดทั้งที่ซ้อมผ่าน = โชคร้ายจริงๆ — token ใหม่ยังใช้ได้รอบนี้
    # และการซ้อมทำให้เคสนี้แทบเป็นไปไม่ได้ ไม่ log อะไรเพราะห้ามมีร่องรอย token
    return merged["claudeAiOauth"]["accessToken"]


def _read_token(config_dir: str) -> Optional[str]:
    """access token ที่พร้อมใช้ — สดอยู่ใช้เลย หมดอายุแล้วต่ออายุเองเงียบๆ"""
    service = keychain_service(config_dir)
    blob = _read_credentials(service)
    if blob is None:
        return None
    oauth = blob.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    expires_ms = oauth.get("expiresAt")
    if isinstance(expires_ms, (int, float)) and expires_ms / 1000.0 <= time.time():
        # บัญชีที่ไม่ได้เปิดใช้ Claude Code จะไม่มีใครต่ออายุให้ — เราต่อเอง
        # (ผู้ใช้อนุมัติ 2026-08-12 พร้อมเงื่อนไขซ้อมเขียนก่อนรีเฟรช)
        return _refreshed_token(service, blob)
    return token


def fetch_utilization(config_dir: str, timeout: float = 3.5) -> Optional[Utilization]:
    """คืน Utilization สด (fetched_at = ตอนนี้) หรือ None ให้ผู้เรียกตกไปใช้แคช"""
    token = _read_token(config_dir)
    if token is None:
        return None
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": OAUTH_BETA,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:  # noqa: BLE001 — 401/เน็ตล่ม/JSON พัง: ตกกลับแคชเงียบๆ
        return None
    if not isinstance(data, dict):
        return None
    windows = windows_from_limits(data.get("limits"))
    if not windows:
        return None
    return Utilization(fetched_at=datetime.now(timezone.utc), windows=windows)
