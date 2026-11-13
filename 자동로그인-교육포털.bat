@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 전북 업무포털 자동 로그인
node "%~dp0scripts\auto-login.js" eduptl
if errorlevel 1 pause
