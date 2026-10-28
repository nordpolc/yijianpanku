# -*- coding: utf-8 -*-
"""读表、清洗、合并、生成两份输出。"""

import datetime as _dt
import os
import re

import openpyxl

from . import batchrules as R
from .config import load_config
from .detect import ROLE_CLEANED, detect_workbook
from .fileutil import dir_writable, pick_out_dir


class Cancelled(Exception):
    """用户点了取消。"""


# ------------------------------------------------------------------ 读表

class StockTable(object):
    def __init__(self, path, sheet, header_row, headers, cols):
        self.path = path
        self.sheet = sheet
        self.header_row = header_row
        self.headers = headers
        self.cols = cols
        self.rows = []      # [(源行号, [值...])]
        self.footer = []    # 合计行等非数据行

    def get(self, row, key):
        i = self.cols.get(key)
        return None if not i else row[i - 1]

    def put(self, row, key, value):
        i = self.cols.get(key)
        if i:
            row[i - 1] = value


def read_table(det):
    """按识别结果流式读出整张表（只读模式，快）。"""
    wb = openpyxl.load_workbook(det["path"], data_only=True, read_only=True)
    ws = wb[det["sheet"]]
    all_rows = []
    try:
        if hasattr(ws, "reset_dimensions"):
            ws.reset_dimensions()   # 无 dimension 记录的文件需要重置，否则只读 1 列
        for row in ws.iter_rows(values_only=True):
            all_rows.append(list(row))
    finally:
        wb.close()

    hr = det["header_row"]
    headers = all_rows[hr - 1] if len(all_rows) >= hr else []
    width = max(len(r) for r in all_rows) if all_rows else len(headers)
    headers = list(headers) + [None] * (width - len(headers))
    t = StockTable(det["path"], det["sheet"], hr, headers, det["columns"])

    code_i, batch_i = t.cols.get("code"), t.cols.get("batch")
    for idx in range(hr, len(all_rows)):
        vals = all_rows[idx] + [None] * (width - len(all_rows[idx]))
        if not any(v is not None and str(v).strip() != "" for v in vals):
            continue
        code = vals[code_i - 1] if code_i else None
        batch = vals[batch_i - 1] if batch_i else None
        blank_code = code is None or str(code).strip() == ""
        blank_batch = batch is None or str(batch).strip() == ""
        if blank_code and blank_batch:
            t.footer.append((idx + 1, vals))
        else:
            t.rows.append((idx + 1, vals))
    return t


# ------------------------------------------------------------------ 清洗

def clean_table(t, log=None):
    """逐行清洗，返回 (清洗后行, ROW_DATA 行, 统计)。"""
    batch_i, code_i = t.cols.get("batch"), t.cols.get("code")
    cleaned, rowdata = [], []
    rule_stats, action_stats = {}, {}
    for src, row in t.rows:
        raw = row[batch_i - 1]
        code = row[code_i - 1] if code_i else None
        res = R.classify(raw, code)
        new = list(row)
        new[batch_i - 1] = res["value"]
        cleaned.append({"src": src, "row": new, "res": res})
        rule_stats[res["rule"]] = rule_stats.get(res["rule"], 0) + 1
        if res["changed"] or res["form"] == R.FORM_BAD:
            rowdata.append({"src": src, "row": row, "res": res})
            action_stats[res["action"]] = action_stats.get(res["action"], 0) + 1
    if log:
        log("清洗：需处理 %d 行 / 共 %d 行" % (len(rowdata), len(t.rows)))
    return cleaned, rowdata, {"rule": rule_stats, "action": action_stats}


# ------------------------------------------------------------------ 合并

def _key(v):
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()[:10]
    if v is None:
        return ""
    return str(v).strip()


def merge_table(cleaned, cols, merge_keys=None, sum_cols=None):
    """同键合并，返回 (合并后行, 合并组)。"""
    cfg = load_config()
    keys = merge_keys if merge_keys is not None else cfg["merge_keys"]
    sums = sum_cols if sum_cols is not None else cfg["sum_columns"]
    key_idx = [(k, cols[k] - 1) for k in keys if k in cols]

    buckets, order = {}, []
    for rec in cleaned:
        k = tuple(_key(rec["row"][i]) for _, i in key_idx)
        if k not in buckets:
            buckets[k] = []
            order.append(k)
        buckets[k].append(rec)

    merged, groups = [], []
    for k in order:
        grp = buckets[k]
        if len(grp) == 1:
            merged.append(grp[0])
            continue
        base = list(grp[0]["row"])
        for name in sums:
            i = cols.get(name)
            if i is None:
                continue
            vals = [g["row"][i - 1] for g in grp]
            if all(isinstance(v, (int, float)) for v in vals):
                base[i - 1] = sum(vals)
        rec = {"src": grp[0]["src"], "row": base, "res": grp[0]["res"], "group": grp}
        merged.append(rec)
        groups.append({"key": k, "rows": grp, "kept": rec})
    return merged, groups


# ------------------------------------------------------------------ 主流程

def process(paths, out_dir=None, warehouse=None, stocktake_date=None,
            template_path=None, log=print, progress=None, cancel=None):
    """完整流程：识别 -> 读表 -> 清洗 -> 合并 -> 出两份文件。

    progress(pct, text)：真实百分比回调；cancel：threading.Event，置位即中止。
    返回 dict，含 formal / detail 两个输出路径与统计。
    """
    from .template import build_formal
    from .report import build_detail

    def step(pct, text=""):
        if progress:
            progress(int(pct), text)

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    check()
    step(2, "识别文件")
    cfg = load_config()
    dets = [detect_workbook(p) for p in paths]
    stocks = [d for d in dets if d["role"] in (ROLE_CLEANED, "stock", "ledger")]
    if not stocks:
        raise RuntimeError("没有找到库存数据表：需要包含「物料编码 + 批次 + 数量」列")

    step(6, "准备输出目录")
    try:
        from .branding import app_dir
        _app_dir = app_dir()
    except Exception:
        _app_dir = None
    out_dir = pick_out_dir(out_dir or os.path.dirname(os.path.abspath(stocks[0]["path"])),
                           log=log, app_dir=_app_dir)
    os.makedirs(out_dir, exist_ok=True)

    # 多个库存表时按顺序拼接
    all_cleaned, all_rowdata, all_rows = [], [], []
    stats = {"rule": {}, "action": {}}
    base_table = None
    for d in stocks:
        check()
        step(10, "读取 %s" % d["file"])
        log("读取 %s [%s]" % (d["file"], d["sheet"]))
        t = read_table(d)
        if base_table is None:
            base_table = t
        cleaned, rowdata, st = clean_table(t, log)
        all_cleaned.extend(cleaned)
        all_rowdata.extend(rowdata)
        all_rows.extend(t.rows)
        for k, v in st["rule"].items():
            stats["rule"][k] = stats["rule"].get(k, 0) + v
        for k, v in st["action"].items():
            stats["action"][k] = stats["action"].get(k, 0) + v

    check()
    step(38, "清洗完成")
    merged, groups = merge_table(all_cleaned, base_table.cols)
    log("合并：%d 组，减少 %d 行" % (len(groups), sum(len(g["rows"]) - 1 for g in groups)))

    wh = warehouse or _guess_warehouse(merged, base_table) or cfg.get("warehouse_default", "")
    d = _parse_date(stocktake_date)
    stamp = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
    safe_wh = (wh or "库存").replace("/", "_").replace("\\", "_")

    formal_path = os.path.join(out_dir, "%s_盘点表_%s.xlsx" % (safe_wh, stamp))
    detail_path = os.path.join(out_dir, "%s_清洗排查_%s.xlsx" % (safe_wh, stamp))

    if not dir_writable(out_dir):
        raise RuntimeError("输出目录不可写：%s\n请换一个输出目录（例如桌面）后重试。" % out_dir)

    check()
    step(45, "生成盘点表")
    formal_path = build_formal(formal_path, merged, base_table, wh, d, template_path, log,
                               progress=step)
    check()
    step(93, "生成排查表")
    detail_path = build_detail(detail_path, base_table, all_rows, merged, all_rowdata, groups,
                               stats, wh, d, log, progress=step)
    check()
    step(99, "完成")

    return {"formal": formal_path, "detail": detail_path,
            "rows_in": len(all_rows), "rows_out": len(merged),
            "cleaned": len(all_rowdata), "merged_groups": len(groups),
            "merged_removed": sum(len(g["rows"]) - 1 for g in groups),
            "warehouse": wh, "date": stamp, "stats": stats}


def _parse_date(v):
    """把 2026-10-27 / 20261027 / 2026/10/27 / date 统一成 date；解析不了就原样返回。"""
    if v is None or (isinstance(v, str) and not v.strip()):
        return _dt.date.today()
    if hasattr(v, "strftime"):
        return v
    s = str(v).strip().replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
    if re.match(r"^\d{8}$", s):
        try:
            return _dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
        except ValueError:
            return str(v).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return str(v).strip()
    return str(v).strip()


def _guess_warehouse(merged, table):
    from collections import Counter
    c = Counter()
    for rec in merged:
        v = rec["row"][table.cols["warehouse"] - 1] if "warehouse" in table.cols else None
        if v:
            c[str(v).strip()] += 1
    return c.most_common(1)[0][0] if c else ""


def peek_warehouse(path):
    """快速猜出仓库名，用于界面预填。"""
    from collections import Counter
    d = detect_workbook(path)
    if d["role"] not in ("stock", "cleaned", "ledger"):
        return ""
    t = read_table(d)
    i = t.cols.get("warehouse")
    if not i:
        return ""
    c = Counter()
    for _, row in t.rows[:5000]:
        v = row[i - 1]
        if v:
            c[str(v).strip()] += 1
    return c.most_common(1)[0][0] if c else ""
