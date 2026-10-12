"""อ่านโครงสร้างของ ccs ตามที่ ccs เองใช้ — ที่อยู่ไดเรกทอรี บัญชี และโปรไฟล์ api

ccs หาไดเรกทอรีของมันตามลำดับ ``CCS_DIR`` > ``CCS_HOME``/.ccs > ``~/.ccs``
(dist/utils/config-manager.js ``_resolveCcsDir``) และเก็บรายชื่อบัญชี/โปรไฟล์ไว้ใน
``config.yaml`` — โปรไฟล์ชี้ไฟล์ settings ที่อยู่ที่ไหนก็ได้ ไม่จำเป็นต้องเป็น
``<ccs>/<ชื่อ>.settings.json`` · อ่านไม่ได้ก็คืนค่าว่าง ผู้เรียกยัง glob แบบเดิมต่อได้

parser ตรงนี้อ่านแค่ ``accounts:`` กับ ``profiles:`` ระดับบนสุด ไม่พึ่ง PyYAML
เพราะ interpreter ที่แอปหาเจอไม่รับประกันว่ามีแพ็กเกจนี้
"""

import os
from typing import Dict, List, Optional


def ccs_dir(env: Optional[Dict[str, str]] = None) -> str:
    env = os.environ if env is None else env
    if env.get("CCS_DIR"):
        return os.path.abspath(os.path.expanduser(env["CCS_DIR"]))
    if env.get("CCS_HOME"):
        return os.path.join(os.path.abspath(os.path.expanduser(env["CCS_HOME"])), ".ccs")
    return os.path.join(os.path.expanduser("~"), ".ccs")


def _scalar(raw: str) -> str:
    value = raw.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def _blocks(text: str, wanted: tuple) -> Dict[str, Dict[str, Dict[str, str]]]:
    """{top: {child: {field: value}}} ของ mapping สองชั้นใต้คีย์ระดับบนสุดที่ต้องการ"""
    out: Dict[str, Dict[str, Dict[str, str]]] = {}
    top = child = None
    child_indent = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            key = stripped.split(":", 1)[0].strip()
            top = key if key in wanted and stripped.endswith(":") else None
            child = child_indent = None
            if top:
                out.setdefault(top, {})
            continue
        if top is None or ":" not in stripped or stripped.startswith("- "):
            continue
        key, _, rest = stripped.partition(":")
        key = _scalar(key)
        if child_indent is None or indent <= child_indent:
            child_indent = indent
            child = key
            out[top].setdefault(child, {})
        elif child is not None:
            out[top][child][key] = _scalar(rest)
    return out


def read_config(directory: Optional[str] = None) -> Dict[str, object]:
    """{"accounts": [ชื่อ], "profiles": {ชื่อ: path ของ settings}}"""
    directory = directory or ccs_dir()
    result: Dict[str, object] = {"accounts": [], "profiles": {}}
    try:
        with open(os.path.join(directory, "config.yaml"), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return result
    blocks = _blocks(text, ("accounts", "profiles"))
    accounts: List[str] = [name for name in blocks.get("accounts", {}) if name]
    profiles: Dict[str, str] = {}
    for name, fields in blocks.get("profiles", {}).items():
        path = fields.get("settings")
        if not name or not path:
            continue
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(directory, path)
        profiles[name] = path
    result["accounts"] = accounts
    result["profiles"] = profiles
    return result
