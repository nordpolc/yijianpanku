# -*- coding: utf-8 -*-
"""按表头指纹识别文件角色，不看文件名。

角色：
    cleaned   已清洗结果工作簿（含「清洗后」表）
    template  盘点模板（含 账面数量 + 盘点数量 列）
    stock     库存导出表（含 物料编码 + 批次 + 数量 列）
    ledger    盘点台账（含 批次 + 数量，无账面列）
    unknown   认不出
"""

import os
import unicodedata

import openpyxl

from .config import load_config

ROLE_CLEANED = "cleaned"
ROLE_TEMPLATE = "template"
ROLE_STOCK = "stock"
ROLE_LEDGER = "ledger"
ROLE_UNKNOWN = "unknown"

ROLE_LABEL = {
    ROLE_CLEANED: "已清洗结果",
    ROLE_TEMPLATE: "盘点模板",
    ROLE_STOCK: "库存导出表",
    ROLE_LEDGER: "盘点台账",
    ROLE_UNKNOWN: "无法识别",
}

#: 匹配优先级：先精确、后包含，同一次扫描按此顺序认领列
PRIORITY = ["code", "batch", "name", "spec", "unit", "book_qty", "count_qty",
            "diff_qty", "qty_stock", "qty_avail", "prod_date", "exp_date",
            "warehouse", "inv_type", "inv_status", "serial", "seq", "remark"]

MAX_SCAN_ROWS = 25


def norm(v):
    """表头归一化：全角转半角、去空白、去冒号、小写。"""
    if v is None:
        return ""
    s = unicodedata.normalize("NFKC", str(v))
    s = "".join(s.split())
    return s.strip(":：*").lower()


def match_columns(header_values):
    """把一行表头映射到逻辑列名，返回 {logical: 1-based col}。"""
    syn = load_config()["columns"]
    normed = [norm(v) for v in header_values]
    found, used = {}, set()

    # 第一轮：精确匹配（表头就是同义词之一）
    for key in PRIORITY:
        cands = {norm(x) for x in syn.get(key, []) if x}
        for i, h in enumerate(normed):
            if h and i not in used and h in cands:
                found[key] = i + 1
                used.add(i)
                break

    # 第二轮：包含匹配，给「可用数量/库存数量」这类带修饰的表头兜底
    for key in PRIORITY:
        if key in found:
            continue
        cands = [norm(x) for x in syn.get(key, []) if x]
        for i, h in enumerate(normed):
            if not h or i in used:
                continue
            if any(c and (c in h or h in c) for c in cands):
                found[key] = i + 1
                used.add(i)
                break
    return found


def find_header(ws, max_scan=MAX_SCAN_ROWS):
    """向下扫描找表头行，返回 (header_row, columns, header_values)。"""
    best = (0, {}, [])
    best_score = 0
    limit = min(ws.max_row or 1, max_scan)
    width = min(ws.max_column or 1, 60)
    for r in range(1, limit + 1):
        vals = [ws.cell(r, c).value for c in range(1, width + 1)]
        cols = match_columns(vals)
        score = len(cols)
        if "code" in cols and "batch" in cols:
            score += 3
        if score > best_score:
            best_score, best = score, (r, cols, vals)
    return best


def find_header_in_rows(rows):
    """在已经读出的前若干行里找表头，返回 (header_row, columns, values)。"""
    best = (0, {}, [])
    best_score = 0
    for idx, vals in enumerate(rows, start=1):
        cols = match_columns(list(vals))
        score = len(cols)
        if "code" in cols and "batch" in cols:
            score += 3
        if score > best_score:
            best_score, best = score, (idx, cols, list(vals))
    return best


def score_sheet(cols, sheet_name):
    """按命中的逻辑列给角色打分。"""
    s = {ROLE_STOCK: 0, ROLE_TEMPLATE: 0, ROLE_LEDGER: 0}
    has = set(cols)
    if {"book_qty", "count_qty"} <= has:
        s[ROLE_TEMPLATE] += 10
    if "diff_qty" in has:
        s[ROLE_TEMPLATE] += 2
    if "盘点" in (sheet_name or ""):
        s[ROLE_TEMPLATE] += 2
    if {"code", "batch"} <= has:
        s[ROLE_STOCK] += 5
        s[ROLE_LEDGER] += 2
    if has & {"qty_stock", "qty_avail"}:
        s[ROLE_STOCK] += 4
        s[ROLE_LEDGER] += 3
    if "book_qty" in has:
        s[ROLE_LEDGER] -= 3
    if {"name", "spec", "unit"} & has:
        s[ROLE_STOCK] += 1
    return s


def peek_workbook(path, max_rows=MAX_SCAN_ROWS):
    """只读前若干行，返回 {sheet_name: [row tuple, ...]}（流式，很快）。"""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = {}
    try:
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                continue
            rows = []
            try:
                # 有的导出文件没有 dimension 记录，read_only 会误判为 1 列
                if hasattr(ws, "reset_dimensions"):
                    ws.reset_dimensions()
                for row in ws.iter_rows(min_row=1, max_row=max_rows, values_only=True):
                    rows.append(row)
            except Exception:
                pass
            out[ws.title] = rows
    finally:
        wb.close()
    return out


def detect_workbook(path):
    """识别一个 xlsx 的角色，返回 dict（role / sheet / header_row / columns / notes）。"""
    cfg = load_config()
    names = cfg["sheet_names"]
    res = {"path": path, "file": os.path.basename(path), "role": ROLE_UNKNOWN,
           "sheet": None, "header_row": 0, "columns": {}, "sheets": [], "notes": []}

    sheets = peek_workbook(path)
    res["sheets"] = list(sheets.keys())

    # 已清洗结果：直接取「清洗后」表
    for nm in (names.get("clean"), "清洗后", "cleaned"):
        if nm and nm in sheets:
            hr, cols, _ = find_header_in_rows(sheets[nm])
            res.update(role=ROLE_CLEANED, sheet=nm, header_row=hr, columns=cols)
            res["notes"].append("含工作表「%s」，按已清洗数据读取" % nm)
            return res

    best = (0, ROLE_UNKNOWN, None, 0, {})
    for nm, rows in sheets.items():
        hr, cols, _ = find_header_in_rows(rows)
        if not cols:
            continue
        for role, v in score_sheet(cols, nm).items():
            if v > best[0]:
                best = (v, role, nm, hr, cols)
    if best[0] >= 5:
        res.update(role=best[1], sheet=best[2], header_row=best[3], columns=best[4])
    return res


def detect_many(paths):
    """批量识别，返回 (数据表列表, 模板, 其它)。"""
    stocks, templates, others = [], None, []
    for p in paths:
        try:
            d = detect_workbook(p)
        except Exception as e:
            others.append({"path": p, "file": os.path.basename(p), "role": ROLE_UNKNOWN,
                           "error": str(e)})
            continue
        if d["role"] == ROLE_TEMPLATE and templates is None:
            templates = d
        elif d["role"] in (ROLE_STOCK, ROLE_CLEANED, ROLE_LEDGER):
            stocks.append(d)
        else:
            others.append(d)
    return stocks, templates, others
