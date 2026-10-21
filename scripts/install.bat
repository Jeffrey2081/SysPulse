@echo off
title SysPulse Windows Installer
echo Starting SysPulse Setup...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
