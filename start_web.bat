@echo off
chcp 65001 >nul
python viewer.py %*
if errorlevel 1 pause
