"""แผนที่ชื่อโมเดล → ถังโควตา สร้างจาก ~/.ccs/*.settings.json"""

import glob
import ipaddress
import json
import os
from typing import Dict, NamedTuple, Optional
from urllib.parse import urlparse


class Bucket(NamedTuple):
    key: str
    name: str
    host: str
    local: bool


ANTHROPIC = Bucket("anthropic", "Claude", "api.anthropic.com", False)
UNKNOWN = Bucket("unknown", "ยังไม่รู้จัก", "", False)

# ชื่อที่ Claude Code ใส่แทนโมเดลจริงเมื่อข้อความไม่ได้เกิดจากการเรียก API
# ไม่ใช่ provider จึงต้องไม่กลายเป็นถังโควตา
NON_MODEL_NAMES = frozenset({"<synthetic>"})


def is_real_model(model: Optional[str]) -> bool:
    """True เมื่อชื่อนี้หมายถึงโมเดลจริงที่กินโควตาของใครสักคน"""
    if not isinstance(model, str):
        return False
    name = model.strip()
    return bool(name) and name.lower() not in NON_MODEL_NAMES

MODEL_ENV_KEYS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
)

HOST_NAMES = (
    ("anthropic.com", "Claude"),
    ("z.ai", "GLM"),
    ("bigmodel.cn", "GLM"),
    ("maas.aliyuncs.com", "Qwen Cloud"),
    ("dashscope.aliyuncs.com", "Qwen Cloud"),
    ("openai.com", "OpenAI"),
    ("moonshot.cn", "Kimi"),
    ("deepseek.com", "DeepSeek"),
)


def is_local_host(host: str) -> bool:
    if not host:
        return False
    bare = host.split(":")[0]
    if bare in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        return ipaddress.ip_address(bare).is_private
    except ValueError:
        return False


def _name_for_host(host: str, fallback: str) -> str:
    bare = host.split(":")[0]
    for suffix, name in HOST_NAMES:
        if bare == suffix or bare.endswith("." + suffix):
            return name
    return fallback


# endpoint แบบ token-plan ของ Alibaba — ประกาศเพดานผ่านข้อความ 429 (quota429.py)
TOKEN_PLAN_HOSTS = ("maas.aliyuncs.com", "dashscope.aliyuncs.com")


def is_token_plan(bucket: Bucket) -> bool:
    """True เมื่อถังนี้คือแผน token-plan ของ Alibaba ไม่ว่าผู้ใช้จะตั้งชื่อว่าอะไร"""
    bare = bucket.host.split(":")[0]
    return any(bare == s or bare.endswith("." + s) for s in TOKEN_PLAN_HOSTS)


def load_bucket_table(ccs_dir: Optional[str] = None,
                      names: Optional[Dict[str, str]] = None) -> Dict[str, Bucket]:
    """names คือชื่อที่ผู้ใช้ตั้งเองต่อโปรไฟล์ ccs (config ``bucketNames``)

    หลายโปรไฟล์ชี้ host เดียวกันได้ด้วย token คนละใบ = คนละโควตา (เคสจริง:
    ``qwenc`` กับ ``albb`` ใช้ token-plan เดียวกันคนละบัญชี) ชื่อจาก host จะชนกัน
    และ id ของแถว ("group/label") ชนตาม จึงต่อท้ายด้วยชื่อโปรไฟล์ให้เองถ้าไม่ได้ตั้ง
    """
    if ccs_dir is None:
        ccs_dir = os.path.join(os.path.expanduser("~"), ".ccs")
    names = names if isinstance(names, dict) else {}
    profiles = []
    for path in sorted(glob.glob(os.path.join(ccs_dir, "*.settings.json"))):
        key = os.path.basename(path)[: -len(".settings.json")]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                env = (json.load(fh) or {}).get("env") or {}
        except (OSError, ValueError):
            continue
        base = env.get("ANTHROPIC_BASE_URL") or ""
        host = urlparse(base).hostname or ""
        profiles.append((key, host, env))

    default_names = {key: _name_for_host(host, key) for key, host, _ in profiles}
    taken: Dict[str, int] = {}
    for key, name in default_names.items():
        if not (isinstance(names.get(key), str) and names[key].strip()):
            taken[name] = taken.get(name, 0) + 1

    table: Dict[str, Bucket] = {}
    for key, host, env in profiles:
        custom = names.get(key)
        if isinstance(custom, str) and custom.strip():
            name = custom.strip()
        elif taken.get(default_names[key], 0) > 1:
            name = "%s · %s" % (default_names[key], key)
        else:
            name = default_names[key]
        bucket = Bucket(key, name, host, is_local_host(host))
        for env_key in MODEL_ENV_KEYS:
            model = env.get(env_key)
            if isinstance(model, str) and model.strip():
                table[model.strip().lower()] = bucket
    return table


def bucket_for_model(model: Optional[str], table: Dict[str, Bucket]) -> Bucket:
    if not isinstance(model, str) or not model.strip():
        return UNKNOWN
    key = model.strip().lower()
    if key in table:
        return table[key]
    # Endpoint settings sometimes use a suffix (e.g. ``-code``) while
    # transcript records the provider's shorter model id.  Resolve only when
    # the relationship is an explicit token-boundary variant and all matches
    # agree on one bucket; this remains endpoint-based, not brand-based.
    variants = {
        bucket for configured, bucket in table.items()
        if configured.startswith(key + "-") or key.startswith(configured + "-")
    }
    if len(variants) == 1:
        return next(iter(variants))
    if key.startswith("claude-"):
        return ANTHROPIC
    return UNKNOWN
