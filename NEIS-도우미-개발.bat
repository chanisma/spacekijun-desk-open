@echo off
chcp 65001 >nul
cd /d "%~dp0"
title NEIS 도우미 개발용 실행
echo.
echo  == NEIS 도우미 개발용 실행 ==
echo.
echo  인증서 자동 로그인부터 데스크와 같은 코드로 돌립니다.
echo  창이 뜨면 오른쪽 아래 [도우미] 를 눌러 하려는 업무를 말해 보세요.
echo  app/web/neis-overlay.js 를 저장하면 로그인을 유지한 채 패널만 다시 심습니다.
echo  창을 닫으면 끝납니다.
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo [오류] Python 이 설치돼 있지 않습니다. https://www.python.org 에서 설치하세요.
  echo.
  pause
  exit /b 1
)
python "%~dp0scripts/dev-neis-assist.py" %*
echo.
rem 더블클릭으로 열었을 때 마지막 줄을 읽을 수 있도록 항상 멈춘다.
pause
