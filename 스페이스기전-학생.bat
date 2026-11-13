@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem 스페이스기전 학생 — 학생판 독 (바로가기·다마고찌·별까지 쌓기·시간표·캡처·클립보드).
rem 교사판 데스크와 저장 폴더가 따로라 한 PC 에 함께 있어도 섞이지 않는다.
python -c "import webview, pystray, psutil" 2>nul || (
  echo 필요한 모듈을 설치합니다...
  python -m pip install -r app\requirements.txt || (pause & exit /b 1)
)
start "" pythonw app\student.py
