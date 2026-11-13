@echo off
chcp 65001 > nul
title 쿨메신저 → spacekijun 알림
cd /d "%~dp0"
echo.
echo  쿨메신저에 새 쪽지가 오면 spacekijun 알림함으로 보냅니다.
echo  창을 닫거나 Ctrl+C 를 누르면 중지됩니다.
echo.
set PYTHONIOENCODING=utf-8
python ".claude\skills\coolmessenger\watch-messages.py" --interval 30
pause
