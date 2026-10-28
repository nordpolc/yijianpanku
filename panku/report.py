# -*- coding: utf-8 -*-
"""生成排查用工作簿：原始数据 / 清洗后 / ROW_DATA / 清洗规则说明 / 合并明细。"""

import os

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .config import load_config
from .fileutil import save_wb

THIN = Side(style="thin", color="FFBFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", fgColor="FFDCE6F1")
WARN_FILL = PatternFill("solid", fgColor="FFFFF2CC")
SKIP_FILL = PatternFill("solid", fgColor="FFE2EFDA")


def _write(ws, headers, rows, widths=None):
    ws.append(headers)
    for r in rows:
        ws.append(r)
    n = len(headers)
    for c in range(1, n + 1):
        cell = ws.cell(1, c)
        cell.font = Font(name="宋体", size=10, bold=True)
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    # 正文样式只构造一次，逐格共用同一个 StyleArray（openpyxl 写属性时才复制）
    if ws.max_row >= 2:
        proto = ws.cell(2, 1)
        proto.font = Font(name="宋体", size=10)
        proto.border = BORDER
        body = proto._style
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=n):
            for cell in row:
                cell._style = body
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, 14)
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(n), ws.max_row)


def build_detail(out_path, table, all_rows, merged, rowdata, groups, stats,
                 warehouse, stocktake_date, log=print, progress=None):
    """生成排查工作簿。"""
    cfg = load_config()
    names = cfg["sheet_names"]
    headers = [h if h is not None else "" for h in table.headers]
    batch_i = table.cols.get("batch")

    wb = openpyxl.Workbook()
    ws_raw = wb.active
    ws_raw.title = names["raw"]
    ws_clean = wb.create_sheet(names["clean"])
    ws_row = wb.create_sheet(names["rowdata"])
    ws_doc = wb.create_sheet(names["doc"])
    ws_mg = wb.create_sheet(names["merge"])

    # 原始数据 / 清洗后
    if progress:
        progress(93, "写原始数据")
    _write(ws_raw, headers, [r for _, r in all_rows] + [r for _, r in table.footer])
    if progress:
        progress(95, "写清洗后")
    _write(ws_clean, headers, [r["row"] for r in merged] + [r for _, r in table.footer])
    if progress:
        progress(97, "写 ROW_DATA")

    # ROW_DATA
    rd_headers = (["原行号"] + headers +
                  ["清洗后批次号", "清洗后形态", "原始判定", "清洗动作", "备注", "清洗后行号"])
    pos = {rec["src"]: i + table.header_row + 1 for i, rec in enumerate(merged)}
    deleted = {}
    for g in groups:
        for extra in g["rows"][1:]:
            deleted[extra["src"]] = pos.get(g["kept"]["src"])
    rd_rows = []
    for rd in rowdata:
        loc = pos.get(rd["src"])
        where = loc if loc else ("已合并至第%d行" % deleted[rd["src"]] if rd["src"] in deleted else "")
        rd_rows.append([rd["src"]] + list(rd["row"]) +
                       [rd["res"]["value"], rd["res"]["form"], rd["res"]["rule"],
                        rd["res"]["action"], rd["res"]["note"], where])
    _write(ws_row, rd_headers, rd_rows)
    # 高亮：异常黄、器械类绿
    for i, rd in enumerate(rd_rows, start=2):
        if rd[len(headers) + 2] == "异常":
            for c in range(1, len(rd_headers) + 1):
                ws_row.cell(i, c).fill = WARN_FILL
        elif rd[len(headers) + 3] == "跳过":
            for c in range(1, len(rd_headers) + 1):
                ws_row.cell(i, c).fill = SKIP_FILL

    # 合并明细
    mg_headers = ["合并键", "行数", "合并前明细", "保留行"]
    mg_rows = []
    for g in groups:
        detail = "；".join("第%d行 %s" % (r["src"], _qty(r["row"], table)) for r in g["rows"])
        mg_rows.append([" | ".join(str(x) for x in g["key"]), len(g["rows"]), detail,
                        "第%d行" % g["kept"]["src"]])
    _write(ws_mg, mg_headers, mg_rows, {"合并键": 60, "合并前明细": 70})

    # 规则说明
    _doc(ws_doc, cfg, table, len(all_rows), len(merged), len(rowdata), stats,
         len(groups), warehouse, stocktake_date)

    if progress:
        progress(98, "保存排查表")
    saved = save_wb(wb, out_path, log)
    log("清洗排查表：%s" % os.path.basename(saved))
    return saved


def _qty(row, table):
    parts = []
    for k, label in (("qty_avail", "可用"), ("qty_stock", "库存")):
        i = table.cols.get(k)
        if i:
            parts.append("%s=%s" % (label, row[i - 1]))
    return "，".join(parts)


def _doc(ws, cfg, table, n_in, n_out, n_clean, stats, n_groups, warehouse, date):
    L = []
    L.append(["批次号清洗规则说明（工具自动生成）"])
    L.append([])
    L.append(["数据来源", os.path.basename(table.path)])
    L.append(["读取工作表", table.sheet])
    L.append(["清洗对象", "「%s」列" % table.headers[table.cols["batch"] - 1]])
    L.append(["判定依据", "「%s」列是否以 xx.xxx.xx.20 开头" % table.headers[table.cols["code"] - 1]])
    L.append(["仓库/寄售库", warehouse])
    L.append(["盘点日期", str(date)])
    L.append(["数据行数", "原始 %d 行；清洗并合并后 %d 行" % (n_in, n_out)])
    L.append(["需清洗行数", n_clean])
    L.append(["合并组数", n_groups])
    L.append([])
    L.append(["一、目标形态（清洗后只允许这三种）"])
    L.append(["形态1", "纯数字"])
    L.append(["形态2", "纯数字 + 一位英文字母"])
    L.append(["形态3", "空值，或反斜杠 \\"])
    L.append([])
    L.append(["二、四条规则"])
    L.append(["规则1", "批次号为纯数字 → 合格，保留"])
    L.append(["规则2", "批次号为纯数字+一位字母，且长编码不为 xx.xxx.xx.20 开头 → 合格，保留"])
    L.append(["规则3", "批次号为空或为 \\ → 合格；全角/半角斜杠统一归一为 \\"])
    L.append(["规则4", "批次号开头有字母，且长编码为 xx.xxx.xx.20 开头 → 删除开头的字母"])
    L.append(["说明", "规则4 原文「纯数字且开头和结尾都有字母」自相矛盾，按业务口径执行为「删除开头字母」"])
    L.append(["说明", "长编码 .20 的物料，其批次只保留纯数字：开头字母、结尾字母都去掉（规则2 明文排除 .20）"])
    L.append([])
    L.append(["三、清洗步骤（四种情况以外）"])
    L.append(["步骤1", "空值 / ／ / / / ＼ → \\"])
    L.append(["步骤2", "删除开头的全部英文字母"])
    L.append(["步骤3", "删除开头的非字母数字符号"])
    L.append(["步骤4", "在第一个非字母数字字符处截断，其后内容视为备注丢弃"])
    L.append(["步骤5", "主体拆解 ^(\\d+)([A-Za-z]*)$：纯数字→形态1；数字+1位字母→非.20 保留、.20 去字母；数字+多位字母→去字母取数字"])
    L.append(["步骤6", "字母夹在数字中间（如 SW19L006）→ 保留原值，标待人工确认"])
    L.append(["步骤7", "器械类物料（编码前缀 %s）按器械管理，不参与清洗" %
              "、".join(cfg.get("skip_clean_prefixes") or [])])
    L.append([])
    L.append(["四、合并规则"])
    L.append(["合并键", "、".join(cfg["merge_keys"])])
    L.append(["合并方式", "合并键全部相等的行合成一行；可用数量、库存数量求和"])
    L.append(["不合并情形", "同批次但生产日期/到期日期不同，或物料编码不同 —— 保留多行，需 ERP 拆批次"])
    L.append([])
    L.append(["五、本次判定分布"])
    for k in ("规则1", "规则2", "规则3", "规则4", "条件外", "跳过"):
        if k in stats["rule"]:
            L.append([k, stats["rule"][k]])
    L.append([])
    L.append(["清洗动作分布"])
    for k, v in sorted(stats["action"].items(), key=lambda kv: -kv[1]):
        L.append([k, v])
    L.append([])
    L.append(["六、工作表说明"])
    L.append(["原始数据", "清洗前原表，逐格未改动"])
    L.append(["清洗后", "清洗并合并后的结果"])
    L.append(["ROW_DATA", "需要清洗的原始行，附清洗结果、动作、备注、新行号"])
    L.append(["合并明细", "同键重复合并的逐组明细"])
    for row in L:
        ws.append(row)
    ws["A1"].font = Font(name="黑体", size=12, bold=True)
    ws.column_dimensions["A"].width = 100
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1)
        if isinstance(a.value, str) and a.value[:2] in ("一、", "二、", "三、", "四、", "五、", "六、"):
            a.font = Font(name="黑体", size=11, bold=True)
