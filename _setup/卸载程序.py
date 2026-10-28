# -*- coding: utf-8 -*-
"""一键盘库 卸载程序"""
import os, shutil, subprocess, sys, winreg

APP_NAME = "一键盘库"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\一键盘库"
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
SILENT = "--silent" in sys.argv


def desktop_dirs():
    out = []
    up = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(up):
        out.append(up)
    pub = os.path.join(os.environ.get("PUBLIC") or r"C:\Users\Public", "Desktop")
    if os.path.isdir(pub) and pub not in out:
        out.append(pub)
    return out


def startmenu_dir():
    ap = os.environ.get("APPDATA") or ""
    return os.path.join(ap, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)


def remove_shortcuts(log):
    for d in desktop_dirs():
        p = os.path.join(d, APP_NAME + ".lnk")
        if os.path.exists(p):
            try:
                os.remove(p)
                log("已删除快捷方式：%s" % p)
            except OSError as e:
                log("删除失败 %s（%s）" % (p, e))
    sm = startmenu_dir()
    if os.path.isdir(sm):
        try:
            shutil.rmtree(sm)
            log("已删除开始菜单文件夹：%s" % sm)
        except OSError as e:
            log("删除失败 %s（%s）" % (sm, e))


def remove_registry(log):
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        log("已移除「程序和功能」中的条目")
    except FileNotFoundError:
        pass
    except OSError as e:
        log("移除注册表失败（%s）" % e)


def remove_files(log):
    keep = os.path.basename(sys.executable) if FROZEN else ""
    n = 0
    for name in os.listdir(HERE):
        if name == keep:
            continue
        p = os.path.join(HERE, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            n += 1
        except OSError as e:
            log("跳过 %s（%s）" % (name, e))
    log("已删除 %d 个文件/文件夹" % n)


def schedule_self_delete():
    if not FROZEN:
        return
    subprocess.Popen('ping -n 3 127.0.0.1 >nul & rmdir /s /q "%s"' % HERE,
                     shell=True, creationflags=0x00000008)


def main():
    lines = []
    def log(s):
        lines.append(s)
    if not SILENT:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        if not messagebox.askyesno("卸载 %s" % APP_NAME,
                                   "将从本机移除 %s。\n\n"
                                   "· 程序文件、桌面和开始菜单快捷方式、\n"
                                   "  「程序和功能」中的条目都会被删除\n"
                                   "· 你自己的模板和配置（%%APPDATA%%\\%s）会保留\n\n"
                                   "继续卸载？" % (APP_NAME, APP_NAME)):
            r.destroy()
            return
        r.destroy()
    remove_shortcuts(log)
    remove_registry(log)
    remove_files(log)
    schedule_self_delete()
    if not SILENT:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        r.attributes("-topmost", True)
        messagebox.showinfo("卸载完成", "%s 已卸载。\n\n你自己的模板与配置仍保留在：\n%%APPDATA%%\\%s" % (APP_NAME, APP_NAME))
        r.destroy()


if __name__ == "__main__":
    main()
