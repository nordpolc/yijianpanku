@echo off
chcp 936 >nul
cd /d "%~dp0"
title 安装依赖
echo 正在安装运行依赖 openpyxl / tkinterdnd2 ...
python -m pip install --upgrade openpyxl tkinterdnd2 -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo 清华源失败，改用官方源重试...
    python -m pip install --upgrade openpyxl tkinterdnd2
)
echo.
echo 完成。双击 运行.bat 启动。
pause
