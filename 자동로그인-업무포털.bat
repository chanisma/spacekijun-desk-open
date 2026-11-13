@echo off
chcp 65001 >nul
cd /d "%~dp0"
title K-에듀파인 업무포털 자동 로그인
node "%~dp0scripts\auto-login.js" klef
if errorlevel 1 pause
