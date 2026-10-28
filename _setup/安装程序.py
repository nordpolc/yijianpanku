# -*- coding: utf-8 -*-
"""一键盘库 安装程序（装到当前用户目录，不需要管理员权限）"""
import base64, os, queue, shutil, subprocess, sys, threading, time, zipfile, winreg
import tkinter as tk
from tkinter import filedialog, messagebox

APP_NAME = "一键盘库"
APP_VERSION = "1.1.0"
PUBLISHER = "Eason Chen"
APP_EXE = "一键盘库.exe"
UNINST_EXE = "卸载.exe"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\一键盘库"
NO_WINDOW = 0x08000000

BG = "#F4F6FB"; CARD = "#FFFFFF"; BORDER = "#E3E8F2"; INK = "#0F172A"
SUB = "#475569"; MUTED = "#94A3B8"; ACCENT = "#4F46E5"; ACCENT_HOVER = "#4338CA"
ACCENT_SOFT = "#EEF2FF"; OK = "#059669"; DANGER = "#DC2626"
FONT = "Microsoft YaHei UI"


def res_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def payload():
    return os.path.join(res_dir(), "payload.zip")


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", APP_NAME)


def payload_mb():
    try:
        return os.path.getsize(payload()) / 1024.0 / 1024.0
    except OSError:
        return 0.0


def run_ps(script):
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", enc], creationflags=NO_WINDOW, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_shortcut(lnk, target, workdir, desc):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
          "$s.TargetPath='%s';$s.WorkingDirectory='%s';$s.IconLocation='%s,0';"
          "$s.Description='%s';$s.Save()") % (lnk, target, workdir, target, desc)
    run_ps(ps)


def dir_size_kb(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total // 1024


def write_registry(dest):
    exe = os.path.join(dest, APP_EXE)
    uninst = os.path.join(dest, UNINST_EXE)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
    vals = [("DisplayName", winreg.REG_SZ, APP_NAME),
            ("DisplayVersion", winreg.REG_SZ, APP_VERSION),
            ("DisplayIcon", winreg.REG_SZ, exe),
            ("Publisher", winreg.REG_SZ, PUBLISHER),
            ("InstallLocation", winreg.REG_SZ, dest),
            ("InstallDate", winreg.REG_SZ, time.strftime("%Y%m%d")),
            ("UninstallString", winreg.REG_SZ, '"%s"' % uninst),
            ("QuietUninstallString", winreg.REG_SZ, '"%s" --silent' % uninst),
            ("EstimatedSize", winreg.REG_DWORD, dir_size_kb(dest)),
            ("NoModify", winreg.REG_DWORD, 1),
            ("NoRepair", winreg.REG_DWORD, 1)]
    for name, typ, val in vals:
        winreg.SetValueEx(key, name, 0, typ, val)
    winreg.CloseKey(key)


def install(dest, desktop_sc, startmenu_sc, progress):
    dest = os.path.abspath(dest)
    progress(3, "检查安装位置")
    os.makedirs(dest, exist_ok=True)
    probe = os.path.join(dest, ".pkw_setup_probe")
    with open(probe, "w") as f:
        f.write("ok")
    os.remove(probe)

    progress(8, "清理旧版本文件")
    for n in os.listdir(dest):
        p = os.path.join(dest, n)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass

    progress(20, "解压程序文件（约 %d MB）" % int(payload_mb()))
    with zipfile.ZipFile(payload()) as zf:
        names = zf.namelist()
        zf.extractall(dest)

    progress(72, "创建快捷方式")
    exe = os.path.join(dest, APP_EXE)
    if not os.path.exists(exe):
        raise RuntimeError("解压后没有找到 %s" % APP_EXE)
    if desktop_sc:
        d = os.path.join(os.path.expanduser("~"), "Desktop")
        make_shortcut(os.path.join(d, APP_NAME + ".lnk"), exe, dest, APP_NAME)
    if startmenu_sc:
        sm = os.path.join(os.environ.get("APPDATA") or "",
                          "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)
        os.makedirs(sm, exist_ok=True)
        make_shortcut(os.path.join(sm, APP_NAME + ".lnk"), exe, dest, APP_NAME)

    progress(88, "登记到「程序和功能」")
    write_registry(dest)
    progress(100, "安装完成")
    return exe


# ---------------------------------------------------------------- 界面
class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.done = False
        self.exe = None
        root.title("%s 安装程序  v%s" % (APP_NAME, APP_VERSION))
        root.configure(bg=BG)
        root.resizable(False, False)
        w, h = 720, 468
        x = max(0, (root.winfo_screenwidth() - w) // 2)
        y = max(0, (root.winfo_screenheight() - h) // 3)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.var_dir = tk.StringVar(value=default_dir())
        self.var_desktop = tk.BooleanVar(value=True)
        self.var_startmenu = tk.BooleanVar(value=True)
        self.var_launch = tk.BooleanVar(value=True)
        self._icon()
        self._header()
        self._body()
        self._footer()
        self.root.after(80, self._poll)

    def _icon(self):
        p = os.path.join(res_dir(), "资源", "logo.png")
        if os.path.exists(p):
            try:
                self._img = tk.PhotoImage(file=p)
                self.root.iconphoto(True, self._img)
            except Exception:
                pass

    def _header(self):
        hd = tk.Frame(self.root, bg=CARD, height=96)
        hd.pack(fill="x")
        hd.pack_propagate(False)
        p = os.path.join(res_dir(), "资源", "logo.png")
        if os.path.exists(p):
            try:
                img = tk.PhotoImage(file=p)
                k = max(1, round(img.width() / 46.0))
                self._logo = img.subsample(k) if k > 1 else img
                tk.Label(hd, image=self._logo, bg=CARD).pack(side="left", padx=(22, 14), pady=18)
            except Exception:
                pass
        box = tk.Frame(hd, bg=CARD)
        box.pack(side="left", pady=(20, 0))
        tk.Label(box, text=APP_NAME + " 安装程序", bg=CARD, fg=INK,
                 font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(box, text="批次清洗 · 自动套模板 · 输出盘点表", bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", pady=(2, 0))
        tk.Label(hd, text="Eason Chen", bg=CARD, fg=SUB,
                 font=(FONT, 9, "bold")).pack(side="right", padx=22)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

    def _body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(18, 0))
        card = tk.Frame(body, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        tk.Label(card, text="安装位置", bg=CARD, fg=SUB, font=(FONT, 9)).pack(anchor="w", padx=16, pady=(14, 4))
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=16)
        self.ent = tk.Entry(row, textvariable=self.var_dir, font=(FONT, 10), relief="solid",
                            bd=1, bg="#FFFFFF", fg=INK, insertbackground=INK)
        self.ent.pack(side="left", fill="x", expand=True, ipady=5)
        tk.Button(row, text="浏览…", command=self._browse, font=(FONT, 9), relief="solid", bd=1,
                  bg="#FFFFFF", fg=SUB, activebackground=ACCENT_SOFT, padx=12, cursor="hand2"
                  ).pack(side="left", padx=(8, 0), ipady=3)
        tk.Label(card, text="装到当前用户目录，不需要管理员权限；卸载在「设置 → 应用」里点卸载即可。",
                 bg=CARD, fg=MUTED, font=(FONT, 8)).pack(anchor="w", padx=16, pady=(6, 0))
        opts = tk.Frame(card, bg=CARD)
        opts.pack(fill="x", padx=16, pady=(12, 16))
        for text, var in (("创建桌面快捷方式", self.var_desktop), ("创建开始菜单快捷方式", self.var_startmenu)):
            tk.Checkbutton(opts, text=text, variable=var, bg=CARD, fg=SUB, font=(FONT, 9),
                           activebackground=CARD, selectcolor="#FFFFFF", bd=0,
                           highlightthickness=0).pack(side="left", padx=(0, 24))
        tk.Label(body, text="安装内容：程序本体、内置盘点模板、程序图标、卸载程序。磁盘占用约 %d MB。"
                            % max(1, int(payload_mb() * 1.9)),
                 bg=BG, fg=MUTED, font=(FONT, 8), wraplength=640, justify="left"
                 ).pack(anchor="w", pady=(10, 0))
        self.done_frame = tk.Frame(body, bg=BG)

    def _footer(self):
        foot = tk.Frame(self.root, bg=BG)
        foot.pack(fill="x", padx=22, pady=(10, 16))
        self.prog = tk.Canvas(foot, height=10, bg=BG, highlightthickness=0)
        self.prog.pack(fill="x")
        self.prog.bind("<Configure>", lambda e: self._draw_prog(self._pct))
        self._pct = 0
        info = tk.Frame(foot, bg=BG)
        info.pack(fill="x", pady=(6, 10))
        self.lbl_state = tk.Label(info, text="就绪，点「开始安装」", bg=BG, fg=SUB, font=(FONT, 9))
        self.lbl_state.pack(side="left")
        self.lbl_pct = tk.Label(info, text="", bg=BG, fg=ACCENT, font=(FONT, 9, "bold"))
        self.lbl_pct.pack(side="right")
        btns = tk.Frame(foot, bg=BG)
        btns.pack(fill="x")
        self.btn_go = tk.Button(btns, text="开始安装", command=self.start, font=(FONT, 10, "bold"),
                                bg=ACCENT, fg="#FFFFFF", activebackground=ACCENT_HOVER,
                                activeforeground="#FFFFFF", relief="flat", bd=0, padx=26, pady=8,
                                cursor="hand2")
        self.btn_go.pack(side="left")
        self.btn_quit = tk.Button(btns, text="退出", command=self.root.destroy, font=(FONT, 10),
                                  bg="#FFFFFF", fg=SUB, activebackground=ACCENT_SOFT, relief="solid",
                                  bd=1, padx=22, pady=7, cursor="hand2")
        self.btn_quit.pack(side="left", padx=(10, 0))
        self.chk_launch = tk.Checkbutton(btns, text="立即启动一键盘库", variable=self.var_launch,
                                         bg=BG, fg=SUB, font=(FONT, 9), activebackground=BG,
                                         bd=0, highlightthickness=0, state="disabled")

    def _draw_prog(self, pct):
        c = self.prog
        c.delete("all")
        w = c.winfo_width() or 600
        c.create_rectangle(0, 1, w, 9, fill="#E7EBF4", outline="")
        if pct:
            c.create_rectangle(0, 1, max(2, int(w * pct / 100.0)), 9, fill=ACCENT, outline="")

    def _browse(self):
        d = filedialog.askdirectory(title="选择安装位置", initialdir=os.path.dirname(self.var_dir.get()) or None)
        if d:
            self.var_dir.set(os.path.join(d, APP_NAME))

    def start(self):
        dest = self.var_dir.get().strip()
        if not dest:
            messagebox.showwarning("提示", "请先选择安装位置。")
            return
        self.btn_go.configure(state="disabled", text="安装中…")
        self.btn_quit.configure(state="disabled")
        self.ent.configure(state="disabled")
        self.lbl_state.configure(text="准备安装")
        threading.Thread(target=self._work, args=(dest, self.var_desktop.get(),
                                                  self.var_startmenu.get()), daemon=True).start()

    def _work(self, dest, dsc, ssc):
        def progress(pct, text):
            self.q.put(("p", pct, text))
        try:
            exe = install(dest, dsc, ssc, progress)
            self.q.put(("done", exe))
        except Exception as e:
            self.q.put(("err", str(e)))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "p":
                    self._pct = item[1]
                    self._draw_prog(self._pct)
                    self.lbl_pct.configure(text="%d%%" % item[1])
                    self.lbl_state.configure(text=item[2])
                elif item[0] == "done":
                    self._finish(item[1])
                elif item[0] == "err":
                    self._fail(item[1])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _finish(self, exe):
        self.done = True
        self.exe = exe
        self._pct = 100
        self._draw_prog(100)
        self.lbl_pct.configure(text="100%", fg=OK)
        self.lbl_state.configure(text="安装完成", fg=OK)
        self.btn_go.configure(state="disabled", text="已安装")
        self.btn_quit.configure(state="normal", text="完成", command=self._close)
        self.chk_launch.configure(state="normal")
        self.chk_launch.pack(side="right")

    def _fail(self, msg):
        self.lbl_state.configure(text="安装失败", fg=DANGER)
        self.btn_go.configure(state="normal", text="重试")
        self.btn_quit.configure(state="normal")
        self.ent.configure(state="normal")
        messagebox.showerror("安装失败", "安装没有完成：\n\n%s\n\n可以换一个安装位置后重试。" % msg)

    def _close(self):
        if self.var_launch.get() and self.exe and os.path.exists(self.exe):
            try:
                os.startfile(self.exe)
            except OSError:
                pass
        self.root.destroy()


def main():
    args = sys.argv[1:]
    if "--silent" in args:
        dest = default_dir()
        dsc = ssc = True
        for a in args:
            if a.startswith("--dir="):
                dest = a[6:]
            elif a == "--desktop=0":
                dsc = False
            elif a == "--startmenu=0":
                ssc = False
        exe = install(dest, dsc, ssc, lambda p, t: None)
        print("INSTALLED", exe)
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
