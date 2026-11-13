"""교사용(데스크)·학생용 어느 판으로 돌고 있나 — 저장 폴더·이름·중복 실행 막기를 판마다 가른다.

판은 환경 변수 `SPACEKIJUN_EDITION` 으로 정한다. 학생용 입구(student.py)가 **다른 모듈을 불러오기 전에**
'student' 로 정해 둔다 — 저장 폴더는 모듈을 불러올 때 정해지기 때문이다. 정하지 않으면 교사용.

학생판은 저장 폴더가 따로라(`%LOCALAPPDATA%/SpacekijunStudent`) 한 PC 에 두 판이 있어도 계정·인증서·
기록이 섞이지 않는다. 교사만 쓰는 기능(나이스·업무포털·에듀파인·인증서·쿨메신저·교직원 명부)은
학생판에서 데스크 API 가 아예 받지 않는다 (desktop.py `STUDENT_ACTIONS`).
"""
from __future__ import annotations

import os

EDITION = 'student' if os.environ.get('SPACEKIJUN_EDITION', '').strip().lower() == 'student' else 'teacher'
STUDENT = EDITION == 'student'

APP_ID = 'SpacekijunStudent' if STUDENT else 'SpacekijunDesk'     # 저장 폴더·자동 실행 이름
TITLE = '스페이스기전 학생' if STUDENT else '스페이스기전 데스크'
MUTEX = 'Local\\SpacekijunStudent' if STUDENT else 'Local\\SpacekijunDeskWeb'
DATA_DIR = os.path.join(os.path.expandvars('%LOCALAPPDATA%'), APP_ID)
# 학생판 배포 판 번호 — Intune 탐지 규칙이 이 값으로 새 판을 알아본다 (deploy/intune/build.ps1).
# 학생 PC 에 새로 내보낼 때마다 올린다.
STUDENT_VERSION = '1.0.63'
# 교사판(데스크) 판 번호 — 자동 업데이트가 이것과 서버의 판을 견준다 (core/updater.py).
# 새로 내보낼 때마다 올리고 deploy/desk-update/publish.py 로 올린다.
DESK_VERSION = '1.3.91'
# 지금 도는 판의 번호 — 자동 업데이트가 서버의 판과 견준다
VERSION = STUDENT_VERSION if STUDENT else DESK_VERSION
