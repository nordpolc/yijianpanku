@echo off
chcp 936 >nul
cd /d "%~dp0"
title 打包安装包
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python
    pause
    exit /b 1
)
if not exist "..\dist\一键盘库\一键盘库.exe" (
    echo [错误] 还没有打包主程序，请先运行上级目录的 打包exe.bat
    pause
    exit /b 1
)

echo [1/3] 打包卸载程序...
python -m PyInstaller --noconfirm --onefile --windowed --name 卸载 --icon "..\资源\logo.ico" 卸载程序.py
if errorlevel 1 goto fail

echo [2/3] 生成 payload.zip...
python stage_payload.py
if errorlevel 1 goto fail

echo [3/3] 打包安装程序...
python -m PyInstaller --noconfirm --onefile --windowed --name 一键盘库安装程序_v1.1.0 ^
  --icon "..\资源\logo.ico" ^
  --version-file version_setup.txt ^
  --add-data "payload.zip;." ^
  --add-data "..\资源;资源" ^
  安装程序.py
if errorlevel 1 goto fail

echo.
echo 完成：dist\一键盘库安装程序_v1.1.0.exe
echo 交付时把它和 ..\dist\一键盘库 一起放到桌面「一键盘库程序」里。
pause
exit /b 0

:fail
echo.
echo [错误] 打包失败，请把上面的报错发出来
pause
exit /b 1
