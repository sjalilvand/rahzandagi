@echo off
chcp 65001 >nul
python crawler_gui.py %*
if errorlevel 1 pause
