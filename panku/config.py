# -*- coding: utf-8 -*-
"""默认配置、列名同义词库、外部 config.json 读写。

所有与具体文件无关的口径都在这里，改配置不需要改代码。
"""

import json
import os

#: 列名同义词库：逻辑列名 -> 可能的表头文字（按优先级排列，先精确后包含）
COLUMN_SYNONYMS = {
    "code": ["物料编码", "物料编号", "存货编码", "物料代码", "产品编码", "编码", "物料号", "itemcode", "item"],
    "name": ["物料", "物料名称", "品名", "产品名称", "存货名称", "名称", "itemname"],
    "spec": ["规格型号", "规格", "型号", "规格/型号", "spec"],
    "unit": ["计量单位", "单位", "主计量单位", "unit"],
    "batch": ["批次", "批次号", "批号", "批号/序列号", "批号或序列号", "生产批号", "lot", "batch", "batchno"],
    "qty_avail": ["可用数量", "可用量", "可用库存", "结存数量", "现存量", "数量"],
    "qty_stock": ["库存数量", "库存量", "库存", "结存", "数量"],
    "prod_date": ["生产日期", "生产时间", "制造日期"],
    "exp_date": ["到期日期", "有效期至", "失效日期", "到期日", "有效期"],
    "warehouse": ["仓库", "仓库名称", "库房", "存货仓库", "warehouse"],
    "inv_type": ["库存类型", "库存类别", "业务类型"],
    "inv_status": ["库存状态", "状态"],
    "serial": ["序列号", "序号号", "serial"],
    "book_qty": ["账面数量", "账面数", "账面"],
    "count_qty": ["盘点数量", "实盘数量", "实盘数", "盘点数"],
    "diff_qty": ["差异数量", "差异", "差异数"],
    "seq": ["序号", "行号", "no"],
    "remark": ["备注", "说明", "remark"],
}

#: 模板必需列（用于识别盘点模板）
TEMPLATE_REQUIRED = ["book_qty", "count_qty"]

#: 库存表必需列
STOCK_REQUIRED = ["code", "batch", "qty_stock"]

#: 合并键（逻辑列名）；全部相等才合并
DEFAULT_MERGE_KEYS = ["code", "name", "spec", "unit", "warehouse", "inv_type",
                      "inv_status", "batch", "prod_date", "exp_date"]

#: 合并时要相加的数量列
SUM_COLUMNS = ["qty_avail", "qty_stock"]

#: 器械类物料编码前缀：按器械管理，批次不做清洗
DEFAULT_SKIP_CLEAN_PREFIXES = ["09.203"]

#: 模板标题占位符（原样出现时被替换）
TEMPLATE_TITLE_PLACEHOLDER = "XX寄售库(XX)"

DEFAULT_CONFIG = {
    "columns": COLUMN_SYNONYMS,
    "merge_keys": DEFAULT_MERGE_KEYS,
    "sum_columns": SUM_COLUMNS,
    "skip_clean_prefixes": DEFAULT_SKIP_CLEAN_PREFIXES,
    "template_title": "{year}年 {warehouse}产成品盘点表",
    "template_title_placeholder": TEMPLATE_TITLE_PLACEHOLDER,
    "code20_regex": r"^\d{2}\.\d{3}\.\d{2}\.20",
    "sheet_names": {
        "raw": "原始数据",
        "clean": "清洗后",
        "rowdata": "ROW_DATA",
        "doc": "清洗规则说明",
        "merge": "合并明细",
    },
    "formal_sheet_keep": ["账面数量", "无实物数量需报消耗"],
    "warehouse_default": "运营一库",
}

_CONFIG_CACHE = None


def config_path():
    """config.json 的位置：优先程序目录，其次用户目录。"""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(os.path.dirname(here), "config.json"),
              os.path.join(here, "config.json")):
        if os.path.exists(p):
            return p
    return os.path.join(os.path.dirname(here), "config.json")


def _merge_file(cfg, p):
    """把一个配置文件合并进 cfg（columns / sheet_names 按子键合并，其余覆盖）。"""
    try:
        with open(p, "r", encoding="utf-8") as f:
            user = json.load(f)
        if not isinstance(user, dict):
            return
        for k, v in user.items():
            if k == "columns" and isinstance(v, dict):
                cfg["columns"].update(v)
            elif k == "sheet_names" and isinstance(v, dict):
                cfg["sheet_names"].update(v)
            else:
                cfg[k] = v
    except Exception as e:  # 配置写坏了不影响主流程
        print("读取配置失败（%s）：%s" % (p, e))


def load_config(path=None):
    """读取配置：默认值 <- 程序目录 config.json <- 用户目录 config.json。"""
    global _CONFIG_CACHE
    if path is None and _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝
    p = path or config_path()
    if os.path.exists(p):
        _merge_file(cfg, p)
    if path is None:
        up = user_config_path()
        if os.path.exists(up):
            _merge_file(cfg, up)
        _CONFIG_CACHE = cfg
    return cfg


def user_config_path():
    """用户配置位置（永远可写）：%APPDATA%/一键盘库/config.json"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "一键盘库", "config.json")


def update_config(**kwargs):
    """把若干键写进用户配置（不动程序目录的 config.json），并刷新缓存。

    程序装在 Program Files 之类不可写目录时，写用户配置才不会失败。
    """
    global _CONFIG_CACHE
    p = user_config_path()
    data = {}
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    data.update(kwargs)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("写入用户配置失败：%s" % e)
    _CONFIG_CACHE = None
    return p


def write_default_config(path=None):
    """写出带注释的默认 config.json（不存在时才写）。"""
    p = path or config_path()
    if os.path.exists(p):
        return p
    with open(p, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    return p
