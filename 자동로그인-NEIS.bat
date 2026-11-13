@echo off
chcp 65001 >nul
cd /d "%~dp0"
title NEIS 자동 로그인
node "%~dp0scripts\auto-login.js" neis
if errorlevel 1 pause
