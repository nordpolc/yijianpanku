# -*- coding: utf-8 -*-
"""把清洗后的数据填进盘点模板，生成正式盘点表。"""

import datetime as _dt
import os
from copy import copy

import openpyxl
from openpyxl.utils import get_column_letter

from .config import load_config
from .detect import find_header, norm
from .fileutil import save_wb

DEFAULT_TEMPLATE_NAME = "盘点模板.xlsx"

# 模板列名 -> 源表列名的兜底映射（模板叫「账面数量」，源表叫「库存数量/可用数量」）
SRC_ALIAS = {"book_qty": ("qty_stock", "qty_avail")}
TEXT_KEYS = ("code", "batch")


def template_path(user_template=None):
    """模板位置：优先用户自定义，其次内置。"""
    if user_template and os.path.exists(user_template):
        return user_template
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(os.path.dirname(here), "模板", DEFAULT_TEMPLATE_NAME),
              os.path.join(here, "模板", DEFAULT_TEMPLATE_NAME)):
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到内置盘点模板：%s" % DEFAULT_TEMPLATE_NAME)


def _find_row(ws, text, col=None, max_row=None):
    text = norm(text)
    for r in range(1, (max_row or ws.max_row or 1) + 1):
        cells = [ws.cell(r, col)] if col else ws[r]
        for c in cells:
            if norm(c.value) == text:
                return r
    return 0


def _apply(dst, src):
    """整块复制样式（字体/边框/填充/对齐/数字格式）。"""
    if src is not None and src.has_style:
        dst._style = copy(src._style)


def build_formal(out_path, merged, table, warehouse, stocktake_date,
                 tpl=None, log=print, progress=None):
    """生成正式盘点表。"""
    cfg = load_config()
    tpl = template_path(tpl or cfg.get("user_template"))
    wb = openpyxl.load_workbook(tpl)
    keep = cfg.get("formal_sheet_keep") or []

    # 选目标表：优先「账面数量」，否则按列指纹
    ws = None
    for nm in keep:
        if nm in wb.sheetnames:
            ws = wb[nm]
            break
    if ws is None:
        for w in wb.worksheets:
            hr, cols, _ = find_header(w)
            if "book_qty" in cols and "count_qty" in cols:
                ws = w
                break
    if ws is None:
        raise RuntimeError("模板里找不到账面数量/盘点数量表")
    wb.active = wb.sheetnames.index(ws.title)

    hr, cols, _ = find_header(ws)
    if not cols:
        raise RuntimeError("模板「%s」表头识别失败" % ws.title)
    data_row = hr + 1
    total_row = _find_row(ws, "总计")
    sign_row = _find_row(ws, "盘点人员")
    last_row = ws.max_row

    # 备份样式与签名行文字
    blueprint = [copy(ws.cell(data_row, c)._style) if ws.cell(data_row, c).has_style else None
                 for c in range(1, ws.max_column + 1)]
    total_vals = {}
    if total_row:
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(total_row, c)
            total_vals[c] = (cell.value, copy(cell._style) if cell.has_style else None)
    sign_vals = {}
    if sign_row:
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(sign_row, c)
            if cell.value not in (None, ""):
                sign_vals[c] = (cell.value, copy(cell._style) if cell.has_style else None)

    # 清空数据区至表尾
    if last_row >= data_row:
        ws.delete_rows(data_row, last_row - data_row + 1)

    # 逐行写入
    n = len(merged)
    max_col = ws.max_column  # 只取一次：openpyxl 每次读取都要遍历全部单元格
    # 物料编码/批次列要按文本存，样式改成文本后再赋，否则会被模板样式覆盖回常规
    text_style = {}
    for key in TEXT_KEYS:
        ci = cols.get(key)
        if ci and ci <= len(blueprint) and blueprint[ci - 1] is not None:
            st = copy(blueprint[ci - 1])
            st.numFmtId = 49  # 内置格式 49 = 文本(@)
            text_style[ci] = st
    seq_c, wh_c = cols.get("seq"), cols.get("warehouse")
    for i, rec in enumerate(merged):
        if progress and n and i % 1500 == 0:
            progress(45 + int(45.0 * i / n), "写入第 %d / %d 行" % (i, n))
        r = data_row + i
        row = rec["row"]
        for key, ci in cols.items():
            if key in ("count_qty", "diff_qty", "remark", "seq"):
                continue
            cell = ws.cell(r, ci)
            if key in table.cols:
                v = row[table.cols[key] - 1]
            else:
                v = None
                for alias in SRC_ALIAS.get(key, ()):
                    if alias in table.cols:
                        v = row[table.cols[alias] - 1]
                        break
            if key in TEXT_KEYS:
                v = "" if v is None else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
            cell.value = v
        if seq_c:
            ws.cell(r, seq_c).value = i + 1
        if wh_c:
            ws.cell(r, wh_c).value = warehouse
        for c in range(1, max_col + 1):
            st = text_style.get(c) or blueprint[c - 1]
            if st is not None:
                ws.cell(r, c)._style = st

    # 差异数量公式
    kc, jc, ic = cols.get("diff_qty"), cols.get("count_qty"), cols.get("book_qty")
    if kc and jc and ic:
        L = get_column_letter
        for i in range(n):
            r = data_row + i
            ws.cell(r, kc).value = '=IF($%s%d="","",$%s%d-$%s%d)' % (
                L(jc), r, L(jc), r, L(ic), r)

    # 总计行
    tr = data_row + n
    if total_vals:
        for c, (v, st) in total_vals.items():
            cell = ws.cell(tr, c)
            if st is not None:
                cell._style = copy(st)
            if isinstance(v, str) and v.strip().lower() == "xx":
                cell.value = None
            else:
                cell.value = v
        L = get_column_letter
        for key in ("book_qty", "count_qty", "diff_qty"):
            ci = cols.get(key)
            if ci:
                ws.cell(tr, ci).value = "=SUM(%s%d:%s%d)" % (
                    L(ci), data_row, L(ci), tr - 1)

    # 签名行
    if sign_vals:
        sr = tr + 4
        for c, (v, st) in sign_vals.items():
            cell = ws.cell(sr, c)
            if st is not None:
                cell._style = copy(st)
            cell.value = v

    # 标题
    year = stocktake_date.year if hasattr(stocktake_date, "year") else _dt.date.today().year
    ph = cfg.get("template_title_placeholder")
    title_done = False
    for r in range(1, hr):
        for c in range(1, max_col + 1):
            cell = ws.cell(r, c)
            if isinstance(cell.value, str) and ph and ph in cell.value:
                cell.value = cell.value.replace(ph, warehouse)
                title_done = True
    if not title_done:
        ws.cell(1, 1).value = cfg.get("template_title", "{year}年 {warehouse}产成品盘点表").format(
            year=year, warehouse=warehouse)

    # 视图与打印
    ws.freeze_panes = "A%d" % data_row
    if n:
        ws.auto_filter.ref = "A%d:%s%d" % (hr, get_column_letter(max_col), tr - 1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "$1:$%d" % hr

    # 其他表保持原样，只清掉可能残留的样例行
    for w in wb.worksheets:
        if w is ws:
            continue
        for nm in ("无实物数量需报消耗",):
            if w.title == nm:
                w.freeze_panes = "A3"

    if progress:
        progress(92, "保存盘点表")
    saved = save_wb(wb, out_path, log)
    log("正式盘点表：%s（%d 行）" % (os.path.basename(saved), n))
    return saved
