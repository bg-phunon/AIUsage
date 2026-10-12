"""อ่าน token usage ของ Muse จาก session logs ในเครื่อง — ไม่แตะ network/credentials

ที่มา: ``<data>/muse/sessions/YYYY/MM/DD/<id>/session.jsonl`` (รวม
``subagent/<id>/session.jsonl``) · record ที่นับคือ ``model_completed`` ใต้
``payload.event`` เท่านั้น — ``goal_usage_attribution`` คือยอดชุดเดียวกันที่
แยกตามเจ้าของ นับซ้ำแล้วจะเบิ้ล (ดู engine/tests/test_muse.py)

Muse ไม่มีโควตา/% — สิ่งเดียวที่วัดได้คือ token กับจำนวนครั้ง จึงไม่มี pct,
resetAt, หรือ costKnown ให้ฝั่ง UI วาดแถบ มีแต่ยอดวันนี้กับย้อนหลัง 7 วัน
"""

import json
import os
from datetime import datetime, timedelta, timezone


def default_sessions_dir(home=None):
    """data dir ของ Muse — เคารพ XDG_DATA_HOME แบบที่ตัว CLI ใช้เอง"""
    if home is None:
        home = os.path.expanduser("~")
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(data, "muse", "sessions")


def muse_token_total(usage):
    """ยอด token ต่อหนึ่ง model call

    input/output คือยอดรวม — ``cached_tokens``/``cache_read_tokens`` เป็นส่วนย่อย
    ของ input (เคสจริง: input 35510 ในนั้น cached 34289) และ ``reasoning_tokens``
    อยู่ใน output (130 ใน 325) บวกแยกแล้วจะนับซ้ำ
    """
    if not isinstance(usage, dict):
        return 0
    return int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)


def _iter_session_files(sessions_dir, cut_ts):
    """ไฟล์ session.jsonl ที่ยังมีสิทธิ์มี record ในหน้าต่าง — ไฟล์ที่แก้ครั้ง
    สุดท้ายก่อน cut ไม่มีวันมี record ใหม่กว่านั้น (muse เขียน log อย่างเดียว)"""
    if not sessions_dir or not os.path.isdir(sessions_dir):
        return
    for root, _dirs, files in os.walk(sessions_dir):
        if "session.jsonl" not in files:
            continue
        path = os.path.join(root, "session.jsonl")
        try:
            if os.path.getmtime(path) < cut_ts:
                continue
        except OSError:
            continue
        yield path


def _parse_completed(line):
    """คืน (record_id, ts_utc, usage, model) ของ model_completed หรือ None"""
    if '"model_completed"' not in line:
        return None
    try:
        rec = json.loads(line)
    except ValueError:
        return None
    if not isinstance(rec, dict) or rec.get("payload_type") != "runtime.session":
        return None
    payload = rec.get("payload")
    if not isinstance(payload, dict) or payload.get("kind") != "run":
        return None
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("kind") != "model_completed":
        return None
    try:
        ts = datetime.fromtimestamp(float(rec["recorded_at"]) / 1e6,
                                    tz=timezone.utc)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    return (rec.get("id"), ts, event.get("usage"), event.get("model"))


def _collect_completed(sessions_dir, cut_ts):
    """model_completed ทุก record ตั้งแต่ mtime cut — [(ts, tokens, model)]

    ตัดซ้ำด้วย envelope id ข้ามไฟล์ (log แม่กับ subagent เขียน event ชุดเดียวกันได้)
    """
    out = []
    seen = set()
    for path in _iter_session_files(sessions_dir, cut_ts):
        try:
            fh = open(path, "r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                parsed = _parse_completed(line)
                if parsed is None:
                    continue
                rid, ts, usage, model = parsed
                if rid is not None:
                    if rid in seen:
                        continue
                    seen.add(rid)
                out.append((ts, muse_token_total(usage), model))
    return out


def muse_series(sessions_dir, since):
    """[(ts, tokens)] เรียงตามเวลา ตั้งแต่ since — ไว้วัดอัตรา %/token ระหว่างจุดยึด"""
    cut_ts = since.timestamp() if since is not None else 0
    recs = [(ts, tok) for ts, tok, _ in _collect_completed(sessions_dir, cut_ts)]
    if since is not None:
        recs = [(ts, tok) for ts, tok in recs if ts >= since]
    recs.sort(key=lambda r: r[0])
    return recs


def muse_stats(sessions_dir, now, week_days=7, day_start=None):
    """ยอด Muse: วันนี้ (เที่ยงคืนท้องถิ่น) กับย้อนหลัง week_days วัน

    day_start มีไว้ให้เทสต์ปักเขตวันเอง — เรียกจริงปล่อย None ให้ใช้เที่ยงคืน
    ของเครื่องนี้ · นับซ้ำกันด้วย envelope id ข้ามไฟล์ (log แม่กับ subagent
    เขียน event ชุดเดียวกันได้)
    """
    if day_start is None:
        local = now.astimezone() if now.tzinfo is not None else now
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    cut = now - timedelta(days=week_days)
    today_tokens = today_calls = week_tokens = week_calls = 0
    models = []
    latest_model = None
    latest_ts = None
    for ts, total, model in _collect_completed(sessions_dir, cut.timestamp()):
        if ts < cut:
            continue
        week_tokens += total
        week_calls += 1
        if ts >= day_start:
            today_tokens += total
            today_calls += 1
        if isinstance(model, str) and model and model not in models:
            models.append(model)
        if latest_ts is None or ts >= latest_ts:
            latest_ts = ts
            latest_model = model if isinstance(model, str) else latest_model
    return {
        "today": {"tokens": today_tokens, "calls": today_calls},
        "week": {"tokens": week_tokens, "calls": week_calls},
        "model": latest_model,
        "models": sorted(models),
        # ไว้ให้ musetui ตัดสินว่ามีการใช้ใหม่หลังการถามครั้งก่อนไหม
        "latestAt": latest_ts,
    }
