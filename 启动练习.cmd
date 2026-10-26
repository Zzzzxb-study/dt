@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
if exist .deps\django\__init__.py goto start
echo 正在安装项目依赖，首次启动需要联网……
python -m pip install --target .deps -r requirements.txt
if errorlevel 1 goto failed
:start
python tools\start_local.py
if errorlevel 1 goto failed
goto end
:nopython
echo 请先安装 Python 3.12 或更新版本，并勾选 Add Python to PATH。
goto failed
:failed
echo 启动未完成，请查看上方错误信息。
pause
:end
