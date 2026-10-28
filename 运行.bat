@echo off
chcp 936 >nul
cd /d "%~dp0"
title 一键盘库
if exist "dist\一键盘库\一键盘库.exe" (
    start "" "dist\一键盘库\一键盘库.exe"
    exit /b
)
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python，也没有打包好的 exe
    echo 请先双击 安装依赖.bat，或使用 dist\一键盘库\一键盘库.exe
    pause
    exit /b 1
)
python 一键盘库.py
if errorlevel 1 pause
