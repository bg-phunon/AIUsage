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
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from .utilization import Utilization, windows_from_limits

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"


def keychain_service(config_dir: str) -> str:
    path = os.path.abspath(os.path.expanduser(config_dir)).rstrip("/")
    default_dir = os.path.join(os.path.expanduser("~"), ".claude")
    if path == default_dir:
        return "Claude Code-credentials"
    return "Claude Code-credentials-" + hashlib.sha256(path.encode()).hexdigest()[:8]


def _read_token(config_dir: str) -> Optional[str]:
    """อ่าน access token จาก Keychain — คืน None เมื่อไม่มี/หมดอายุ/ถูกปฏิเสธ

    ครั้งแรกที่รัน macOS จะเด้งถามสิทธิ์ต่อ entry — ผู้ใช้กด "Always Allow"
    แล้วรอบถัดไปเงียบ ถ้ากด Deny ก็แค่ตกกลับไปใช้แคชเหมือนเดิม
    """
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", keychain_service(config_dir), "-w"],
            capture_output=True, timeout=6)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        blob = json.loads(proc.stdout.decode("utf-8", "ignore").strip())
    except ValueError:
        return None
    oauth = (blob or {}).get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    expires_ms = oauth.get("expiresAt")
    if isinstance(expires_ms, (int, float)) and expires_ms / 1000.0 <= time.time():
        return None  # หมดอายุ — Claude Code จะรีเฟรชเองตอนบัญชีนั้นถูกใช้
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
