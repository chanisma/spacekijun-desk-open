@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 전북 NEIS / K-에듀파인 자동 로그인
echo.
echo  == 전북 NEIS / K-에듀파인 자동 로그인 ==
echo.
where node >nul 2>&1
if errorlevel 1 (
  echo [오류] Node.js가 설치돼 있지 않습니다. https://nodejs.org 에서 설치하세요.
  pause
  exit /b 1
)
node "%~dp0scripts\auto-login.js" %1 %2
if errorlevel 1 pause
