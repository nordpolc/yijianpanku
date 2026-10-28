# -*- coding: utf-8 -*-
"""批次号四条规则判定与清洗。

目标形态只有三种：
    形态1  纯数字
    形态2  纯数字 + 一位英文字母
    形态3  空值，或反斜杠 \\
"""

import re

from .config import load_config

FORM_DIGITS = "纯数字"
FORM_DIGIT_LETTER = "纯数字+一位字母"
FORM_EMPTY = "空或\\"
FORM_BAD = "异常"

#: 空值占位符：反斜杠与各种斜杠写法统一归一为 \
SLASH_CHARS = {"\\", "／", "/", "＼"}

RE_DIGITS = re.compile(r"^\d+$")
RE_DIGIT_LETTER = re.compile(r"^\d+[A-Za-z]$")
RE_LEAD_LETTERS = re.compile(r"^[A-Za-z]+")
RE_LEAD_SYMBOL = re.compile(r"^[^0-9A-Za-z]+")
RE_HEAD = re.compile(r"^[0-9A-Za-z]*")
RE_SPLIT = re.compile(r"^(\d+)([A-Za-z]*)$")

_RE_CODE20 = None


def _code20_re():
    global _RE_CODE20
    if _RE_CODE20 is None:
        _RE_CODE20 = re.compile(load_config().get("code20_regex", r"^\d{2}\.\d{3}\.\d{2}\.20"))
    return _RE_CODE20


def is_code20(material_code):
    """长编码是否以 xx.xxx.xx.20 开头。"""
    s = "" if material_code is None else str(material_code).strip()
    return bool(_code20_re().match(s))


def is_skipped(material_code):
    """器械类等不参与批次清洗的物料（按编码前缀）。"""
    s = "" if material_code is None else str(material_code).strip()
    for pre in load_config().get("skip_clean_prefixes") or []:
        if s.startswith(pre):
            return True
    return False


def form_of(value):
    """按值反推形态。"""
    s = "" if value is None else str(value).strip()
    if s == "" or s in SLASH_CHARS:
        return FORM_EMPTY
    if RE_DIGITS.match(s):
        return FORM_DIGITS
    if RE_DIGIT_LETTER.match(s):
        return FORM_DIGIT_LETTER
    return FORM_BAD


def _raw_text(raw):
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def classify(raw, material_code):
    """判定并清洗一个批次号。

    返回 dict：
        rule    原始判定：规则1 / 规则2 / 规则3 / 规则4 / 条件外
        value   清洗后的批次号
        action  清洗动作（无需清洗时为「无需清洗」）
        form    清洗后形态
        note    备注
        changed 值是否发生变化
    """
    s = _raw_text(raw)
    is20 = is_code20(material_code)

    # 器械类：不参与批次清洗
    if is_skipped(material_code):
        form = form_of(s)
        return {"rule": "跳过", "value": s, "action": "器械类，不清洗",
                "form": form, "note": "器械类物料，按器械管理，批次不适用清洗规则",
                "changed": False}

    # 规则3：空值 / 斜杠占位
    if s == "":
        return {"rule": "规则3", "value": "", "action": "空值", "form": FORM_EMPTY,
                "note": "", "changed": False}
    if s in SLASH_CHARS:
        return {"rule": "规则3", "value": "\\", "action": "斜杠占位归一为 \\",
                "form": FORM_EMPTY, "note": "", "changed": s != "\\"}

    # 原始判定（按清洗前的样子归类）
    if RE_DIGITS.match(s):
        rule = "规则1"
    elif RE_DIGIT_LETTER.match(s):
        rule = "条件外" if is20 else "规则2"   # .20 物料不适用规则2
    elif RE_LEAD_LETTERS.match(s) and is20:
        rule = "规则4"
    else:
        rule = "条件外"

    # 步骤2：删除开头字母；步骤3：删除开头符号；步骤4：首个非字母数字处截断
    acts, t = [], s
    t2 = RE_LEAD_LETTERS.sub("", t)
    if t2 != t:
        acts.append("去除开头字母")
        t = t2
    t2 = RE_LEAD_SYMBOL.sub("", t)
    if t2 != t:
        acts.append("去除开头符号")
        t = t2
    head = RE_HEAD.match(t).group(0)
    if head != t:
        acts.append("去除备注说明")
    if head == "":
        return {"rule": rule, "value": s, "action": "无法归一，保留原值", "form": FORM_BAD,
                "note": "整段非字母数字，待人工确认", "changed": False}

    # 步骤5：拆主体
    mm = RE_SPLIT.match(head)
    if not mm:
        return {"rule": rule, "value": s, "action": "字母夹在数字中间，保留原值",
                "form": FORM_BAD, "note": "字母在数字中间，无法归入三种形态，待人工确认",
                "changed": False}
    digs, tail = mm.groups()
    if tail == "":
        val = digs
    elif len(tail) == 1:
        if is20:
            val = digs
            acts.append("去除结尾字母（.20 物料仅保留纯数字）")
        else:
            val = digs + tail
    else:
        val = digs
        acts.append("去除结尾多余字母")

    return {"rule": rule, "value": val,
            "action": "、".join(acts) if acts else "无需清洗",
            "form": form_of(val), "note": "", "changed": val != s}


def needs_clean(raw, material_code):
    """该行是否需要出现在 ROW_DATA 里。"""
    r = classify(raw, material_code)
    return r["changed"] or r["form"] == FORM_BAD
