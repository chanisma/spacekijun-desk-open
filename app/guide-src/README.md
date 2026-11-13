# 데스크 사용 방법

데스크 상단 `사용 방법` 버튼에서 여는 로컬 React 안내입니다. 네트워크/API 요청 없이 예시 화면만 재생합니다.

## 구성

| 순서 | 창 × 행동 × 확인 |
|---|---|
| 1 업무 홈 | 데스크 × 스페이스기전 열기 × 프로그램 내부 웹 창 |
| 2 계정 연결 | 연결 및 설정 × 구글 로그인·계정 선택 × 자동 감시 중 |
| 3 인증서 설정 | 인증서 자동 로그인 × 이름 입력·저장 × 하나의 일치 인증서 선택 |
| 4 바로가기 | 업무 홈 × 시스템 선택 × 로그인된 업무 화면 |
| 5 알림·답장 | 쪽지 알림 옵션 × 요약·본문 선택 × SPACEKIJUN 새 알림 |
| 6 쪽지함 | 쪽지 목록 × 항목 선택 × 아래쪽 전문 |
| 7 교직원 명부 | 조직도 새로 읽기 × 검색·별칭 저장 × 실명 연결 |
| 8 개인기기 | 사용자 아이콘 × 프로필·개인기기 등록 × 로그인 유지 안내 |
| 9 자동 실행 | Windows 자동 실행 × 옵션 켜기 × 다음 Windows 로그인 시 트레이 시작 |
| 10 종료·점검 | 창 닫기 × 트레이 메뉴·종료 × 감시 중지 |

## 실사 확인

2026-09-10 실제 `https://spacekijun.lovable.app/`에서 오른쪽 위 사용자 아이콘 → 프로필 → `개인기기 및 자동 로그인` → `이 브라우저를 개인기기로 등록`을 확인했습니다. 별도의 임시 브라우저에서 등록 성공 문구와 스위치 상태를 확인했으며 평소 사용하는 브라우저의 등록 상태는 바꾸지 않았습니다. 실사 카드 캡처는 `../profile-reference.png`입니다. 데스크는 `../web/index.html`, `../desktop.py`, `../core/portal.py`, `../core/watcher.py`와 기존 UI 캡처를 기준으로 대조했습니다.

## 참고·원본

- 사용자 지정 스킬: `C:/repository/presentation/.claude/skills/software-walkthrough-builder/SKILL.md`
- 씬 문법: 해당 스킬의 `references/walkthrough-grammar.md`, presentation `.claude/rules/scene-grammar.md`
- 안내 배치: SPACEKIJUN `src/components/walkthrough/WalkthroughDialog.tsx` — 왼쪽 시연, 오른쪽 설명, 사용자 주도 단계 이동, 다시 재생.
- `runtime/`: SPACEKIJUN `src/lib/walkthrough/`에서 가져온 React 역학. 그 원본은 presentation `src/scene/`·`src/walkthrough/`이며 출처 주석을 유지했습니다. 발표 엔진 대신 SPACEKIJUN의 앱 안내용 시계를 사용합니다.

## 빌드·검증

`npm run check`, `npm run build:guide`, `node scripts/test-guide.js` 순으로 실행합니다. 마지막 명령은 스킬의 국면별 캡처 절차를 앱 안내에 맞춰 적용합니다. 10개 단계 × 시작·중간·완료 30장 캡처는 `%TEMP%/desk-guide-review`에 저장됩니다. `?step=7&t=7.3`처럼 단계(0부터)와 고정 시각으로 재검수할 수 있습니다.

생성된 `app/web/guide`는 PyInstaller 실행 파일에 포함됩니다. 안내 내용을 바꾸면 안내 번들을 다시 빌드한 뒤 실행 파일을 빌드하세요.
