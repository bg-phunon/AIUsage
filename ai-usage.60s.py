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

sys.path.insert(0, os.path.join(os.path.dirname(SELF), "engine"))
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


def claude_account_stats(acc):
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
        # สดก่อน แคชทีหลัง — endpoint ล่ม/token หมดอายุ/ผู้ใช้ Deny คีย์เชน
        # ทุกกรณีตกกลับมาที่พฤติกรรมเดิมโดยไม่มีอะไรพัง
        "utilization": _liveu.fetch_utilization(acc["dir"]) or _util.read_utilization(acc["dir"]),
        "lastActivity": entries[-1][0] if entries else None,
        "costKnown": costs_known(entries),
    }
    if blk:
        s = summarize(blk["entries"])
        s["start"], s["end"] = blk["start"], blk["end"]
        out["block"] = s
    return out


# ── อ่าน rollout ของ Codex ──────────────────────────────────────────────────
def codex_stats(codex_dir):
    """Codex เขียน rate_limits ที่เป็นเปอร์เซ็นต์จริงลง rollout log — ใช้ค่านั้นเลย"""
    files = []
    for pat in ("sessions/**/*.jsonl", "*.jsonl"):
        files += glob.glob(os.path.join(codex_dir, pat), recursive=True)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    tokens = 0
    limits = None
    limits_ts = None
    week_cut = now_utc() - timedelta(days=WEEK_DAYS)

    for path in files[:60]:
        try:
            if datetime.fromtimestamp(os.path.getmtime(path), timezone.utc) < week_cut:
                break
            fh = open(path, "r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if "token_count" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = parse_ts(rec.get("timestamp"))
                payload = rec.get("payload") or rec
                info = payload.get("info") or {}
                last = info.get("last_token_usage") or {}
                if ts and ts >= week_cut:
                    tokens += int(last.get("total_tokens") or 0)
                rl = payload.get("rate_limits") or info.get("rate_limits")
                if rl and (limits_ts is None or (ts and ts > limits_ts)):
                    limits, limits_ts = rl, ts
    return {"tokens": tokens, "limits": limits, "limits_ts": limits_ts}


def window_from_limit(win, base_ts):
    if not isinstance(win, dict):
        return None
    pct = win.get("used_percent", win.get("usedPercent"))
    if pct is None:
        return None
    resets = win.get("resets_in_seconds", win.get("resetsInSeconds"))
    end = None
    if resets is not None and base_ts:
        end = base_ts + timedelta(seconds=float(resets))
    mins = win.get("window_minutes", win.get("windowMinutes"))
    label = "5 ชม." if mins and mins <= 400 else ("สัปดาห์" if mins else "หน้าต่าง")
    return {"pct": float(pct), "end": end, "label": label}


# ── config เริ่มต้น ─────────────────────────────────────────────────────────
def default_config():
    return {
        "titleMode": "worst",  # worst | all | compact
        "showCost": True,
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
    if added:
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
    "weekConfidence": None, "costKnown": False, "costCurrency": None,
    "costSource": None, "costEstimated": False, "costKind": None,
}


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


def bucket_rows(acc, table):
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


def collect():
    """รวบรวมสถานะทุกบัญชีเป็นโครงสร้างเดียว ใช้ได้ทั้งเมนูบาร์และ widget"""
    cfg = load_config()
    state = read_json(STATE_PATH, {})
    items = []
    bucket_table = _buckets.load_bucket_table()
    now = now_utc()

    for acc in cfg.get("claude", []):
        if not acc.get("enabled", True):
            continue
        try:
            st = claude_account_stats(acc)
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
        reset_at = block["end"] if block else None
        if util:
            fetched_at = util.fetched_at.isoformat().replace("+00:00", "Z")
            last_activity = st.get("lastActivity")
            session = next((w for w in util.windows if w.kind == "session"), None)
            weekly = max((w for w in util.windows if w.kind.startswith("weekly")),
                         key=lambda w: w.percent, default=None)
            active = next((w for w in util.windows if w.is_active), None)
            if active is not None:
                severity, active_limit = active.severity, active.scope or active.kind
            elif weekly is not None:
                severity = weekly.severity
            if session is not None:
                confidence = _util.window_confidence(session, util.fetched_at, last_activity, now)
                pct = 0.0 if confidence == _util.CONFIRMED_ZERO else session.percent
                if confidence == _util.UNSURE:
                    pct = None
                pct_source = "official" if pct is not None else None
                reset_at = session.resets_at
            if weekly is not None:
                week_confidence = _util.window_confidence(weekly, util.fetched_at, last_activity, now)
                week_pct = 0.0 if week_confidence == _util.CONFIRMED_ZERO else weekly.percent
                if week_confidence == _util.UNSURE:
                    week_pct = None
            if pct_source is None and week_pct is not None:
                pct_source = "official"

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
            "costKnown": bool(st.get("costKnown")),
            "costCurrency": "USD" if st.get("costKnown") else None,
            "costSource": "anthropic_public_rate" if st.get("costKnown") else None,
            "costEstimated": bool(st.get("costKnown")),
            # บัญชี subscription จ่ายเหมาไปแล้ว ตัวเลขนี้คือ "มูลค่าถ้ายิงผ่าน API"
            # ไม่ใช่บิล — UI ต้องไม่แสดงเหมือนเงินที่ไหลออกจริง
            "costKind": "notional" if (st.get("plan") and st.get("costKnown")) else None,
        }))
        try:
            items.extend(bucket_rows(acc, bucket_table))
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
        limits = cs.get("limits") or {}
        prim = window_from_limit(limits.get("primary"), cs.get("limits_ts"))
        sec = window_from_limit(limits.get("secondary"), cs.get("limits_ts"))
        items.append(with_contract({
            "group": "Codex",
            "label": c.get("label", "Codex"),
            "window": prim["label"] if prim else "5 ชม.",
            "pct": round(prim["pct"], 1) if prim else None,
            "tokens": cs["tokens"],
            "cost": None,
            "calls": 0,
            "resetAt": prim["end"].isoformat().replace("+00:00", "Z") if prim and prim["end"] else None,
            "weekTokens": cs["tokens"],
            "weekCost": None,
            "weekPct": round(sec["pct"], 1) if sec else None,
            "profile": None,
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

    return {"generated": now_utc().isoformat().replace("+00:00", "Z"),
            "items": [with_contract(item) for item in items]}


def write_snapshot(path=None):
    data = collect()
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
    if len(sys.argv) > 1 and sys.argv[1] == "--snapshot":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        data = write_snapshot(target)
        print("เขียน snapshot %d รายการ → %s" % (len(data["items"]), target or SNAPSHOT_PATH))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        print(json.dumps(collect(), ensure_ascii=False, indent=2))
        return
    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        handle_action(sys.argv[1:])
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
            st = claude_account_stats(acc)
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
        limits = cs.get("limits") or {}
        for key in ("primary", "secondary"):
            w = window_from_limit(limits.get(key), cs.get("limits_ts"))
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
