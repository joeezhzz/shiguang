@echo off
rem Shiguang launcher (console version, shows logs) — 调试专用
rem 前提：已安装 Python 3.10+（勾选 py launcher），并 pip install -r requirements.txt
cd /d "%~dp0"
py src\main.py
pause
