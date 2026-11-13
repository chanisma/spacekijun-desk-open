@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem 스페이스기전 교실 — 교실 PC 에 QR 을 띄우고, 교사가 휴대폰으로 승인하면 그 교사의 반별 세팅을 펼친다.
rem 데스크·학생판과 저장 폴더가 따로다(%LOCALAPPDATA%\SpacekijunClassroom).
python -c "import webview, psutil, segno" 2>nul || (
  echo 필요한 모듈을 설치합니다...
  python -m pip install -r app\requirements.txt || (pause & exit /b 1)
)
start "" pythonw app\classroom.py
