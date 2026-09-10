#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# <bitbar.title>AI Usage</bitbar.title>
# <bitbar.version>v1.0</bitbar.version>
# <bitbar.desc>Per-account usage limits for Claude Code (multi-account via ccs), Codex, and manual trackers.</bitbar.desc>
# <bitbar.dependencies>python3</bitbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# <swiftbar.runInBash>false</swiftbar.runInBash>
#
# แหล่งหลักคือไฟล์ log ในเครื่อง — ไม่กินโควตาโมเดล
# ข้อยกเว้นเดียว (ผู้ใช้อนุมัติ 2026-08-11): ถาม % สดจาก endpoint usage ของ
# Anthropic ด้วย OAuth token ใน Keychain — ดูกติกาใน engine/aiusage/liveusage.py
#
# ติดตั้ง:  brew install --cask swiftbar
#          cp ai-usage.60s.py ~/Library/Application\ Support/SwiftBar/Plugins/
#          chmod +x ~/Library/Application\ Support/SwiftBar/Plugins/ai-usage.60s.py

from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
CFG_DIR = os.path.join(HOME, ".config", "ai-usage")
CFG_PATH = os.path.join(CFG_DIR, "config.json")
STATE_PATH = os.path.join(CFG_DIR, "state.json")
SELF = os.path.abspath(__file__)

# ในโปรเจกต์แพ็กเกจอยู่ที่ engine/aiusage ส่วนใน .app ที่ติดตั้งแล้วมันถูกก็อป
# ไปวางข้างสคริปต์เป็น Resources/aiusage เพื่อไม่ให้ engine/tests ติดไปด้วย
sys.path.insert(0, os.path.join(os.path.dirname(SELF), "engine"))
sys.path.insert(0, os.path.dirname(SELF))
from aiusage import buckets as _buckets  # noqa: E402
from aiusage import liveusage as _liveu  # noqa: E402
from aiusage import utilization as _util  # noqa: E402
from aiusage import quota429 as _q429  # noqa: E402

BLOCK_HOURS = 5
WEEK_DAYS = 7

# ── สัญญาณ "โดนตัดโควตาจริง" ─────────────────────────────────────────────────
# Claude Code log ไว้เมื่อเจอ error ที่ error=="rate_limit" และ apiErrorIsTransient
# เป็น false — แต่ข้อความไม่ได้การันตีว่าเป็นโควตาแอคเคาต์จริงจาก Anthropic เสมอไป
# พบ 2 แบบที่ "ไม่ใช่": (1) proxy ท้องถิ่น (เช่น alias ที่ตั้ง ANTHROPIC_BASE_URL เอง)
# ซึ่งมักมี error code เป็นวงเล็บตัวเลขและศัพท์ระบบเติมเงินของตัวเอง (2) ลิมิตเฉพาะ
# โมเดลเดียว (เช่น "Fable 5") ไม่ใช่ลิมิตของบล็อกทั้งบัญชี — กรองสองแบบนี้ออกก่อน
QUOTA_HIT_BRACKET_RE = re.compile(r"\[\d{3,4}\]")
QUOTA_HIT_PROXY_WORDS = ("resource package", "recharge", "token-plan", "token plan")
QUOTA_HIT_MODEL_WORDS = ("/usage-credits", "switch models", "/model")
QUOTA_HIT_WEEK_RE = re.compile(r"week|month", re.I)
QUOTA_HIT_MIN_TOKENS = 500_000  # กันสัญญาณหลอกจาก rate limit ต่อนาทีที่ token ยังแทบไม่ถูกใช้

# ราคา list ของ Anthropic (USD ต่อ 1M tokens) — ตรวจล่าสุด 2026-08-08
#
# นี่คือ "มูลค่าถ้ายิงผ่าน API" ไม่ใช่บิลจริงของบัญชี subscription
# บัญชี Max/Team จ่ายเหมาไปแล้ว ตัวเลขนี้จึงบอกได้แค่ความคุ้ม (ดู costKind)
#
# ห้ามใส่ราคาของเจ้าอื่นแบบเดาๆ — ถังที่ไม่รู้ราคาต้องคืน costKnown=False
# แล้วปล่อยให้ UI ขึ้น "—" ดีกว่าโชว์ตัวเลขที่ผิด
PRICES = {
    "opus": (5.0, 25.0),
    "fable": (10.0, 50.0),
    "mythos": (10.0, 50.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}

GREEN, YELLOW, RED, DIM = "#4CC38A", "#E2A93B", "#E5544B", "#8A93A6"


# ── ตัวช่วยทั่วไป ───────────────────────────────────────────────────────────
def now_utc():
    return datetime.now(timezone.utc)


def parse_ts(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fmt_tokens(n):
    if n >= 1_000_000:
        return "%.2fM" % (n / 1_000_000)
    if n >= 1_000:
        return "%.0fk" % (n / 1_000)
    return str(int(n))


def fmt_left(delta):
    if delta is None:
        return ""
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "รีเซ็ตแล้ว"
    d, h, m = secs // 86400, (secs % 86400) // 3600, (secs % 3600) // 60
    if d:
        return "%dวัน %dชม." % (d, h)
    if h:
        return "%dชม. %02dน." % (h, m)
    return "%dน." % m


def color_for(pct):
    if pct is None:
        return DIM
    if pct >= 90:
        return RED
    if pct >= 70:
        return YELLOW
    return GREEN


def bar(pct, width=12):
    if pct is None:
        return "·" * width
    filled = max(0, min(width, int(round(pct / 100.0 * width))))
    return "█" * filled + "░" * (width - filled)


def clean(s):
    # SwiftBar ใช้ | เป็นตัวคั่นพารามิเตอร์
    return str(s).replace("|", "¦").replace("\n", " ")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ── ค้นหา config dir ของแต่ละ Claude account ────────────────────────────────
def discover_claude_dirs():
    cands = [os.path.join(HOME, ".claude")]
    cands += sorted(glob.glob(os.path.join(HOME, ".ccs", "instances", "*")))
    cands += sorted(glob.glob(os.path.join(HOME, ".config", "ccs", "instances", "*")))
    cands += sorted(glob.glob(os.path.join(HOME, ".claude-*")))
    cands += sorted(glob.glob(os.path.join(HOME, ".config", "claude-*")))

    out, seen = [], set()
    for c in cands:
        real = os.path.realpath(c)
        if real in seen or not os.path.isdir(os.path.join(c, "projects")):
            continue
        seen.add(real)
        name = os.path.basename(c.rstrip("/"))
        label = "default" if name == ".claude" else name.lstrip(".").replace("claude-", "")
        out.append({"label": label, "dir": c, "profile": None if name == ".claude" else label})
    return out


def account_email(config_dir):
    # Never inspect credential stores; account labels are supplied by config.
    for fname in (".claude.json",):
        data = read_json(os.path.join(config_dir, fname), None)
        if not isinstance(data, dict):
            continue
        found = _find_key(data, ("emailAddress", "email", "account_email"))
        if found:
            return found
    return None


def _find_key(obj, keys, depth=0):
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and "@" in v:
                return v
        for v in obj.values():
            r = _find_key(v, keys, depth + 1)
            if r:
                return r
    return None


def account_plan(config_dir):
    """แผน subscription ของบัญชี (Max 20x / Max 5x / Pro / Team / ...)
    ไฟล์ oauthAccount อยู่คนละที่กันระหว่างบัญชี default กับบัญชี ccs:
    - default: HOME/.claude.json (ไฟล์นอก ~/.claude/)
    - ccs instance: <instance_dir>/.claude.json (อยู่ในตัว instance เอง)
    """
    stripped = config_dir.rstrip("/")
    for path in (os.path.join(config_dir, ".claude.json"), stripped + ".json"):
        data = read_json(path, None)
        if not isinstance(data, dict):
            continue
        oauth = data.get("oauthAccount")
        if not isinstance(oauth, dict):
            continue
        tier = oauth.get("organizationRateLimitTier") or oauth.get("userRateLimitTier")
        org_type = oauth.get("organizationType")
        label = plan_label(org_type, tier)
        if label:
            return label
    return None


def plan_label(org_type, tier):
    # tier บอกระดับ (20x/5x) ได้ละเอียดกว่า แต่บางทีเป็น codename ภายใน (เช่น "default_raven")
    # ที่เดาระดับไม่ได้ — ตอนนั้นให้ organizationType (claude_team/claude_max/...) ตัดสินแทน
    t = (tier or "").lower()
    o = (org_type or "").lower()
    if "20x" in t:
        return "Max 20x"
    if "5x" in t:
        return "Max 5x"
    if "max" in t or "max" in o:
        return "Max"
    if "team" in t or "team" in o:
        return "Team"
    if "enterprise" in t or "enterprise" in o:
        return "Enterprise"
    if "pro" in t or "pro" in o:
        return "Pro"
    if "free" in t or "free" in o:
        return "Free"
    s = t or o
    if not s:
        return None
    return s.replace("default_", "").replace("claude_", "").replace("_", " ").title()


# ── อ่าน transcript ของ Claude Code ─────────────────────────────────────────
def claude_entries(config_dir, since):
    """คืน list ของ (timestamp, tokens_dict, model) จากไฟล์ JSONL ของ account นี้"""
    entries, seen = [], set()
    pattern = os.path.join(config_dir, "projects", "**", "*.jsonl")
    cutoff = since.timestamp() - 3600

    for path in glob.iglob(pattern, recursive=True):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            fh = open(path, "r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"usage"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                ts = parse_ts(rec.get("timestamp"))
                if ts is None or ts < since:
                    continue
                key = (msg.get("id"), rec.get("requestId"))
                if key != (None, None):
                    if key in seen:
                        continue
                    seen.add(key)
                entries.append((ts, usage, msg.get("model") or ""))
    entries.sort(key=lambda e: e[0])
    return entries


def total_tokens(u):
    return (
        int(u.get("input_tokens") or 0)
        + int(u.get("output_tokens") or 0)
        + int(u.get("cache_creation_input_tokens") or 0)
        + int(u.get("cache_read_input_tokens") or 0)
    )


def cost_of(u, model):
    key = next((k for k in PRICES if k in (model or "").lower()), None)
    if not key:
        return 0.0
    inp, outp = PRICES[key]
    m = 1_000_000.0
    return (
        int(u.get("input_tokens") or 0) * inp
        + int(u.get("cache_creation_input_tokens") or 0) * inp * 1.25
        + int(u.get("cache_read_input_tokens") or 0) * inp * 0.10
        + int(u.get("output_tokens") or 0) * outp
    ) / m


def cost_known_for_model(model):
    """True only when the model can be matched to a published local rate."""
    return next((k for k in PRICES if k in (model or "").lower()), None) is not None


def costs_known(entries):
    """True when at least part of the total has a published local rate.

    Unknown models contribute no dollars, but the UI labels the result as an
    estimate instead of presenting that incomplete sum as a definitive bill.
    """
    return any(cost_known_for_model(model) for _, _, model in entries)


def current_block(entries):
    """หน้าต่าง 5 ชม. ปัจจุบันตามหลักเดียวกับ Claude Code: เริ่มนับจาก
    ข้อความแรกของบล็อก ปัดลงเป็นต้นชั่วโมง และตัดบล็อกใหม่เมื่อเว้นว่างเกิน 5 ชม."""
    if not entries:
        return None
    span = timedelta(hours=BLOCK_HOURS)
    start = entries[0][0].replace(minute=0, second=0, microsecond=0)
    block, prev = [], entries[0][0]
    for ts, usage, model in entries:
        if ts - start >= span or ts - prev >= span:
            start = ts.replace(minute=0, second=0, microsecond=0)
            block = []
        block.append((ts, usage, model))
        prev = ts
    if now_utc() - start >= span:
        return None  # บล็อกล่าสุดหมดอายุแล้ว = รีเซ็ตเรียบร้อย
    return {"start": start, "end": start + span, "entries": block}


def summarize(entries):
    return {
        "tokens": sum(total_tokens(u) for _, u, _ in entries),
        "cost": sum(cost_of(u, m) for _, u, m in entries),
        "calls": len(entries),
    }


def _quota_hit_text(rec):
    msg = rec.get("message") or {}
    for c in msg.get("content") or []:
        if isinstance(c, dict) and c.get("type") == "text":
            return c.get("text") or ""
    return ""


def _is_clean_quota_signal(text):
    """คัด error ที่ไม่ใช่โควตาแอคเคาต์จริงออก — proxy ท้องถิ่นหรือลิมิตเฉพาะโมเดล"""
    if QUOTA_HIT_BRACKET_RE.search(text):
        return False
    low = text.lower()
    if any(w in low for w in QUOTA_HIT_PROXY_WORDS):
        return False
    if any(w in low for w in QUOTA_HIT_MODEL_WORDS):
        return False
    return True


def quota_hit_events(config_dir, since):
    """หาเวลาที่ Claude Code รายงานว่าโดนตัดโควตาจริง (ไม่ใช่ error ชั่วคราว)
    คืน list ของ (timestamp, window) โดย window คือ "week" หรือ "5h" """
    pattern = os.path.join(config_dir, "projects", "**", "*.jsonl")
    cutoff = since.timestamp() - 3600
    out = []
    for path in glob.iglob(pattern, recursive=True):
        if "/subagents/" in path or "/tool-results/" in path:
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            fh = open(path, "r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"rate_limit"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("error") != "rate_limit" or rec.get("apiErrorIsTransient") is not False:
                    continue
                ts = parse_ts(rec.get("timestamp"))
                if ts is None or ts < since:
                    continue
                text = _quota_hit_text(rec)
                if not text or not _is_clean_quota_signal(text):
                    continue
                window = "week" if QUOTA_HIT_WEEK_RE.search(text) else "5h"
                out.append((ts, window))
    return out


def _tokens_in_block_at(entries, ts):
    """ผลรวม token ของบล็อก 5 ชม. ที่ครอบคลุมเวลา ts — logic เดียวกับ current_block()"""
    span = timedelta(hours=BLOCK_HOURS)
    start, prev, bucket = None, None, []
    for ets, usage, model in entries:
        if ets > ts:
            break
        if start is None or (prev is not None and (ets - start >= span or ets - prev >= span)):
            start, bucket = ets.replace(minute=0, second=0, microsecond=0), []
        bucket.append(total_tokens(usage))
        prev = ets
    return sum(bucket)


def calibrate_budget5h(entries, hits):
    """ประมาณ budget5h จากจำนวน token จริง ณ เวลาที่เคยโดนตัดโควตา (median ถ้ามีหลายครั้ง)"""
    samples = sorted(
        s for s in (_tokens_in_block_at(entries, ts) for ts, window in hits if window == "5h")
        if s >= QUOTA_HIT_MIN_TOKENS
    )
    return samples[len(samples) // 2] if samples else None


def account_utilization(config_dir, live_enabled=True):
    """สด → สดล่าสุดที่เคยได้ → แคชของ Claude Code — อันไหนใหม่สุดชนะ

    เน็ตสะดุดรอบเดียวเคยทำเลขกะพริบหาย: live พลาดแล้วดิ่งไปแคชเก่าที่
    unsure ทันที ทั้งที่ 60 วิก่อนเพิ่งได้ตัวเลขทางการ — จำผลสดล่าสุดไว้
    เลขจะค่อยๆ เสื่อมเป็น lower_bound ตามอายุจริง ไม่ใช่ดับวูบ

    ปิด live = ไม่แตะ Keychain ไม่ออกเน็ต และไม่ใช้แคชที่งอกจาก live ด้วย
    เหลือเฉพาะแคชที่ Claude Code เขียนเองซึ่งไม่เกี่ยวกับ credential
    """
    if not live_enabled:
        return _util.read_utilization(config_dir)
    live = _liveu.fetch_utilization(config_dir)
    if live is not None:
        return live
    candidates = [u for u in (_liveu.cached_live_utilization(config_dir),
                              _util.read_utilization(config_dir)) if u is not None]
    return max(candidates, key=lambda u: u.fetched_at, default=None)


def claude_account_stats(acc, live_enabled=False):
    since = now_utc() - timedelta(days=WEEK_DAYS)
    entries = claude_entries(acc["dir"], since)
    blk = current_block(entries)
    week = summarize(entries)
    hits = quota_hit_events(acc["dir"], since)
    out = {
        "week": week,
        "block": None,
        "last": entries[-1][0] if entries else None,
        "models": sorted({m.split("-")[1] for _, _, m in entries[-40:] if m.count("-") >= 1}),
        "plan": account_plan(acc["dir"]),
        "budget5hAuto": calibrate_budget5h(entries, hits),
        "utilization": account_utilization(acc["dir"], live_enabled),
        "lastActivity": entries[-1][0] if entries else None,
        "costKnown": costs_known(entries),
    }
    if blk:
        s = summarize(blk["entries"])
        s["start"], s["end"] = blk["start"], blk["end"]
        out["block"] = s
    return out


# ── อ่าน rollout ของ Codex ──────────────────────────────────────────────────
def iter_lines_reverse(path, chunk_size=1 << 20):
    """บรรทัดจากท้ายไฟล์ไล่ขึ้นหัว — อ่านเท่าที่ผู้เรียกขอ ไม่ต้องแตะทั้งก้อน

    rollout เรียงตามเวลาอยู่แล้ว ผู้เรียกจึงหยุดได้ทันทีที่เจอ record ที่เก่ากว่า
    หน้าต่างสัปดาห์ session ที่เปิดค้างไว้เป็นเดือนโตได้ถึงระดับกิกะไบต์ (เคสจริง
    2026-09-10: rollout ของวันที่ 15 ส.ค. ยังถูกเขียนต่อจนโต 2.4 GB) การสแกน
    ทั้งไฟล์ทุก 60 วินาทีมีปลายทางเดียวคือชน timeout 45 วินาทีของแอป แล้วแถบ
    Codex หายไปทั้งแถว

    ตัดบรรทัดบนไบต์แล้วค่อย decode — 0x0A ไม่เคยโผล่กลางตัวอักษร UTF-8 ชิ้นที่
    ถูก chunk หั่นกลางบรรทัดจึงรอต่อกับ chunk ก่อนหน้าได้อย่างปลอดภัย
    """
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos = fh.tell()
        tail = b""
        while pos > 0:
            step = min(chunk_size, pos)
            pos -= step
            fh.seek(pos)
            parts = (fh.read(step) + tail).split(b"\n")
            tail = parts.pop(0)
            for part in reversed(parts):
                if part:
                    yield part.decode("utf-8", "ignore")
        if tail:
            yield tail.decode("utf-8", "ignore")


def codex_stats(codex_dir):
    """Codex เขียน rate_limits ที่เป็นเปอร์เซ็นต์จริงลง rollout log — ใช้ค่านั้นเลย

    เก็บ "หน้าต่างล่าสุดที่มีค่าจริง" แยกรายช่อง ไม่ใช่ก้อน rate_limits ใหม่สุด
    ทั้งก้อน — บาง record มี primary/secondary เป็น null ทั้งคู่ (เช่นก้อนของ
    limit_id "premium" ที่บอกแค่เครดิต) ถ้าเอาก้อนใหม่สุดแบบไม่ดูว่ามีหน้าต่างไหม
    ก้อนว่างจะไปลบเลขที่รู้แล้วทิ้ง (เคสจริง 2026-08-21: weekly 100% ที่ยังไม่ถึง
    เวลารีเซ็ตหายจากจอเพราะก้อนว่างมาทีหลัง 4 นาที)
    """
    files = []
    for pat in ("sessions/**/*.jsonl", "*.jsonl"):
        files += glob.glob(os.path.join(codex_dir, pat), recursive=True)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    tokens = 0
    windows = {}       # ช่อง → {limit_id → {"win": หน้าต่างดิบ, "ts": เวลาของ record}}
    last_activity = None
    credits = None     # (ts, ค่า) — เครดิตล่าสุดที่อ่านออก
    week_cut = now_utc() - timedelta(days=WEEK_DAYS)

    for path in files[:60]:
        try:
            if datetime.fromtimestamp(os.path.getmtime(path), timezone.utc) < week_cut:
                break
        except OSError:
            continue
        lines = iter_lines_reverse(path)
        try:
            for line in lines:
                if "token_count" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = parse_ts(rec.get("timestamp"))
                if ts is not None and ts < week_cut:
                    break  # ไล่จากท้ายมา ที่เหลือข้างหน้าเก่ากว่านี้ทั้งหมด
                payload = rec.get("payload") or rec
                info = payload.get("info") or {}
                last = info.get("last_token_usage") or {}
                used = int(last.get("total_tokens") or 0)
                if ts:
                    tokens += used
                    if used and (last_activity is None or ts > last_activity):
                        last_activity = ts
                rl = payload.get("rate_limits") or info.get("rate_limits")
                if not isinstance(rl, dict):
                    continue
                limit_id = rl.get("limit_id")
                cr = parse_credits(rl.get("credits"))
                if cr is not None and ts is not None and (credits is None or ts > credits[0]):
                    credits = (ts, cr)
                for slot in ("primary", "secondary"):
                    win = rl.get(slot)
                    if not isinstance(win, dict):
                        continue  # ก้อนที่ไม่มีหน้าต่าง ไม่ใช่คำประกาศว่า "ไม่มีลิมิตแล้ว"
                    # เก็บแยกรายถัง ไม่ยุบเหลือ "ใหม่สุดของช่องนี้" — สอง session ที่
                    # รันพร้อมกันรายงานคนละถังได้ และตัวที่ใหม่กว่าไม่ได้แปลว่าดีกว่า
                    bucket = windows.setdefault(slot, {}).setdefault(
                        limit_id, {"win": win, "ts": ts, "limitId": limit_id, "seen": []})
                    if ts is not None and (bucket["ts"] is None or ts > bucket["ts"]):
                        bucket["win"], bucket["ts"] = win, ts
                    end = window_end(win, ts)
                    if ts is not None and end is not None:
                        bucket["seen"].append((ts, end))
        except OSError:
            continue
        finally:
            lines.close()
    return {"tokens": tokens,
            "windows": {slot: pick_live_window(buckets)
                        for slot, buckets in windows.items() if buckets},
            "credits": credits[1] if credits else None,
            "lastActivity": last_activity}


def parse_credits(raw):
    """เครดิตจากก้อน rate_limits — โควตาส่วนที่ใช้ต่อได้หลังชนเพดานแผน

    คนละเรื่องกับ % จึงห้ามยุบรวมกัน · balance เป็น string ในล็อก อ่านไม่ออกเมื่อไหร่
    ให้คืน None ไปเลย ดีกว่าเดาเป็น 0 ซึ่งอ่านว่า "หมดแล้ว" ทั้งที่แปลว่า "ไม่รู้"
    """
    if not isinstance(raw, dict):
        return None
    try:
        balance = float(raw.get("balance"))
    except (TypeError, ValueError):
        return None
    return {"balance": balance, "unlimited": bool(raw.get("unlimited"))}


def pick_live_window(buckets):
    """ถังที่ยังเดินจริงชนะถังที่ไม่มีวันหมด แม้ตัวหลังจะใหม่กว่า

    เคสจริง 2026-09-10: อัปเดต Codex CLI แล้ว session ใหม่รายงาน limit_id "codex"
    พร้อมเลขจริง แต่ session เก่าที่เปิดค้างมา 24 ชั่วโมงยังพ่น codex_bengalfox
    (ช่องเปล่า) ต่อไปเรื่อยๆ record ของมันจึงใหม่กว่าเสมอ — กติกา "เอาใหม่สุด"
    อย่างเดียวเลยได้ขยะทั้งที่ของดีอยู่ในมือแล้ว

    ถ้าทุกถังเป็นช่องเปล่าก็คืนตัวใหม่สุดตามเดิม แล้วให้ codex_fields รายงานว่า
    ตอบไม่ได้ — ไม่ใช่หน้าที่ของที่นี่จะตัดสินแทน
    """
    real, fake = [], []
    for entry in buckets.values():
        win = entry["win"]
        mins = win.get("window_minutes", win.get("windowMinutes"))
        (fake if window_never_elapses(entry["seen"], mins) else real).append(entry)
    pool = real or fake
    return max(pool, key=lambda e: e["ts"] or datetime.min.replace(tzinfo=timezone.utc))


SHORT_WINDOW_MINUTES = 400  # เกินนี้ถือเป็นหน้าต่างยาว (สัปดาห์) ไม่ใช่บล็อก 5 ชม.


def window_end(win, base_ts):
    """เวลาสิ้นสุดของหน้าต่าง — แยกจาก window_from_limit เพราะการเฝ้าดูว่าหน้าต่าง
    เดินจริงไหม ไม่ต้องรอให้มี used_percent

    เวลารีเซ็ตมาได้สามแบบ: resets_at (epoch สัมบูรณ์ — รูปที่ Codex ใช้ตอนนี้),
    resets_in_seconds (รูปเก่า นับจากเวลาของ record) หรือไม่บอกเลย ถ้าไม่บอก
    ก็อนุมานขอบบนจากความยาวหน้าต่าง — หน้าต่างยาว W นาทีที่เห็นตอน ts วิ่งต่อ
    ได้ไม่เกิน ts+W ทุกหน้าต่างจึงมีวันหมดอายุ ไม่มีเลขไหนค้างจอได้ตลอดกาล
    """
    if not isinstance(win, dict):
        return None
    mins = win.get("window_minutes", win.get("windowMinutes"))
    resets_at = win.get("resets_at", win.get("resetsAt"))
    resets_in = win.get("resets_in_seconds", win.get("resetsInSeconds"))
    if isinstance(resets_at, (int, float)):
        return datetime.fromtimestamp(float(resets_at), timezone.utc)
    if resets_in is not None and base_ts:
        return base_ts + timedelta(seconds=float(resets_in))
    if mins and base_ts:
        return base_ts + timedelta(minutes=float(mins))
    return None


# ต้องเห็นห่างกันอย่างน้อยเท่านี้ก่อนจะกล้าฟันธง — ถามหน้าต่างจริงสองครั้งห่างกัน
# ไม่กี่วินาทีก็ได้คำตอบ "เหลือเท่าเดิม" โดยไม่ได้แปลว่ามันไม่เดิน
PLACEHOLDER_MIN_SPAN_MINUTES = 15
# เวลาผ่านไป span นาที หน้าต่างจริงต้องเหลือน้อยลงราว span นาทีเท่ากัน ถ้าลดไม่ถึง
# ครึ่งของเวลาที่ผ่านไป แปลว่าเส้นตายถูกเลื่อนตามนาฬิกา ไม่ใช่ปักไว้กับที่
#
# วัดแบบนี้ไม่ต้องรอให้หน้าต่างหมดอายุ ซึ่งจำเป็นกับหน้าต่างสัปดาห์ — กฎที่ขอเห็น
# ครึ่งหนึ่งของหน้าต่างก่อนแปลว่าต้องเฝ้าดู 3 วันครึ่งถึงจะรู้ว่ามันปลอม
PLACEHOLDER_MAX_DRIFT = 0.5


def window_never_elapses(observations, window_minutes):
    """จริงเมื่อหน้าต่างตอบว่า "เหลืออีกเต็มจำนวน" ทุกครั้งที่ถูกถาม

    เคสจริง 2026-09-10: หลังเปลี่ยนแผน Codex ออก limit_id ใหม่ (`codex_bengalfox`
    / GPT-5.3-Codex-Spark) ที่รายงาน used_percent 0.0 ค้างตลอด 129 record ใน
    5 ชั่วโมงครึ่งที่ใช้ไป 17 ล้าน token ตัวแยกที่ชัดกว่าตัวเลข % คือเวลารีเซ็ต:

        codex (ถังจริง)   resets_at คงที่  → เหลือ 290.5 → 289.6 → 288.9 นาที
        codex_bengalfox   resets_at ไหลขึ้น → เหลือ 299.8 → 299.4 → 299.8 นาที

    เทียบ "เวลาที่ผ่านไป" กับ "เวลาที่เหลือลดลง" แทนการรอให้หน้าต่างหมดอายุ —
    หน้าต่างสัปดาห์ของถังปลอมจึงถูกจับได้ในไม่กี่สิบนาที ไม่ต้องรอสามวันครึ่ง

    หน้าต่างที่ไม่มีวันหมดคือหน้าต่างที่ไม่มีอยู่จริง เอา 0% ของมันไปวาดเป็นแถบทึบ
    เท่ากับบอกผู้ใช้ว่า "ยังไม่ได้ใช้เลย" ทั้งที่ความจริงคือ "ไม่มีใครนับให้"

    observations = [(ts ของ record, เวลาสิ้นสุดที่ record นั้นอ้าง)]
    """
    if not window_minutes or len(observations) < 2:
        return False
    pairs = [(ts, end) for ts, end in observations if ts is not None and end is not None]
    if len(pairs) < 2:
        return False
    stamps = [ts for ts, _ in pairs]
    span = (max(stamps) - min(stamps)).total_seconds() / 60.0
    if span < PLACEHOLDER_MIN_SPAN_MINUTES:
        return False   # ยังดูไม่นานพอ — ห้ามด่วนสรุปว่าถังนี้ใช้ไม่ได้
    remaining = [(end - ts).total_seconds() / 60.0 for ts, end in pairs]
    return (max(remaining) - min(remaining)) < span * PLACEHOLDER_MAX_DRIFT


def window_from_limit(win, base_ts):
    """หน้าต่างหนึ่งอันจาก rate_limits ของ Codex"""
    if not isinstance(win, dict):
        return None
    pct = win.get("used_percent", win.get("usedPercent"))
    if pct is None:
        return None
    mins = win.get("window_minutes", win.get("windowMinutes"))
    label = ("5 ชม." if mins and mins <= SHORT_WINDOW_MINUTES
             else ("สัปดาห์" if mins else "หน้าต่าง"))
    return {"pct": float(pct), "end": window_end(win, base_ts),
            "label": label, "minutes": mins}


def codex_fields(cs, now):
    """แปลงหน้าต่างของ Codex เป็นฟิลด์ของ item — แยกจาก collect() ให้เทสต์ได้ตรงๆ

    จัดแถวตามความยาวหน้าต่างจริง ไม่ใช่ตำแหน่ง primary/secondary — Codex ย้าย
    weekly มาไว้ที่ primary แล้ว (secondary กลายเป็น null) ถ้ายังยึดตำแหน่ง
    เลขสัปดาห์จะไปโผล่ในแถว "5h" ของ popover ซึ่งเป็นคนละเรื่องกัน
    """
    out = {"pct": None, "confidence": None, "weekPct": None, "weekConfidence": None,
           "resetAt": None, "weekResetAt": None, "window": "5 ชม."}
    picked = {}
    for slot in ("primary", "secondary"):
        entry = (cs.get("windows") or {}).get(slot)
        if not isinstance(entry, dict):
            continue
        win = window_from_limit(entry.get("win"), entry.get("ts"))
        if win is None:
            continue
        # ช่องเปล่าที่ตอบว่า "เหลืออีกเต็มจำนวน" ตลอด — มีตัวเลขก็จริงแต่ไม่ใช่การวัด
        if window_never_elapses(entry.get("seen") or [], win["minutes"]):
            win = dict(win, placeholder=True)
        key = "week" if (win["minutes"] or 0) > SHORT_WINDOW_MINUTES else "short"
        cur, ts = picked.get(key), entry.get("ts")
        if cur is None or (ts is not None and (cur[0] is None or ts > cur[0])):
            picked[key] = (ts, win)

    def resolved(w):
        """เลขที่ยังยืนยันได้ — หน้าต่างหมุนไปแล้วห้ามโชว์ของเก่าเป็นเลขสด"""
        if w.get("placeholder"):
            return None, "unsure"   # ไม่มีใครนับให้ ตอบไม่ได้ ห้ามอ่านเป็นศูนย์
        if w["end"] is None or now < w["end"]:
            return w["pct"], "valid"
        last = cs.get("lastActivity")
        if last is None or last < w["end"]:
            return 0.0, "zero"   # หน้าต่างใหม่ยังไม่มีใครแตะ = ศูนย์จริง ไม่ใช่ "ไม่รู้"
        return None, "unsure"    # ใช้ต่อหลังรีเซ็ตแต่ไม่มีเลขใหม่ — ตอบไม่ได้ ห้ามเดา

    short = picked.get("short")
    week = picked.get("week")
    if short:
        out["pct"], out["confidence"] = resolved(short[1])
        out["window"] = short[1]["label"]
    if week:
        out["weekPct"], out["weekConfidence"] = resolved(week[1])
        # แถว 7d มีเวลารีเซ็ตของตัวเอง — ช่อง resetAt ช่องเดียวถูกจองให้ 5h ที่มีเลข
        # อยู่แล้ว เวลาของสัปดาห์จึงเคยหายไปทั้งที่ log บอกมาครบ (เคสจริง 2026-08-31)
        out["weekResetAt"] = None if week[1].get("placeholder") else week[1]["end"]
        if not short:
            out["window"] = week[1]["label"]
    # เวลารีเซ็ตเกาะแถวที่มีเลขจริง — UI ตัดสินจาก pct == nil ต้องเลือกให้ตรงกัน
    # นาฬิกาที่ไม่มีวันเดินถึงศูนย์ไม่ควรขึ้นจอ — หน้าต่างปลอมจึงไม่ให้เวลารีเซ็ตเลย
    if short and out["pct"] is not None and not short[1].get("placeholder"):
        out["resetAt"] = short[1]["end"]
    elif week and not week[1].get("placeholder"):
        out["resetAt"] = week[1]["end"]
    elif short and not short[1].get("placeholder"):
        out["resetAt"] = short[1]["end"]
    return out


# ── config เริ่มต้น ─────────────────────────────────────────────────────────
def default_config():
    return {
        "titleMode": "worst",  # worst | all | compact
        "showCost": True,
        # ต้องเปิดเอง — ดูเหตุผลใน engine/tests/test_liveconsent.py
        "liveUsage": False,
        "claude": [
            {
                "label": a["label"],
                "dir": a["dir"],
                "profile": a["profile"],
                "budget5h": None,     # ใส่จำนวน token ที่เคยชนลิมิต แล้วจะได้ %
                "budgetWeek": None,
                "enabled": True,
            }
            for a in discover_claude_dirs()
        ],
        "codex": [{"label": "Codex", "dir": os.path.join(HOME, ".codex"), "enabled": True}],
        "manual": [
            {"id": "chatgpt", "label": "ChatGPT", "windowHours": 5, "step": 10},
            {"id": "qwen", "label": "Qwen", "windowHours": 24, "step": 10},
            {"id": "antigravity", "label": "Antigravity", "windowHours": 24, "step": 10},
        ],
    }


def load_config():
    cfg = read_json(CFG_PATH, None)
    if cfg is None:
        cfg = default_config()
        write_json(CFG_PATH, cfg)
        return cfg
    # config ที่มีอยู่ก่อนคีย์นี้เกิด = เคยรัน live มาแล้วโดยเจ้าของเครื่องยอมรับ
    # ปิดให้เขาเงียบๆ คือการพังฟีเจอร์ที่ใช้อยู่ ส่วนคนที่ตั้ง False ไว้เองห้ามแตะ
    changed = False
    if "liveUsage" not in cfg:
        cfg["liveUsage"] = True
        changed = True
    # เจอ account ใหม่ที่เพิ่ง login ก็เติมเข้า config ให้เอง
    known = {os.path.realpath(a.get("dir", "")) for a in cfg.get("claude", [])}
    added = False
    for a in discover_claude_dirs():
        if os.path.realpath(a["dir"]) not in known:
            cfg.setdefault("claude", []).append(
                {"label": a["label"], "dir": a["dir"], "profile": a["profile"],
                 "budget5h": None, "budgetWeek": None, "enabled": True}
            )
            added = True
    if added or changed:
        write_json(CFG_PATH, cfg)
    return cfg


# ── ตัวนับแบบกรอกเอง (ChatGPT / Qwen / Antigravity) ─────────────────────────
def manual_state(entry, state):
    st = state.get(entry["id"]) or {}
    start = st.get("windowStart")
    pct = float(st.get("pct") or 0)
    end = None
    if start:
        end = datetime.fromtimestamp(start, timezone.utc) + timedelta(hours=entry.get("windowHours", 5))
        if now_utc() >= end:
            pct, end = 0.0, None
    return {"pct": pct, "end": end}


def handle_action(argv):
    state = read_json(STATE_PATH, {})
    cmd = argv[0]
    if cmd == "--bump":
        key, amount = argv[1], float(argv[2])
        st = state.get(key) or {}
        cfg = load_config()
        entry = next((m for m in cfg.get("manual", []) if m["id"] == key), {"windowHours": 5})
        cur = manual_state(entry, state)
        st["pct"] = max(0.0, min(100.0, cur["pct"] + amount))
        st["windowStart"] = st.get("windowStart") or time.time()
        if cur["end"] is None:
            st["windowStart"] = time.time()
        state[key] = st
    elif cmd == "--reset":
        state.pop(argv[1], None)
    write_json(STATE_PATH, state)



# ── เก็บข้อมูลเป็น JSON ให้ widget อ่าน ─────────────────────────────────────
SNAPSHOT_PATH = os.path.join(HOME, "Library", "Application Support", "AIUsage", "snapshot.json")


CONTRACT_DEFAULTS = {
    "pctSource": None, "confidence": None, "dataFetchedAt": None,
    "severity": None, "activeLimit": None, "error": None, "local": False,
    "weekConfidence": None, "weekResetAt": None,
    "costKnown": False, "costCurrency": None,
    "costSource": None, "costEstimated": False, "costKind": None,
    "modelWindows": [],
    # เครดิต = โควตาส่วนที่ใช้ต่อได้หลังชนเพดานแผน · None คือถังนี้ไม่มีแนวคิดนี้
    # ต่างจาก 0.0 ที่แปลว่า "มีแนวคิดนี้แต่หมดแล้ว"
    "credits": None, "creditsUnlimited": False,
    # ใบรีเซ็ตลิมิตที่ยังไม่หมดอายุ · None = ถังนี้ไม่มีแนวคิดนี้
    "limitResets": None, "limitResetExpiresAt": None,
}


def utilization_fields(util, last_activity, now):
    """แปลง Utilization เป็นฟิลด์ของ item — แยกจาก collect() ให้เทสต์ได้ตรงๆ

    weekPct คือหน้าต่างรวมทุกโมเดล (weekly_all) — gauge เฉพาะโมเดลอย่าง Fable
    แยกออกมาเป็น modelWindows ไม่ถูก max() กลืนเข้าไปใน 7d อีกต่อไป
    """
    out = {"pct": None, "confidence": None, "weekPct": None, "weekConfidence": None,
           "pctSource": None, "severity": None, "activeLimit": None,
           "resetAt": None, "weekResetAt": None, "modelWindows": []}
    session = next((w for w in util.windows if w.kind == "session"), None)
    weeklies = [w for w in util.windows if w.kind.startswith("weekly")]
    unscoped = [w for w in weeklies if not w.scope]
    weekly_all = max(unscoped or weeklies, key=lambda w: w.percent, default=None)

    active = next((w for w in util.windows if w.is_active), None)
    if active is not None:
        out["severity"], out["activeLimit"] = active.severity, active.scope or active.kind
    else:
        worst_week = max(weeklies, key=lambda w: w.percent, default=None)
        if worst_week is not None:
            out["severity"] = worst_week.severity

    def resolved(window):
        conf = _util.window_confidence(window, util.fetched_at, last_activity, now)
        pct = 0.0 if conf == _util.CONFIRMED_ZERO else window.percent
        return (None if conf == _util.UNSURE else pct), conf

    if session is not None:
        out["pct"], out["confidence"] = resolved(session)
        out["pctSource"] = "official" if out["pct"] is not None else None
        out["resetAt"] = session.resets_at
    if weekly_all is not None:
        out["weekPct"], out["weekConfidence"] = resolved(weekly_all)
        # session รีเซ็ตทุก 5 ชม. — แถว 7d ยืมเวลานั้นมาใช้ไม่ได้ ต้องมีของตัวเอง
        out["weekResetAt"] = weekly_all.resets_at
    for w in weeklies:
        if not w.scope or w is weekly_all:
            continue
        pct, conf = resolved(w)
        if pct is None:
            continue  # gauge ที่ไม่รู้ค่าไม่ต้องงอกเป็นแถวจุดประ
        out["modelWindows"].append({
            "label": w.scope, "pct": round(pct, 1), "confidence": conf,
            "resetAt": (w.resets_at.isoformat().replace("+00:00", "Z")
                        if w.resets_at else None),
        })
    if out["pctSource"] is None and out["weekPct"] is not None:
        out["pctSource"] = "official"
    return out


def with_contract(item):
    for key, value in CONTRACT_DEFAULTS.items():
        item.setdefault(key, value)
    return item



def token_plan_hits(config_dir, since):
    """หา 429 ของ token-plan (Qwen Cloud) → {'5h': reset_dt, 'week': reset_dt}

    กรองเฉพาะ record ที่เป็น API error จริง (error=="rate_limit", ไม่ transient)
    ข้อความเดียวกันที่ถูกเล่าซ้ำในบทสนทนาจะไม่ใช่ record แบบนี้ จึงไม่ปนเข้ามา

    คืน (merged, seen_at): merged คือเวลารีเซ็ตล่าสุดต่อหน้าต่าง ส่วน seen_at คือ
    เวลาที่เห็นคำประกาศครั้งล่าสุด — เป็นคนละเรื่องกับเวลาที่สแกนเจอ
    """
    pattern = os.path.join(config_dir, "projects", "**", "*.jsonl")
    cutoff = since.timestamp() - 3600
    found = []
    seen_at = {}
    for path in glob.iglob(pattern, recursive=True):
        if "/subagents/" in path or "/tool-results/" in path:
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            fh = open(path, "r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if "token-plan" not in line or '"rate_limit"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("error") != "rate_limit" or rec.get("apiErrorIsTransient") is not False:
                    continue
                ts = parse_ts(rec.get("timestamp"))
                if ts is None or ts < since:
                    continue
                msg = rec.get("message") or {}
                text = msg.get("content")
                if isinstance(text, list):
                    text = " ".join(b.get("text", "") for b in text if isinstance(b, dict))
                hit = _q429.parse_hit(text, ts)
                if hit:
                    found.append(hit)
                    window = hit[0]
                    if window not in seen_at or ts > seen_at[window]:
                        seen_at[window] = ts
    return _q429.merge_hits(found), seen_at


def parse_qwen_anchor(raw):
    """จุดยึดจากแดชบอร์ด Qwen — "% ที่ใช้ไปแล้ว ณ เวลาหนึ่ง" ในหน้าต่างสัปดาห์ปัจจุบัน

    dashboard เป็น cookie-auth ดึงอัตโนมัติไม่ได้ ผู้ใช้จดค่ามาให้เป็นครั้งคราว
    ค่านี้เป็น lower bound แท้ๆ ของปัจจุบัน (โควตามีแต่ใช้เพิ่ม ไม่มีคืน)
    จนกว่าหน้าต่างจะรีเซ็ต — ตรงกับ semantics "lower_bound" ที่ UI มีอยู่แล้ว
    """
    if not isinstance(raw, dict):
        return None
    used = raw.get("weeklyUsedPct")
    at = parse_ts(raw.get("at"))
    reset = parse_ts(raw.get("resetAt"))
    if not isinstance(used, (int, float)) or at is None or reset is None:
        return None
    return {"usedPct": float(used), "at": at, "resetAt": reset}


def bucket_rows(acc, table, qwen_anchor=None):
    """แยก traffic ที่ไม่ใช่ Anthropic ตาม endpoint ของถังโควตา"""
    since = now_utc() - timedelta(days=WEEK_DAYS)
    entries = claude_entries(acc["dir"], since)
    grouped = {}
    for row in entries:
        if not _buckets.is_real_model(row[2]):
            continue  # <synthetic> ไม่ใช่ provider อย่าให้มันงอกเป็นถัง
        bucket = _buckets.bucket_for_model(row[2], table)
        if bucket.key == _buckets.ANTHROPIC.key:
            continue
        grouped.setdefault(bucket, []).append(row)

    now = now_utc()
    hits, hits_seen_at = token_plan_hits(acc["dir"], since)

    # ถังที่ exhausted ห้ามหายเพียงเพราะไม่มี traffic — โควตาเต็มแปลว่าใช้ไม่ได้
    # แปลว่าจะไม่มี traffic ใหม่โดยธรรมชาติ ยิ่งเต็มนานยิ่งเสี่ยงหายจากจอ
    # (anchor ไม่เสกถัง — bucket_rows รันทุกบัญชี ถ้าเสกจะได้ถัง Qwen ซ้ำ
    # ทุกบัญชีทั้งที่แผนมีใบเดียว เคยพลาดมาแล้ว: 4.8% โผล่ 4 แถว)
    anchor_active = qwen_anchor is not None and qwen_anchor["resetAt"] > now
    if any(reset > now for reset in hits.values()):
        for bucket in set(table.values()):
            if bucket.name == "Qwen Cloud":
                grouped.setdefault(bucket, [])

    out = []
    for bucket, rows in sorted(grouped.items(), key=lambda pair: pair[0].name):
        week = summarize(rows)
        block = current_block(rows)
        block_summary = summarize(block["entries"]) if block else None
        known = costs_known(rows)

        # 429 ของ token-plan คือคำประกาศจากผู้ให้บริการเอง — หน้าต่างนั้น 100%
        # จนกว่าจะถึงเวลารีเซ็ต (ตรวจกับ dashboard แล้วเวลาตรงเป๊ะ)
        pct = week_pct = None
        reset_at = None
        conf = week_conf = None
        source = None
        fetched_at = None
        if bucket.name == "Qwen Cloud":
            hit_5h = hits.get("5h")
            hit_week = hits.get("week")
            if hit_5h and hit_5h > now:
                pct, conf, reset_at = 100.0, "valid", hit_5h
                fetched_at = hits_seen_at.get("5h")
            if hit_week and hit_week > now:
                week_pct, week_conf = 100.0, "valid"
                if reset_at is None:
                    reset_at = hit_week
                week_seen = hits_seen_at.get("week")
                if week_seen and (fetched_at is None or week_seen > fetched_at):
                    fetched_at = week_seen
            if pct is not None or week_pct is not None:
                source = "official"
            # ไม่มี 429 สดๆ ให้เชื่อ → ใช้จุดยึดจากแดชบอร์ด (lower bound ไม่ใช่ทางการ)
            if week_pct is None and anchor_active and now >= qwen_anchor["at"]:
                week_pct, week_conf = min(100.0, qwen_anchor["usedPct"]), "lower_bound"
                fetched_at = qwen_anchor["at"]
                if reset_at is None:
                    reset_at = qwen_anchor["resetAt"]

        out.append(with_contract({
            "group": bucket.name,
            "label": acc["label"],
            "window": "5 ชม.",
            "local": bucket.local,
            "pct": pct,
            "pctSource": source,
            "confidence": conf,
            "weekConfidence": week_conf,
            # เวลาที่ "เห็นคำประกาศจากผู้ให้บริการ" ไม่ใช่เวลาที่สแกนรอบล่าสุด
            "dataFetchedAt": fetched_at.isoformat().replace("+00:00", "Z") if fetched_at else None,
            "pctEstimated": False,
            "tokens": block_summary["tokens"] if block_summary else 0,
            # ไม่รู้ราคา → None ไม่ใช่ 0.0 · ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี"
            "cost": round(block_summary["cost"], 2) if (known and block_summary) else None,
            "calls": block_summary["calls"] if block_summary else 0,
            "resetAt": (reset_at.isoformat().replace("+00:00", "Z") if reset_at
                        else (block["end"].isoformat().replace("+00:00", "Z") if block else None)),
            "weekTokens": week["tokens"],
            "weekCost": round(week["cost"], 2) if known else None,
            "weekPct": week_pct,
            "profile": acc.get("profile"),
            "plan": None,
            "costKnown": known,
            "costCurrency": "USD" if known else None,
            "costSource": "anthropic_public_rate" if known else None,
            "costEstimated": known,
        }))
    return out


def split_live_usage_flag(argv):
    """แยก --live-usage=0|1 ออกจาก argv — คืน (argv ที่เหลือ, override หรือ None)

    แอปเก็บสวิตช์ความยินยอมไว้ใน UserDefaults ของตัวเองแล้วส่งมาทาง argv แทนการ
    เขียน config.json เพราะเอนจินก็เขียนไฟล์นั้นเองตอนเจอบัญชีใหม่ สองฝั่งเขียน
    พร้อมกันเมื่อไหร่จะมีฝั่งหนึ่งหาย และการหายของสวิตช์นี้แปลว่ามันเงียบๆ กลับไป
    แตะ Keychain ได้เอง
    """
    override, rest = None, []
    for arg in argv:
        if arg.startswith("--live-usage="):
            override = arg.split("=", 1)[1] not in ("0", "false", "no", "")
        else:
            rest.append(arg)
    return rest, override


def effective_live_usage(cfg, override=None):
    """สวิตช์จากแอปชนะไฟล์ config — ไม่มีทั้งคู่ถือว่าปิด"""
    if override is not None:
        return override
    return bool(cfg.get("liveUsage", False))


def parse_codex_resets(raw):
    """ใบรีเซ็ตลิมิตที่จดมาจากหน้า usage ของ OpenAI — คืนวันหมดอายุ เรียงใบที่จะหมดก่อน

    ใบรีเซ็ตคือทางออกตอนชนเพดาน กดแล้วโควตากลับมาเต็ม แต่มีวันหมดอายุ ใช้ไม่ทัน
    ก็หายไปเฉยๆ · ไม่มีแหล่งในเครื่องเลย ไม่อยู่ในล็อก ไม่อยู่ใน sqlite ของ Codex
    จึงต้องจดมาเหมือน codexAnchor

    รูปแบบ: {"expiring": ["2026-10-04T01:06:00Z", "2026-10-04T22:41:00Z"]}
    """
    if not isinstance(raw, dict):
        return None
    stamps = [parse_ts(x) for x in (raw.get("expiring") or []) if isinstance(x, str)]
    stamps = sorted(x for x in stamps if x is not None)
    return stamps or None


def live_codex_resets(resets, now):
    """เฉพาะใบที่ยังใช้ได้ — ใบที่เลยเวลาแล้วหายไปเอง ไม่ต้องรอใครมาลบ"""
    return [x for x in (resets or []) if x > now]


def parse_codex_anchor(raw):
    """จุดยึดโควตา Codex จากหน้า usage ของ OpenAI — พี่น้องกับ parse_qwen_anchor

    หลังเปลี่ยนแผน rate_limits ในล็อกกลายเป็นช่องเปล่า (0% ค้าง เวลารีเซ็ตเลื่อนตาม
    นาฬิกา) แต่หน้าเว็บยังบอกตัวเลขจริงอยู่ และเทียบกลับจาก token ก็ไม่ได้ เพราะ
    อัตรา token ต่อ 1% ที่วัดจากล็อกของแผนเก่าไหลจาก 443k ลงไป 375k (คลาด ~15%)
    แปลว่า % ที่ OpenAI นับไม่ได้ผูกกับ token ตรงๆ การเสกสูตรขึ้นมาเองจึงเป็นการเดา

    ค่าที่จดมาเป็น lower bound แท้ๆ ของปัจจุบัน — โควตามีแต่ใช้เพิ่ม ไม่มีคืน
    จนกว่าหน้าต่างจะรีเซ็ต ตรงกับ semantics "lower_bound" ที่ UI มีอยู่แล้ว

    รูปแบบ (ทั้งสองหน้าต่างเป็น optional):
        {"at": "...Z",
         "session": {"usedPct": 12, "resetAt": "...Z"},
         "weekly":  {"usedPct": 33, "resetAt": "...Z"}}
    """
    if not isinstance(raw, dict):
        return None
    at = parse_ts(raw.get("at"))
    if at is None:
        return None

    def window(key):
        w = raw.get(key)
        if not isinstance(w, dict):
            return None
        used = w.get("usedPct")
        reset = parse_ts(w.get("resetAt"))
        # ไม่มีเวลารีเซ็ต = ไม่มีวันหมดอายุ ซึ่งคือสิ่งที่ window_never_elapses เพิ่งกันไว้
        if not isinstance(used, (int, float)) or reset is None:
            return None
        return {"usedPct": float(used), "resetAt": reset}

    session, weekly = window("session"), window("weekly")
    if session is None and weekly is None:
        return None
    return {"at": at, "session": session, "weekly": weekly}


def apply_codex_anchor(fields, anchor, now):
    """เติมจุดยึดเฉพาะช่องที่ล็อกตอบไม่ได้ — เลขทางการชนะเสมอ"""
    if anchor is None or now < anchor["at"]:
        return fields
    pairs = (("session", "pct", "confidence", "resetAt"),
             ("weekly", "weekPct", "weekConfidence", "weekResetAt"))
    for key, pct_key, conf_key, reset_key in pairs:
        win = anchor.get(key)
        if win is None or now >= win["resetAt"]:
            continue          # หน้าต่างหมุนไปแล้ว ค่าที่จดไว้เป็นของรอบเก่า
        if fields.get(pct_key) is not None:
            continue          # OpenAI ตอบเองได้ ไม่ต้องพึ่งของที่จดมา
        fields[pct_key] = min(100.0, win["usedPct"])
        fields[conf_key] = "lower_bound"
        fields[reset_key] = win["resetAt"]
    return fields


def collect(live_override=None):
    """รวบรวมสถานะทุกบัญชีเป็นโครงสร้างเดียว ใช้ได้ทั้งเมนูบาร์และ widget"""
    cfg = load_config()
    live_enabled = effective_live_usage(cfg, live_override)
    state = read_json(STATE_PATH, {})
    items = []
    bucket_table = _buckets.load_bucket_table()
    now = now_utc()

    for acc in cfg.get("claude", []):
        if not acc.get("enabled", True):
            continue
        try:
            st = claude_account_stats(acc, live_enabled)
        except Exception as exc:  # noqa: BLE001
            items.append(with_contract({
                "group": "Claude Code", "label": acc["label"], "window": "5 ชม.",
                "pct": None, "pctEstimated": False,
                "tokens": 0, "cost": None, "calls": 0, "resetAt": None,
                "weekTokens": 0, "weekCost": None, "weekPct": None,
                "profile": acc.get("profile"), "plan": None,
                "error": ("%s: %s" % (type(exc).__name__, exc))[:120],
            }))
            continue

        block, week = st["block"], st["week"]
        util = st.get("utilization")
        pct = week_pct = None
        week_confidence = None
        pct_source = confidence = fetched_at = severity = active_limit = None
        model_windows = []
        reset_at = block["end"] if block else None
        week_reset_at = None
        if util:
            fetched_at = util.fetched_at.isoformat().replace("+00:00", "Z")
            uf = utilization_fields(util, st.get("lastActivity"), now)
            pct, confidence = uf["pct"], uf["confidence"]
            week_pct, week_confidence = uf["weekPct"], uf["weekConfidence"]
            pct_source = uf["pctSource"]
            severity, active_limit = uf["severity"], uf["activeLimit"]
            model_windows = uf["modelWindows"]
            week_reset_at = uf["weekResetAt"]
            if uf["resetAt"] is not None:
                reset_at = uf["resetAt"]

        items.append(with_contract({
            "group": "Claude Code", "label": acc["label"], "window": "5 ชม.",
            "pct": round(pct, 1) if pct is not None else None,
            "pctEstimated": False, "tokens": block["tokens"] if block else 0,
            # ไม่รู้ราคา → None ไม่ใช่ 0.0 · ศูนย์ที่แปลว่า "ไม่รู้" อ่านเป็น "ฟรี"
            "cost": round(block["cost"], 2) if (st.get("costKnown") and block) else None,
            "calls": block["calls"] if block else 0, "resetAt": reset_at.isoformat().replace("+00:00", "Z") if reset_at else None,
            "weekTokens": week["tokens"],
            "weekCost": round(week["cost"], 2) if st.get("costKnown") else None,
            "weekPct": round(week_pct, 1) if week_pct is not None else None,
            "profile": acc.get("profile"), "plan": st.get("plan"),
            "pctSource": pct_source, "confidence": confidence, "dataFetchedAt": fetched_at,
            "severity": severity, "activeLimit": active_limit,
            "weekConfidence": week_confidence,
            "weekResetAt": (week_reset_at.isoformat().replace("+00:00", "Z")
                            if week_reset_at else None),
            "modelWindows": model_windows,
            "costKnown": bool(st.get("costKnown")),
            "costCurrency": "USD" if st.get("costKnown") else None,
            "costSource": "anthropic_public_rate" if st.get("costKnown") else None,
            "costEstimated": bool(st.get("costKnown")),
            # บัญชี subscription จ่ายเหมาไปแล้ว ตัวเลขนี้คือ "มูลค่าถ้ายิงผ่าน API"
            # ไม่ใช่บิล — UI ต้องไม่แสดงเหมือนเงินที่ไหลออกจริง
            "costKind": "notional" if (st.get("plan") and st.get("costKnown")) else None,
        }))
        try:
            items.extend(bucket_rows(acc, bucket_table,
                                     parse_qwen_anchor(cfg.get("qwenWeeklyAnchor"))))
        except Exception:  # noqa: BLE001
            pass

    for c in cfg.get("codex", []):
        if not c.get("enabled", True) or not os.path.isdir(c.get("dir", "")):
            continue
        try:
            cs = codex_stats(c["dir"])
        except Exception:  # noqa: BLE001
            cs = None
        if not cs:
            continue
        cf = apply_codex_anchor(codex_fields(cs, now),
                                parse_codex_anchor(cfg.get("codexAnchor")), now)
        configured = parse_codex_resets(cfg.get("codexLimitResets"))
        codex_resets = live_codex_resets(configured, now) if configured is not None else None
        items.append(with_contract({
            "group": "Codex",
            "label": c.get("label", "Codex"),
            "window": cf["window"],
            "pct": round(cf["pct"], 1) if cf["pct"] is not None else None,
            "tokens": cs["tokens"],
            "cost": None,
            "calls": 0,
            "resetAt": cf["resetAt"].isoformat().replace("+00:00", "Z") if cf["resetAt"] else None,
            "weekTokens": cs["tokens"],
            "weekCost": None,
            "weekPct": round(cf["weekPct"], 1) if cf["weekPct"] is not None else None,
            "profile": None,
            "limitResets": len(codex_resets) if codex_resets is not None else None,
            "limitResetExpiresAt": (codex_resets[0].isoformat().replace("+00:00", "Z")
                                    if codex_resets else None),
            "credits": cs["credits"]["balance"] if cs.get("credits") else None,
            "creditsUnlimited": bool(cs["credits"]["unlimited"]) if cs.get("credits") else False,
            # % ของ Codex มาจาก rate_limits ที่ OpenAI ส่งกลับมาเอง — เป็นทางการ
            # เท่ากับของ Anthropic ความมั่นใจจึงต้องเดินตามอายุหน้าต่างเหมือนกัน
            # จุดยึดที่ผู้ใช้จดมาไม่ใช่ตัวเลขทางการ — lower_bound บอกที่มาไว้แล้ว
            "pctSource": ("official"
                          if ((cf["pct"] is not None and cf["confidence"] != "lower_bound")
                              or (cf["weekPct"] is not None
                                  and cf["weekConfidence"] != "lower_bound"))
                          else ("anchor" if (cf["pct"] is not None
                                             or cf["weekPct"] is not None) else None)),
            "confidence": cf["confidence"],
            "weekConfidence": cf["weekConfidence"],
            "weekResetAt": (cf["weekResetAt"].isoformat().replace("+00:00", "Z")
                            if cf["weekResetAt"] else None),
        }))

    for m in cfg.get("manual", []):
        cur = manual_state(m, state)
        items.append(with_contract({
            "group": "กรอกเอง",
            "label": m["label"],
            "window": "%d ชม." % m.get("windowHours", 5),
            "pct": round(cur["pct"], 1),
            "tokens": 0, "cost": None, "calls": 0,
            "resetAt": cur["end"].isoformat().replace("+00:00", "Z") if cur["end"] else None,
            "weekTokens": 0, "weekCost": None, "weekPct": None,
            "profile": None,
        }))

    # บอกสถานะจริงกลับไปให้ UI — สวิตช์อยู่ได้สองที่ (UserDefaults ของแอปกับ
    # config.json) หน้าตั้งค่าจึงเดาเองไม่ได้ว่าตอนนี้เปิดอยู่หรือเปล่า
    return {"generated": now_utc().isoformat().replace("+00:00", "Z"),
            "liveUsage": live_enabled,
            "items": [with_contract(item) for item in items]}


def write_snapshot(path=None, live_override=None):
    data = collect(live_override)
    target = path or SNAPSHOT_PATH
    if not data["items"]:
        old = read_json(target, None)
        if old and old.get("items"):
            return old
    write_json(target, data)
    return data


# ── การพิมพ์เมนู ────────────────────────────────────────────────────────────
def line(text, **attrs):
    parts = [clean(text)]
    for k, v in attrs.items():
        if v is None:
            continue
        parts.append("%s=%s" % (k, v))
    print(" | ".join(parts) if len(parts) > 1 else parts[0])


def action(text, args, indent="--"):
    params = " ".join("param%d=%s" % (i + 1, a) for i, a in enumerate(args))
    print("%s%s | bash=%s %s terminal=false refresh=true"
          % (indent, clean(text), SELF, params))


def main():
    argv, live_override = split_live_usage_flag(sys.argv[1:])
    if argv and argv[0] == "--snapshot":
        target = argv[1] if len(argv) > 1 else None
        data = write_snapshot(target, live_override)
        print("เขียน snapshot %d รายการ → %s" % (len(data["items"]), target or SNAPSHOT_PATH))
        return
    if argv and argv[0] == "--json":
        print(json.dumps(collect(live_override), ensure_ascii=False, indent=2))
        return
    if argv and argv[0].startswith("--"):
        handle_action(argv)
        return

    cfg = load_config()
    state = read_json(STATE_PATH, {})
    rows = []  # (label, pct, detail_lines)

    # ── Claude accounts ───────────────────────────────────────────────
    claude_rows = []
    for acc in cfg.get("claude", []):
        if not acc.get("enabled", True):
            continue
        try:
            st = claude_account_stats(acc, effective_live_usage(cfg))
        except Exception as e:  # noqa: BLE001 — เมนูต้องไม่พังทั้งอัน
            claude_rows.append((acc["label"], None, ["อ่านไม่ได้: %s" % e], acc, None, False))
            continue

        blk = st["block"]
        budget5h = acc.get("budget5h") or st.get("budget5hAuto")
        budget5h_auto = not acc.get("budget5h") and bool(st.get("budget5hAuto"))
        pct = None
        if blk and budget5h:
            pct = min(100.0, blk["tokens"] / float(budget5h) * 100)

        detail = []
        if blk:
            head = "5 ชม.  %s  %s" % (bar(pct), fmt_tokens(blk["tokens"]))
            if pct is not None:
                head += "  ~%.0f%%" % pct if budget5h_auto else "  %.0f%%" % pct
            detail.append((head, color_for(pct)))
            detail.append(("       รีเซ็ตใน %s · %d ครั้ง%s"
                           % (fmt_left(blk["end"] - now_utc()), blk["calls"],
                              "  $%.2f" % blk["cost"] if cfg.get("showCost", True) else ""), DIM))
        else:
            detail.append(("5 ชม.  ว่าง — ยังไม่เริ่มหน้าต่างใหม่", GREEN))

        wk = st["week"]
        wpct = min(100.0, wk["tokens"] / float(acc["budgetWeek"]) * 100) if acc.get("budgetWeek") else None
        wline = "7 วัน  %s  %s" % (bar(wpct), fmt_tokens(wk["tokens"]))
        if wpct is not None:
            wline += "  %.0f%%" % wpct
        detail.append((wline, color_for(wpct)))
        if cfg.get("showCost", True) and wk["cost"]:
            detail.append(("       มูลค่าประมาณ $%.2f" % wk["cost"], DIM))
        if st["last"]:
            detail.append(("       ใช้ล่าสุด %s ที่แล้ว" % fmt_left(now_utc() - st["last"]), DIM))

        claude_rows.append((acc["label"], pct if pct is not None else wpct, detail, acc, st.get("plan"), budget5h_auto))

    # ── Codex ─────────────────────────────────────────────────────────
    codex_rows = []
    for c in cfg.get("codex", []):
        if not c.get("enabled", True) or not os.path.isdir(c.get("dir", "")):
            continue
        try:
            cs = codex_stats(c["dir"])
        except Exception:  # noqa: BLE001
            cs = None
        if not cs:
            continue
        detail, top = [], None
        for slot in ("primary", "secondary"):
            entry = (cs.get("windows") or {}).get(slot) or {}
            w = window_from_limit(entry.get("win"), entry.get("ts"))
            if not w:
                continue
            top = w["pct"] if top is None else max(top, w["pct"])
            txt = "%-6s %s  %.0f%%" % (w["label"], bar(w["pct"]), w["pct"])
            if w["end"]:
                txt += "  ·  รีเซ็ตใน %s" % fmt_left(w["end"] - now_utc())
            detail.append((txt, color_for(w["pct"])))
        if not detail:
            detail.append(("ยังไม่พบข้อมูลลิมิตใน log — เปิด session สักครั้ง", DIM))
        detail.append(("       7 วัน %s tokens" % fmt_tokens(cs["tokens"]), DIM))
        codex_rows.append((c.get("label", "Codex"), top, detail))

    # ── ตัวนับกรอกเอง ─────────────────────────────────────────────────
    manual_rows = []
    for m in cfg.get("manual", []):
        cur = manual_state(m, state)
        manual_rows.append((m, cur))

    # ── หัวเมนูบาร์ ───────────────────────────────────────────────────
    all_pcts = [p for _, p, _, _, _, _ in claude_rows if p is not None]
    all_pcts += [p for _, p, _ in codex_rows if p is not None]
    all_pcts += [c["pct"] for _, c in manual_rows if c["pct"] > 0]
    mode = cfg.get("titleMode", "worst")

    if not all_pcts:
        line("AI ·", color=DIM, font="Menlo")
    elif mode == "all":
        chunks = []
        for label, p, _, _, _, _ in claude_rows:
            chunks.append("%s%s" % (label[:2].upper(), "%.0f" % p if p is not None else "·"))
        for label, p, _ in codex_rows:
            chunks.append("CX%s" % ("%.0f" % p if p is not None else "·"))
        line(" ".join(chunks), color=color_for(max(all_pcts)), font="Menlo", size=12)
    else:
        worst = max(all_pcts)
        line("AI %.0f%%" % worst, color=color_for(worst), font="Menlo", size=13)

    print("---")

    if claude_rows:
        line("Claude Code", color=DIM, size=11)
        for label, pct, detail, acc, plan, budget5h_auto in claude_rows:
            head = "  %s" % label
            if plan:
                head += "  ·  %s" % plan
            if pct is not None:
                head += "   ~%.0f%%" % pct if budget5h_auto else "   %.0f%%" % pct
            email = account_email(acc["dir"])
            line(head, color=color_for(pct) if pct is not None else None, font="Menlo")
            for txt, col in detail:
                line("--" + txt, color=col, font="Menlo", size=12)
            if email:
                line("-----")
                line("--" + email, color=DIM, size=11)
            if acc.get("profile"):
                print("--สลับมาใช้บัญชีนี้ (ccs) | bash=/bin/bash param1=-lc param2=\"ccs sw %s\" terminal=true refresh=true"
                      % acc["profile"])
            if not acc.get("budget5h"):
                if budget5h_auto:
                    line("--~% ประมาณจากที่เคยชนลิมิตจริง — ตั้ง budget5h เองเพื่อความแม่นยำ",
                         color=DIM, size=11)
                else:
                    line("--ตั้ง budget5h ใน config เพื่อดูเป็น % (หรือรอจนกว่าจะเคยชนลิมิตจริงสักครั้ง)",
                         color=DIM, size=11)

    if codex_rows:
        print("---")
        line("Codex", color=DIM, size=11)
        for label, pct, detail in codex_rows:
            head = "  %s" % label
            if pct is not None:
                head += "   %.0f%%" % pct
            line(head, color=color_for(pct) if pct is not None else None, font="Menlo")
            for txt, col in detail:
                line("--" + txt, color=col, font="Menlo", size=12)

    if manual_rows:
        print("---")
        line("กรอกเอง", color=DIM, size=11)
        for m, cur in manual_rows:
            pct = cur["pct"]
            txt = "  %-12s %s %3.0f%%" % (m["label"], bar(pct), pct)
            if cur["end"]:
                txt += "  %s" % fmt_left(cur["end"] - now_utc())
            line(txt, color=color_for(pct) if pct else DIM, font="Menlo")
            step = m.get("step", 10)
            for amount in (step, step * 2, step * 5):
                action("+%d%%" % amount, ["--bump", m["id"], str(int(amount))])
            action("เคลียร์", ["--reset", m["id"]])

    print("---")
    print("แก้ config… | bash=/usr/bin/open param1=%s terminal=false" % CFG_PATH)
    print("รีเฟรช | refresh=true")


if __name__ == "__main__":
    main()
