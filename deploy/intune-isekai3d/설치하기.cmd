@echo off
chcp 65001 >nul
title 이세계 사회인 3D 캐릭터 팩 설치
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-user.ps1"
echo.
pause
