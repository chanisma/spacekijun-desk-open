@echo off
chcp 65001 > nul
title 쿨메신저 실행 (자동화용)
echo.
echo  쿨메신저를 자동화용 옵션(--remote-debugging-port=9222)으로 다시 실행합니다.
echo  본문 입력에 이 옵션이 필요합니다. 옵션 없이 켜져 있으면 답장 발송이 실패합니다.
echo.
tasklist /FI "IMAGENAME eq CoolMessenger.exe" 2>nul | find /I "CoolMessenger.exe" >nul
if not errorlevel 1 (
  echo  [주의] 쿨메신저가 이미 실행 중입니다. 종료 후 다시 켭니다.
  echo         작성 중인 쪽지가 있으면 먼저 저장하세요.
  echo.
  pause
  taskkill /IM CoolMessenger.exe /F >nul 2>&1
  timeout /t 3 /nobreak >nul
)
start "" "C:\Program Files (x86)\CoolMessenger Gentoo\CoolMessenger.exe" --remote-debugging-port=9222
echo  실행했습니다. 로그인 창이 뜨면 로그인해 주세요.
timeout /t 3 /nobreak >nul
