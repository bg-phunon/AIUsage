"""แผนที่ชื่อโมเดล → ถังโควตา สร้างจากโปรไฟล์ api ของ ccs (config.yaml + *.settings.json)"""

import glob
import ipaddress
import json
import os
import re
from typing import Dict, NamedTuple, Optional
from urllib.parse import urlparse

from . import ccs as _ccs


class Bucket(NamedTuple):
    key: str
    name: str
    host: str
    local: bool
    path: str = ""          # path ของ ANTHROPIC_BASE_URL — BytePlus แยกแผนกับ pay-as-you-go ด้วย path


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
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
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
    ("xiaomimimo.com", "Xiaomi MiMo"),
    ("moonshot.ai", "Kimi"),
    ("kimi.com", "Kimi"),
    ("bytepluses.com", "BytePlus"),
    ("volces.com", "Volcengine"),
    ("minimax.io", "MiniMax"),
    ("minimaxi.com", "MiniMax"),
    ("openrouter.ai", "OpenRouter"),
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


class BucketTable(dict):
    """ชื่อโมเดล (ตัวเล็ก) → Bucket พร้อม ``pinned``: config dir → Bucket

    โปรไฟล์ที่ตั้ง ``CLAUDE_CONFIG_DIR`` ไว้ใน env ผูก instance นั้นเป็นของตัวเอง
    (เคสจริง: ``spark`` ชี้ ``instances/spark`` ผ่าน proxy LAN ที่เปลี่ยนชื่อโมเดล
    ตามใจ — log เขียน ``qwen3.8-27b`` ทั้งที่ settings บอก ``spark-code``)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pinned: Dict[str, Bucket] = {}


def _profile_paths(ccs_dir: str) -> Dict[str, str]:
    """{โปรไฟล์: path} — config.yaml ของ ccs ก่อน แล้วเติม *.settings.json ที่เหลือ

    ไฟล์ที่ไม่อยู่ใน config แล้วยังนับ เพราะ log เก่าของโปรไฟล์ที่ลบไปต้องยังเข้าถังถูก
    """
    paths = dict(_ccs.read_config(ccs_dir)["profiles"])
    known = {os.path.realpath(p) for p in paths.values()}
    for path in sorted(glob.glob(os.path.join(ccs_dir, "*.settings.json"))):
        key = os.path.basename(path)[: -len(".settings.json")]
        if os.path.realpath(path) not in known and key not in paths:
            paths[key] = path
    return paths


_CONTEXT_SUFFIX = re.compile(r"\[[^\]]*\]$")


def _model_keys(model: str):
    """ชื่อใน settings เช่น ``glm-5.2[1m]`` — log บันทึกแค่ ``glm-5.2``"""
    key = model.strip().lower()
    yield key
    bare = _CONTEXT_SUFFIX.sub("", key).strip()
    if bare and bare != key:
        yield bare


def _normalized(model: str) -> str:
    # BytePlus ตอบชื่อโมเดลแบบขีดแทนจุด: settings ``glm-5.3-flash`` → log ``glm-5-3-flash``
    return _CONTEXT_SUFFIX.sub("", model.strip().lower()).replace(".", "-").replace("_", "-")


def load_bucket_table(ccs_dir: Optional[str] = None,
                      names: Optional[Dict[str, str]] = None) -> BucketTable:
    """names คือชื่อที่ผู้ใช้ตั้งเองต่อโปรไฟล์ ccs (config ``bucketNames``)

    หลายโปรไฟล์ชี้ host เดียวกันได้ด้วย token คนละใบ = คนละโควตา (เคสจริง:
    ``qwenc`` กับ ``albb`` ใช้ token-plan เดียวกันคนละบัญชี) ชื่อจาก host จะชนกัน
    และ id ของแถว ("group/label") ชนตาม จึงต่อท้ายด้วยชื่อโปรไฟล์ให้เองถ้าไม่ได้ตั้ง
    """
    if ccs_dir is None:
        ccs_dir = _ccs.ccs_dir()
    names = names if isinstance(names, dict) else {}
    profiles = []
    for key, path in sorted(_profile_paths(ccs_dir).items()):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                env = (json.load(fh) or {}).get("env") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(env, dict):
            continue
        base = env.get("ANTHROPIC_BASE_URL") or ""
        parsed = urlparse(base) if isinstance(base, str) else None
        host = (parsed.hostname or "") if parsed else ""
        profiles.append((key, host, parsed.path if parsed else "", env))

    default_names = {key: _name_for_host(host, key) for key, host, _, _ in profiles}
    taken: Dict[str, int] = {}
    for key, name in default_names.items():
        if not (isinstance(names.get(key), str) and names[key].strip()):
            taken[name] = taken.get(name, 0) + 1

    table = BucketTable()
    for key, host, path, env in profiles:
        custom = names.get(key)
        if isinstance(custom, str) and custom.strip():
            name = custom.strip()
        elif taken.get(default_names[key], 0) > 1:
            name = "%s · %s" % (default_names[key], key)
        else:
            name = default_names[key]
        bucket = Bucket(key, name, host, is_local_host(host), path)
        for env_key in MODEL_ENV_KEYS:
            model = env.get(env_key)
            if isinstance(model, str) and model.strip():
                for model_key in _model_keys(model):
                    table[model_key] = bucket
        pinned = env.get("CLAUDE_CONFIG_DIR")
        if isinstance(pinned, str) and pinned.strip():
            table.pinned[os.path.realpath(os.path.expanduser(pinned.strip()))] = bucket
    return table


def bucket_for_model(model: Optional[str], table: Dict[str, Bucket],
                     config_dir: Optional[str] = None) -> Bucket:
    """config_dir คือ instance ที่ log นี้มาจาก — ใช้เป็นทางสุดท้ายเมื่อโปรไฟล์ผูก dir ไว้"""
    if not isinstance(model, str) or not model.strip():
        return UNKNOWN
    key = model.strip().lower()
    if key in table:
        return table[key]
    norm = _normalized(key)
    same = {bucket for configured, bucket in table.items() if _normalized(configured) == norm}
    if len(same) == 1:
        return next(iter(same))
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
    pinned = getattr(table, "pinned", None)
    if pinned and config_dir:
        owner = pinned.get(os.path.realpath(config_dir))
        if owner is not None:
            return owner
    return UNKNOWN
