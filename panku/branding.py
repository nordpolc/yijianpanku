# -*- coding: utf-8 -*-
"""品牌与视觉常量（颜色 / 字体 / logo 路径）。"""

import os
import sys

APP_NAME = "一键盘库"
APP_SUB = "批次清洗 · 自动套模板 · 输出盘点表"
APP_VERSION = "1.1.0"
AUTHOR = "Eason Chen"

# 中性色
BG = "#F4F6FB"
CARD = "#FFFFFF"
BORDER = "#E3E8F2"
INK = "#0F172A"
SUB = "#475569"
MUTED = "#94A3B8"

# 强调色（单一强调色 + 中性灰）
ACCENT = "#4F46E5"
ACCENT_HOVER = "#4338CA"
ACCENT_SOFT = "#EEF2FF"

OK = "#059669"
WARN = "#B45309"
DANGER = "#DC2626"

CONSOLE_BG = "#0B1220"
CONSOLE_FG = "#C7D2E4"

FONT = "Microsoft YaHei UI"
MONO = "Consolas"


def res_dir():
    """资源目录：打包后从 _MEIPASS 取，源码运行取项目根目录。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "资源")


def logo_path(name="logo.png"):
    p = os.path.join(res_dir(), name)
    return p if os.path.exists(p) else None


def app_dir():
    """程序所在目录（用户可见的目录，用于放 config/模板）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
