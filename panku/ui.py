# -*- coding: utf-8 -*-
"""一键盘库 —— 图形界面。"""

import datetime as _dt
import os
import queue
import re
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import engine
from .branding import (ACCENT, ACCENT_HOVER, ACCENT_SOFT, APP_NAME, APP_SUB, APP_VERSION,
                       AUTHOR, BG, BORDER, CARD, CONSOLE_BG, CONSOLE_FG, DANGER, FONT, INK,
                       MONO, MUTED, OK, SUB, WARN, logo_path)
from .config import load_config, update_config
from .detect import ROLE_LABEL, detect_workbook

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False

RE_DATE_IN_NAME = re.compile(r"(20\d{2})(\d{2})(\d{2})")


# ----------------------------------------------------------------- 小工具
def _shade(color, factor):
    """按比例调亮/调暗一个 #RRGGBB 颜色。"""
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    if factor >= 0:
        r, g, b = (int(c + (255 - c) * factor) for c in (r, g, b))
    else:
        r, g, b = (int(c * (1 + factor)) for c in (r, g, b))
    return "#%02X%02X%02X" % (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def _rounded_points(x1, y1, x2, y2, r):
    r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RButton(tk.Canvas):
    """圆角按钮（Canvas 绘制，支持 hover / 禁用）。"""

    def __init__(self, master, text, command=None, width=140, height=42, radius=10,
                 fill=ACCENT, fill_hover=None, fg="#FFFFFF", font=None, outline="",
                 parent_bg=None):
        bg = parent_bg or master.cget("bg")
        tk.Canvas.__init__(self, master, width=width, height=height, bg=bg,
                           highlightthickness=0, bd=0, cursor="hand2")
        self._fill = fill
        self._hover = fill_hover or _shade(fill, -0.12)
        self._fg = fg
        self._cmd = command
        self._enabled = True
        self._shape = self.create_polygon(
            _rounded_points(1, 1, width - 1, height - 1, radius),
            smooth=True, splinesteps=24, fill=fill, outline=outline)
        self._label = self.create_text(width / 2.0, height / 2.0, text=text, fill=fg,
                                       font=font or (FONT, 10, "bold"))
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _=None):
        if self._enabled:
            self.itemconfigure(self._shape, fill=self._hover)

    def _on_leave(self, _=None):
        if self._enabled:
            self.itemconfigure(self._shape, fill=self._fill)

    def _on_press(self, _=None):
        if self._enabled:
            self.itemconfigure(self._shape, fill=_shade(self._fill, -0.22))

    def _on_release(self, _=None):
        if not self._enabled:
            return
        self.itemconfigure(self._shape, fill=self._hover)
        if self._cmd:
            self._cmd()

    def set_text(self, text):
        self.itemconfigure(self._label, text=text)

    def set_enabled(self, ok):
        self._enabled = bool(ok)
        self.configure(cursor="hand2" if ok else "arrow")
        self.itemconfigure(self._shape, fill=self._fill if ok else "#E8ECF4")
        self.itemconfigure(self._label, fill=self._fg if ok else MUTED)


class Card(tk.Frame):
    """白色卡片：细边框 + 内边距。"""

    def __init__(self, master, **kw):
        kw.setdefault("bg", CARD)
        tk.Frame.__init__(self, master, bg=kw.pop("bg"), highlightbackground=BORDER,
                          highlightthickness=1, bd=0, **kw)


class ProgressBar(tk.Canvas):
    """圆角进度条：轨道常驻可见，进度用强调色填充。"""

    def __init__(self, master, height=10, bg=BG, track="#E7EBF4", fill=ACCENT):
        tk.Canvas.__init__(self, master, height=height, bg=bg,
                           highlightthickness=0, bd=0)
        self._h = height
        self._track = track
        self._fill = fill
        self._v = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, pct):
        try:
            self._v = max(0.0, min(100.0, float(pct)))
        except Exception:
            self._v = 0.0
        self._draw()

    def _bar(self, x1, x2, color):
        h = self._h
        r = h / 2.0
        x1, x2 = float(x1), float(x2)
        if x2 - x1 < h:
            x2 = x1 + h
        pts = [x1 + r, 0, x2 - r, 0, x2, 0, x2, r, x2, h - r, x2, h,
               x2 - r, h, x1 + r, h, x1, h, x1, h - r, x1, r, x1, 0]
        self.create_polygon(pts, smooth=True, splinesteps=12, fill=color, outline=color)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w <= 2:
            return
        self._bar(0, w, self._track)
        if self._v > 0:
            self._bar(0, max(self._h, w * self._v / 100.0), self._fill)


class DropZone(tk.Canvas):
    """虚线圆角拖放区。"""

    def __init__(self, master, on_click, height=96):
        tk.Canvas.__init__(self, master, height=height, bg=BG, highlightthickness=0, bd=0,
                           cursor="hand2")
        self._on_click = on_click
        self._hot = False
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", lambda e: self._on_click())
        self.bind("<Enter>", lambda e: self._draw())
        self.bind("<Leave>", lambda e: self._draw())

    def set_hot(self, hot):
        self._hot = bool(hot)
        self._draw()

    def _draw(self, _=None):
        self.delete("all")
        w = self.winfo_width() or 800
        h = self.winfo_height() or 96
        outline = ACCENT if self._hot else "#C7D2E4"
        fill = ACCENT_SOFT if self._hot else CARD
        self.create_polygon(_rounded_points(1, 1, w - 2, h - 2, 14), smooth=True,
                            splinesteps=24, fill=fill, outline=outline, width=1,
                            dash=(5, 4))
        title = "把库存导出表拖到这里，或点击选择文件" if HAS_DND else "点击选择库存导出表"
        self.create_text(w / 2.0, h / 2.0 - 12, text=title, fill=INK, font=(FONT, 11, "bold"))
        self.create_text(w / 2.0, h / 2.0 + 13,
                         text="支持 即时库存查询表 / 盘点模板 · 按表头自动识别，不看文件名",
                         fill=MUTED, font=(FONT, 9))


# ----------------------------------------------------------------- 主窗口
class App(object):
    def __init__(self):
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.title("%s  v%s" % (APP_NAME, APP_VERSION))
        self.root.configure(bg=BG)
        self._center(960, 716)
        self.root.minsize(880, 620)

        self.files = []           # [(path, role, label)]
        self.tpl = ""             # 用户自定义模板（空 = 内置）
        self.q = queue.Queue()
        self.running = False
        self.cancel_evt = None
        self._logo_img = None
        self._last_beat = 0.0
        self._warned_stall = False

        self._style()
        self._icon()
        self._build()
        self._refresh_tpl_label()
        self._poll()

    # ------------------------------------------------------------ 基础
    def _center(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.root.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def _style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK,
                     rowheight=30, font=(FONT, 10), borderwidth=0)
        st.configure("Treeview.Heading", background=CARD, foreground=SUB,
                     font=(FONT, 9, "bold"), relief="flat", borderwidth=0, padding=(6, 6))
        st.map("Treeview", background=[("selected", ACCENT_SOFT)],
               foreground=[("selected", INK)])
        st.map("Treeview.Heading", background=[("active", CARD)])
        st.configure("Bar.Horizontal.TProgressbar", troughcolor="#EDF0F7",
                     background=ACCENT, bordercolor="#EDF0F7", lightcolor=ACCENT,
                     darkcolor=ACCENT, thickness=8, borderwidth=0)
        st.configure("Slim.Vertical.TScrollbar", background="#D7DEEC", troughcolor=CARD,
                     bordercolor=CARD, arrowcolor=SUB, borderwidth=0, width=8)

    def _icon(self):
        p = logo_path()
        if not p:
            return
        try:
            self._icon_img = tk.PhotoImage(file=p)
            self.root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _build(self):
        self._header()
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(14, 0))
        self._dropzone(body)
        self._files_card(body)
        self._params_card(body)
        self._action_row(body)
        self._console(body)
        self._statusbar()

    def _header(self):
        head = tk.Frame(self.root, bg=CARD, height=80)
        head.pack(fill="x")
        head.pack_propagate(False)

        left = tk.Frame(head, bg=CARD)
        left.pack(side="left", padx=20)
        p = logo_path()
        if p:
            try:
                img = tk.PhotoImage(file=p)
                k = max(1, int(round(img.width() / 46.0)))
                self._logo_img = img.subsample(k) if k > 1 else img
                tk.Label(left, image=self._logo_img, bg=CARD).pack(side="left")
            except Exception:
                self._logo_img = None
        txt = tk.Frame(left, bg=CARD)
        txt.pack(side="left", padx=(12, 0))
        tk.Label(txt, text=APP_NAME, bg=CARD, fg=INK,
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(txt, text=APP_SUB, bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", pady=(3, 0))

        right = tk.Frame(head, bg=CARD)
        right.pack(side="right", padx=20)
        tk.Label(right, text=AUTHOR, bg=CARD, fg=SUB,
                 font=(FONT, 9, "bold")).pack(anchor="e")
        tk.Label(right, text="v" + APP_VERSION, bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="e", pady=(2, 0))

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

    def _dropzone(self, body):
        self.drop = DropZone(body, self.pick_files, height=84)
        self.drop.pack(fill="x")
        if HAS_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self._on_drop)
            try:
                self.drop.dnd_bind("<<DropEnter>>", lambda e: self.drop.set_hot(True))
                self.drop.dnd_bind("<<DropLeave>>", lambda e: self.drop.set_hot(False))
            except Exception:
                pass

    def _files_card(self, body):
        card = Card(body)
        card.pack(fill="x", pady=(14, 0))
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(top, text="已选文件", bg=CARD, fg=INK,
                 font=(FONT, 10, "bold")).pack(side="left")
        self.lbl_count = tk.Label(top, text="0", bg=CARD, fg=MUTED, font=(FONT, 9))
        self.lbl_count.pack(side="left", padx=(6, 0))

        RButton(top, "添加文件", self.pick_files, width=88, height=28, radius=7,
                fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).pack(side="right", padx=(6, 0))
        RButton(top, "移除选中", self.remove_selected, width=88, height=28, radius=7,
                fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).pack(side="right", padx=(6, 0))
        RButton(top, "清空", self.clear_files, width=64, height=28, radius=7,
                fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).pack(side="right", padx=(6, 0))

        wrap = tk.Frame(card, bg=CARD)
        wrap.pack(fill="x", padx=14, pady=(0, 12))
        cols = ("file", "role", "path")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=3)
        for c, t, w, a in (("file", "文件名", 330, "w"), ("role", "识别为", 108, "center"),
                           ("path", "路径", 400, "w")):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c == "path"))
        self.tree.tag_configure("odd", background="#FAFBFF")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview,
                           style="Slim.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _params_card(self, body):
        card = Card(body)
        card.pack(fill="x", pady=(12, 0))
        grid = tk.Frame(card, bg=CARD)
        grid.pack(fill="x", padx=14, pady=12)
        grid.columnconfigure(2, weight=1)

        cfg = load_config()
        self.var_wh = tk.StringVar(value=cfg.get("warehouse_default") or "")
        self.var_date = tk.StringVar(value=_dt.date.today().strftime("%Y-%m-%d"))
        self.var_out = tk.StringVar(value=_default_out())

        self._field(grid, 0, "仓库 / 寄售库", self.var_wh, 24)
        self._field(grid, 1, "盘点日期", self.var_date, 14)

        tk.Label(grid, text="输出目录", bg=CARD, fg=SUB,
                 font=(FONT, 9)).grid(row=0, column=2, sticky="w", padx=(18, 0))
        cell = tk.Frame(grid, bg=CARD)
        cell.grid(row=1, column=2, sticky="ew", padx=(18, 0))
        cell.columnconfigure(0, weight=1)
        e = tk.Entry(cell, textvariable=self.var_out, font=(FONT, 10), bg=CARD, fg=INK,
                     relief="flat", highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT, insertbackground=INK)
        e.grid(row=0, column=0, sticky="ew", ipady=5)
        RButton(cell, "浏览", self.pick_out, width=60, height=30, radius=7, fill=CARD,
                fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).grid(row=0, column=1, padx=(8, 0))

    def _field(self, grid, col, label, var, width):
        tk.Label(grid, text=label, bg=CARD, fg=SUB,
                 font=(FONT, 9)).grid(row=0, column=col, sticky="w",
                                      padx=(0, 0) if col == 0 else (18, 0))
        e = tk.Entry(grid, textvariable=var, width=width, font=(FONT, 10), bg=CARD, fg=INK,
                     relief="flat", highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT, insertbackground=INK)
        e.grid(row=1, column=col, sticky="w", ipady=5,
               padx=(0, 0) if col == 0 else (18, 0))

    def _action_row(self, body):
        box = tk.Frame(body, bg=BG)
        box.pack(fill="x", pady=(14, 0))

        line = tk.Frame(box, bg=BG)
        line.pack(fill="x")
        self.btn_run = RButton(line, "开始处理", self.start, width=168, height=44,
                               radius=11, fill=ACCENT, fill_hover=ACCENT_HOVER,
                               font=(FONT, 11, "bold"))
        self.btn_run.pack(side="left")
        self.btn_cancel = RButton(line, "取消", self.cancel, width=92, height=44, radius=11,
                                  fill="#E8ECF4", fill_hover="#DCE3EF", fg=SUB,
                                  font=(FONT, 10))
        self.btn_cancel.pack(side="left", padx=(10, 0))
        self.btn_cancel.set_enabled(False)
        self.btn_tpl = RButton(line, "模板管理", self.open_template, width=110, height=44,
                               radius=11, fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB,
                               outline=BORDER, font=(FONT, 10))
        self.btn_tpl.pack(side="left", padx=(10, 0))

        self.lbl_pct = tk.Label(line, text="就绪", bg=BG, fg=MUTED, font=(FONT, 9))
        self.lbl_pct.pack(side="right")

        self.prog = ProgressBar(box, height=10)
        self.prog.pack(fill="x", pady=(12, 2))

    def _console(self, body):
        wrap = tk.Frame(body, bg=CONSOLE_BG, highlightbackground="#1B2437",
                        highlightthickness=1, bd=0)
        wrap.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Text(wrap, height=6, font=(MONO, 9), bg=CONSOLE_BG, fg=CONSOLE_FG,
                           insertbackground=CONSOLE_FG, relief="flat", bd=0,
                           padx=14, pady=10, wrap="word")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview,
                           style="Slim.Vertical.TScrollbar")
        self.log.configure(yscrollcommand=sb.set, state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._log("就绪。选择库存导出表后点「开始处理」。")

    def _statusbar(self):
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))
        bar = tk.Frame(self.root, bg=CARD, height=30)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="作者 %s · v%s" % (AUTHOR, APP_VERSION), bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=18)
        self.lbl_tpl = tk.Label(bar, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
        self.lbl_tpl.pack(side="right", padx=18)
        self.lbl_state = tk.Label(bar, text="就绪", bg=CARD, fg=MUTED, font=(FONT, 9))
        self.lbl_state.pack(side="right", padx=(0, 18))

    # ------------------------------------------------------------ 文件
    def pick_files(self):
        if self.running:
            return
        ps = filedialog.askopenfilenames(
            title="选择库存导出表 / 盘点模板",
            filetypes=[("Excel 工作簿", "*.xlsx *.xlsm"), ("所有文件", "*.*")])
        if ps:
            self.add_files(list(ps))

    def _on_drop(self, event):
        self.drop.set_hot(False)
        raw = self.root.tk.splitlist(event.data)
        self.add_files([p for p in raw if p.lower().endswith((".xlsx", ".xlsm"))])

    def add_files(self, paths):
        for p in paths:
            if any(p == f[0] for f in self.files):
                continue
            try:
                d = detect_workbook(p)
                role = d["role"]
                label = ROLE_LABEL.get(role, "无法识别")
            except Exception as e:
                role, label = "unknown", "读取失败"
                self._log("识别失败 %s：%s" % (os.path.basename(p), e))
            if role == "template":
                self._use_template(p, quiet=True)
                continue
            self.files.append((p, role, label))
        self._refresh()
        self._autofill()
        self._autofill_date()

    def remove_selected(self):
        if self.running:
            return
        for iid in self.tree.selection():
            idx = int(self.tree.item(iid, "tags")[0]) if self.tree.item(iid, "tags") else -1
            if 0 <= idx < len(self.files):
                self.files[idx] = None
        self.files = [f for f in self.files if f]
        self._refresh()

    def clear_files(self):
        if self.running:
            return
        self.files = []
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, (p, role, label) in enumerate(self.files):
            self.tree.insert("", "end", values=(os.path.basename(p), label, p),
                             tags=(str(i), "odd" if i % 2 else ""))
        n_stock = len([f for f in self.files if f[1] in ("stock", "cleaned", "ledger")])
        self.lbl_count.configure(text="%d" % len(self.files))
        if n_stock:
            self.lbl_state.configure(text="库存表 %d" % n_stock, fg=OK)

    def _autofill(self):
        """从表里读仓库名，用户手工改过就不覆盖。"""
        stocks = [f[0] for f in self.files if f[1] in ("stock", "cleaned", "ledger")]
        if not stocks:
            return
        cfg = load_config()
        cur = self.var_wh.get().strip()
        if cur and cur != (cfg.get("warehouse_default") or ""):
            return
        try:
            wh = engine.peek_warehouse(stocks[0])
        except Exception:
            wh = ""
        if wh:
            self.var_wh.set(wh)
            self._log("已自动识别仓库：%s（可直接改）" % wh)

    def _autofill_date(self):
        for p, role, _ in self.files:
            if role not in ("stock", "cleaned", "ledger"):
                continue
            m = RE_DATE_IN_NAME.search(os.path.basename(p))
            if not m:
                continue
            try:
                d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            self.var_date.set(d.strftime("%Y-%m-%d"))
            return

    def pick_out(self):
        d = filedialog.askdirectory(title="选择输出目录",
                                    initialdir=self.var_out.get() or os.path.expanduser("~"))
        if d:
            self.var_out.set(d)

    # ------------------------------------------------------------ 模板
    def _use_template(self, path, quiet=False):
        self.tpl = path
        cfg = load_config()
        cfg["user_template"] = path
        try:
            update_config(user_template=path)
        except Exception:
            pass
        self._refresh_tpl_label()
        if not quiet:
            self._log("已切换模板：%s" % path)

    def _refresh_tpl_label(self):
        p = self.tpl or (load_config().get("user_template") or "")
        if p and os.path.exists(p):
            self.lbl_tpl.configure(text="模板：自定义（%s）" % os.path.basename(p), fg=SUB)
        else:
            self.tpl = ""
            self.lbl_tpl.configure(text="模板：内置", fg=MUTED)

    def open_template(self):
        TemplateDialog(self)

    # ------------------------------------------------------------ 运行
    def start(self):
        if self.running:
            return
        stocks = [f for f in self.files if f[1] in ("stock", "cleaned", "ledger")]
        if not stocks:
            messagebox.showwarning("还差一步", "请先选择库存导出表（含物料编码 / 批次 / 数量列）。")
            return
        out = self.var_out.get().strip()
        if not out:
            messagebox.showwarning("还差一步", "请填写输出目录。")
            return
        self.cancel_evt = threading.Event()
        self._job = {
            "paths": [f[0] for f in stocks],
            "out": out,
            "wh": self.var_wh.get().strip(),
            "date": self.var_date.get().strip(),
            "tpl": self.tpl or None,
        }
        self.running = True
        self._warned_stall = False
        self._last_beat = time.time()
        self.btn_run.set_enabled(False)
        self.btn_run.set_text("处理中…")
        self.btn_cancel.set_enabled(True)
        self.prog.set(0)
        self.lbl_pct.configure(text="0%", fg=SUB)
        self.lbl_state.configure(text="处理中", fg=WARN)
        self._log("-" * 46)
        th = threading.Thread(target=self._work, daemon=True)
        th.start()

    def _work(self):
        job = self._job
        try:
            res = engine.process(
                job["paths"], job["out"], job["wh"], job["date"], job["tpl"],
                log=lambda s: self.q.put(("log", s)),
                progress=lambda p, t: self.q.put(("prog", p, t)),
                cancel=self.cancel_evt)
            self.q.put(("done", res))
        except engine.Cancelled:
            self.q.put(("cancel", "已取消"))
        except Exception as e:
            self.q.put(("err", "%s: %s" % (type(e).__name__, e)))

    def cancel(self):
        if self.running and self.cancel_evt is not None:
            self.cancel_evt.set()
            self.btn_cancel.set_enabled(False)
            self.lbl_state.configure(text="正在取消…", fg=WARN)
            self._log("已请求取消，等待当前步骤结束…")

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                self._last_beat = time.time()
                kind = item[0]
                if kind == "log":
                    self._log(item[1])
                elif kind == "prog":
                    pct, text = item[1], item[2]
                    self.prog.set(max(0, min(100, pct)))
                    self.lbl_pct.configure(text="%d%%" % pct, fg=ACCENT)
                    if text:
                        self.lbl_state.configure(text=text, fg=SUB)
                elif kind == "done":
                    self._finish(item[1])
                elif kind == "cancel":
                    self._reset_ui("已取消", MUTED)
                    self._log("已取消。")
                elif kind == "err":
                    self._fail(item[1])
        except queue.Empty:
            pass
        if self.running and not self._warned_stall and time.time() - self._last_beat > 90:
            self._warned_stall = True
            self._log("⚠ 已 90 秒没有进展：可能被安全软件拦截写入，或文件正被 Excel 打开。"
                      "可以先点「取消」，换一个输出目录（如桌面）再试。")
        self.root.after(100, self._poll)

    def _finish(self, res):
        self._reset_ui("完成", OK)
        self.prog.set(100)
        self.lbl_pct.configure(text="100%", fg=OK)
        self._log("完成：库存 %d 行 → 盘点 %d 行，清洗 %d 行，合并 %d 组"
                  % (res["rows_in"], res["rows_out"], res["cleaned"], res["merged_groups"]))
        self._log("  正式盘点表：%s" % res["formal"])
        self._log("  清洗排查表：%s" % res["detail"])
        out_dir = os.path.dirname(res["formal"])
        if messagebox.askyesno("处理完成",
                               "已生成两份文件：\n%s\n%s\n\n现在打开输出目录吗？"
                               % (os.path.basename(res["formal"]),
                                  os.path.basename(res["detail"]))):
            _open_dir(out_dir)

    def _fail(self, msg):
        self._reset_ui("失败", DANGER)
        self._log("✗ " + msg)
        tip = ""
        if "PermissionError" in msg or "Permission denied" in msg:
            tip = "\n\n提示：输出文件可能被 Excel 打开，或被杀毒软件拦截。\n" \
                  "关掉同名文件后重试，或换一个输出目录。"
        elif "不可写" in msg:
            tip = "\n\n提示：请换一个输出目录（例如桌面）。"
        messagebox.showerror("处理失败", msg + tip)

    def _reset_ui(self, state, color):
        self.running = False
        self.btn_run.set_enabled(True)
        self.btn_run.set_text("开始处理")
        self.btn_cancel.set_enabled(False)
        self.lbl_state.configure(text=state, fg=color)

    # ------------------------------------------------------------ 杂项
    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", str(text) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self):
        self.root.mainloop()


# ----------------------------------------------------------------- 模板对话框
class TemplateDialog(tk.Toplevel):
    def __init__(self, app):
        tk.Toplevel.__init__(self, app.root)
        self.app = app
        self.title("模板管理")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app.root)
        w, h = 620, 340
        x = app.root.winfo_rootx() + (app.root.winfo_width() - w) // 2
        y = app.root.winfo_rooty() + 120
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))
        self._build()
        try:
            self.grab_set()
        except Exception:
            pass

    def _build(self):
        tk.Label(self, text="盘点模板", bg=BG, fg=INK,
                 font=(FONT, 13, "bold")).pack(anchor="w", padx=22, pady=(20, 2))
        tk.Label(self, text="默认使用内置模板；也可以换成你自己维护的模板文件，"
                            "程序会记住这个选择。", bg=BG, fg=MUTED,
                 font=(FONT, 9), wraplength=560, justify="left").pack(anchor="w", padx=22)

        card = Card(self)
        card.pack(fill="x", padx=22, pady=14)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=14)

        self.lbl_kind = tk.Label(inner, text="", bg=CARD, fg=INK, font=(FONT, 10, "bold"))
        self.lbl_kind.pack(anchor="w")
        self.lbl_path = tk.Label(inner, text="", bg=CARD, fg=SUB, font=(FONT, 9),
                                 wraplength=540, justify="left")
        self.lbl_path.pack(anchor="w", pady=(4, 6))
        self.lbl_check = tk.Label(inner, text="", bg=CARD, fg=MUTED, font=(FONT, 9),
                                  wraplength=540, justify="left")
        self.lbl_check.pack(anchor="w")

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=22)
        RButton(bar, "选择模板文件…", self._pick, width=132, height=38, radius=9,
                fill=ACCENT, fill_hover=ACCENT_HOVER, font=(FONT, 10)).pack(side="left")
        RButton(bar, "打开所在文件夹", self._open_dir, width=132, height=38, radius=9,
                fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).pack(side="left", padx=8)
        RButton(bar, "恢复内置模板", self._reset, width=132, height=38, radius=9,
                fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).pack(side="left")
        RButton(bar, "关闭", self.destroy, width=80, height=38, radius=9,
                fill=CARD, fill_hover=ACCENT_SOFT, fg=SUB, outline=BORDER,
                font=(FONT, 9)).pack(side="right")

        self._refresh()

    def _current(self):
        p = self.app.tpl or (load_config().get("user_template") or "")
        if p and os.path.exists(p):
            return p, True
        try:
            from .template import template_path
            return template_path(), False
        except Exception:
            return "", False

    def _refresh(self):
        p, custom = self._current()
        if not p:
            self.lbl_kind.configure(text="找不到模板", fg=DANGER)
            self.lbl_path.configure(text="")
            self.lbl_check.configure(text="")
            return
        self.lbl_kind.configure(text="自定义模板" if custom else "内置模板", fg=ACCENT)
        self.lbl_path.configure(text=p)
        ok, msg = _validate_template(p)
        self.lbl_check.configure(text=("✓ " if ok else "✗ ") + msg, fg=OK if ok else DANGER)

    def _pick(self):
        p = filedialog.askopenfilename(title="选择盘点模板",
                                       filetypes=[("Excel 工作簿", "*.xlsx *.xlsm")])
        if not p:
            return
        ok, msg = _validate_template(p)
        if not ok:
            if not messagebox.askyesno("模板可能不适用", msg + "\n\n仍然使用这个文件吗？"):
                return
        dst_dir = _user_template_dir()
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, "盘点模板_%s.xlsx" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
        try:
            shutil.copy2(p, dst)
        except Exception as e:
            messagebox.showerror("复制失败", "%s\n\n请把模板文件放到一个可写目录后重试。" % e)
            return
        self.app._use_template(dst)
        self._refresh()

    def _reset(self):
        self.app.tpl = ""
        try:
            update_config(user_template="")
        except Exception:
            pass
        self.app._refresh_tpl_label()
        self._refresh()

    def _open_dir(self):
        p, _ = self._current()
        if p:
            _open_dir(os.path.dirname(p))


def _validate_template(path):
    """检查模板是否含「账面数量 / 盘点数量」列。"""
    try:
        d = detect_workbook(path)
    except Exception as e:
        return False, "读不出这个文件：%s" % e
    cols = d.get("columns") or {}
    miss = [n for k, n in (("book_qty", "账面数量"), ("count_qty", "盘点数量")) if k not in cols]
    if miss:
        return False, "这个模板缺少列：%s（程序需要这两列来填写数量）。" % "、".join(miss)
    return True, "模板可用：%s [%s]" % (d.get("file", ""), d.get("sheet", ""))


def _user_template_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "一键盘库", "模板")


def _default_out():
    desk = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desk):
        desk = os.path.expanduser("~")
    return os.path.join(desk, "盘库输出")


def _open_dir(path):
    try:
        if os.path.isdir(path):
            os.startfile(path)
    except Exception:
        pass


def main():
    app = App()
    app.run()
