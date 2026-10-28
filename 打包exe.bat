@echo off
chcp 936 >nul
cd /d "%~dp0"
title 打包 exe

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Python，请先安装 Python 3.10+ 并勾选 Add to PATH
    pause
    exit /b 1
)

echo 安装/更新依赖...
python -m pip install --upgrade pyinstaller openpyxl tkinterdnd2
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo 清理旧产物...
if exist build rmdir /s /q build
if exist "dist\一键盘库" rmdir /s /q "dist\一键盘库"
if exist "一键盘库.spec" del /q "一键盘库.spec"

echo 打包中（约 1 分钟）...
python -m PyInstaller --noconfirm --onedir --windowed ^
  --name 一键盘库 ^
  --icon "资源\logo.ico" ^
  --version-file version_info.txt ^
  --add-data "模板;模板" ^
  --add-data "config.json;." ^
  --add-data "资源;资源" ^
  --collect-all tkinterdnd2 ^
  一键盘库.py
if errorlevel 1 (
    echo [错误] 打包失败，请把上面的报错发出来
    pause
    exit /b 1
)

echo.
echo 打包完成：dist\一键盘库\一键盘库.exe
echo 交付时要把整个 dist\一键盘库 文件夹一起拷走（_internal 不能少）。
pause
