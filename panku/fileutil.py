# -*- coding: utf-8 -*-
"""落盘工具：目标文件被占用时主动跳过，自动改名（精确到秒），避免整轮处理白跑。"""

import datetime as _dt
import os
import tempfile


def dir_writable(d):
    """输出目录是否可写（顺便确认目录存在）。

    只用一次真实的小文件写入判断：mkstemp 在某些受限环境下会卡住（已踩过坑）。
    """
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return False
    probe = os.path.join(d, ".pkw_probe_%d.tmp" % os.getpid())
    try:
        with open(probe, "wb") as f:
            f.write(b"0")
        return True
    except Exception:
        return False
    finally:
        try:
            os.remove(probe)
        except Exception:
            pass


def pick_out_dir(requested, log=print, app_dir=None):
    """返回第一个真正可写的输出目录，并说明改道原因。

    顺序：用户指定 -> 桌面\盘库输出 -> 文档\盘库输出 -> 程序目录\输出 -> 临时目录\盘库输出
    """
    home = os.path.expanduser("~")
    cands = []
    if requested:
        cands.append(requested)
    for nm in ("Desktop", "Documents"):
        d = os.path.join(home, nm)
        if os.path.isdir(d):
            cands.append(os.path.join(d, "盘库输出"))
    if app_dir:
        cands.append(os.path.join(app_dir, "输出"))
    tmp = tempfile.gettempdir()
    if tmp:
        cands.append(os.path.join(tmp, "盘库输出"))

    want = os.path.abspath(requested) if requested else None
    seen = set()
    for d in cands:
        d = os.path.abspath(d)
        if d in seen:
            continue
        seen.add(d)
        if dir_writable(d):
            if want and d != want:
                log("⚠ 输出目录不可写：%s" % requested)
                log("  已自动改到：%s" % d)
                log("  提示：把程序文件夹放到桌面等普通位置运行，就不会有写入限制。")
            return d
    return requested


def is_locked(path):
    """文件是否被别的进程占着（Excel 打开、杀软扫描、只读属性都算）。

    用 share=0 独占打开探测：打不开且错误码是 5（拒绝访问）= 被占用；
    文件不存在（错误码 2/3）视为未占用。
    """
    if os.name != "nt" or not os.path.exists(path):
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
    OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL = 3, 0x80
    INVALID = ctypes.c_void_p(-1).value
    h = k32.CreateFileW(ctypes.c_wchar_p(path), GENERIC_READ | GENERIC_WRITE, 0,
                        None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
    if h in (INVALID, 0xFFFFFFFFFFFFFFFF, -1):
        err = ctypes.get_last_error()
        # 5=拒绝访问（只读/ACL）、32=共享冲突（Excel 打开）、33=锁冲突
        return err in (5, 32, 33)
    k32.CloseHandle(ctypes.c_void_p(h))
    return False


def stamp_name(path, when=None):
    """生成 名称_20261028_102546.xlsx；同秒已存在则加 _2、_3。"""
    when = when or _dt.datetime.now()
    base, ext = os.path.splitext(path)
    tag = when.strftime("%Y%m%d_%H%M%S")
    p = "%s_%s%s" % (base, tag, ext)
    n = 2
    while os.path.exists(p):
        p = "%s_%s_%d%s" % (base, tag, n, ext)
        n += 1
    return p


def describe(path):
    """给日志用的一句话现场描述。"""
    bits = []
    if os.path.exists(path):
        bits.append("已存在")
        try:
            bits.append("只读" if not os.access(path, os.W_OK) else "可写")
        except Exception:
            pass
        bits.append("%d 字节" % os.path.getsize(path))
    else:
        bits.append("不存在")
    bits.append("占用" if is_locked(path) else "未占用")
    d = os.path.dirname(path)
    bits.append("目录" + ("可写" if dir_writable(d) else "不可写"))
    return "、".join(bits)


def save_wb(wb, path, log=print):
    """保存工作簿，返回实际保存路径。

    目标被占用时：主动跳过原文件名，另存为 名称_YYYYMMDD_HHMMSS.xlsx。
    """
    target = path
    if is_locked(path):
        scene = describe(path)
        target = stamp_name(path)
        log("跳过 %s：文件被占用（Excel 打开 / 杀毒软件锁定 / 只读），改存为 %s"
            % (os.path.basename(path), os.path.basename(target)))
        log("  现场：%s" % scene)
    try:
        wb.save(target)
    except PermissionError:
        if target == path:
            target = stamp_name(path)
            log("跳过 %s：写入被拒绝，改存为 %s"
                % (os.path.basename(path), os.path.basename(target)))
            try:
                wb.save(target)
            except PermissionError:
                raise PermissionError(
                    "无法写入 %s\n现场：%s\n输出目录：%s"
                    % (os.path.basename(target), describe(target), os.path.dirname(target)))
        else:
            raise PermissionError(
                "无法写入 %s\n现场：%s\n输出目录：%s"
                % (os.path.basename(target), describe(target), os.path.dirname(target)))
    if target != path:
        log("已另存为：%s" % os.path.basename(target))
    return target
