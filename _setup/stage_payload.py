# -*- coding: utf-8 -*-
"""把 ..\dist\一键盘库 打成一个 payload.zip 供安装程序内嵌。"""
import os, shutil, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
APP = os.path.join(PROJ, "dist", "一键盘库")
STAGE = os.path.join(HERE, "stage", "一键盘库")
if not os.path.isdir(APP):
    raise SystemExit("缺少 %s，请先在上级目录执行 打包exe.bat" % APP)
if os.path.isdir(os.path.join(HERE, "stage")):
    shutil.rmtree(os.path.join(HERE, "stage"))
shutil.copytree(APP, STAGE)
shutil.copy2(os.path.join(HERE, "dist", "卸载.exe"), os.path.join(STAGE, "卸载.exe"))
shutil.copy2(os.path.join(PROJ, "使用说明.md"), os.path.join(STAGE, "使用说明.md"))
out = os.path.join(HERE, "payload.zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for root, _, files in os.walk(STAGE):
        for f in files:
            p = os.path.join(root, f)
            zf.write(p, os.path.relpath(p, STAGE))
print("payload.zip  %.1f MB" % (os.path.getsize(out) / 1048576.0))
