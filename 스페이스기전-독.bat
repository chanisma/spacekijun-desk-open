@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem 스페이스기전 독 — 바탕화면 아래 가운데에 아이콘 줄을 띄운다.
rem 데스크와 같은 프로그램이다(app/desktop.py). 독을 한 번 켜면 다음 실행부터 기억한다.
rem 콘솔 창이 남지 않게 pythonw 로 띄우고, 그 전에 필요한 모듈이 있는지만 확인한다.
python -c "import webview, pystray, playwright, psutil" 2>nul || (
  echo 필요한 모듈을 설치합니다...
  python -m pip install -r app\requirements.txt || (pause & exit /b 1)
)
start "" pythonw app\packaged.py --dock
