# NEIS(4세대) 내부 구조와 함정 — 실측 정리 (2026-08~10)

## 프레임워크
- 화면 프레임워크는 **Cleopatra**(`cl-*` 클래스). 런타임: `cpr.core.Platform.INSTANCE.getAllRunningAppInstances()`.
  - 업무 화면 앱 id 는 `edu/…`(예: `edu/sw/his/srg/aa/his_srgaa04_m01$1`), `app/com/main` 은 포털, `udc/…` 는 공통 부품.
  - `…_m00` 이 화면 위 탭 껍데기이고 실제 화면은 `…_m01` 인 경우가 있다(과목별출결관리). 반대로 `…_m00` 이 본체인 화면도 있다.
  - 컨트롤·데이터: `app.lookup('이름')`, 전체 `app.getAllDataControls()`, 화면 컨트롤 `app.getContainer().getAllRecursiveChildren()`.
  - DataSet: `getRowCount()`, `getRowDataRanged()`(행 객체 배열), `getValue(i, 열)`, `clearData()`. DataMap: `getValue(열)`.
- 지금 화면 DOM 루트 = 보이는 것 중 **가장 바깥** `.cl-mdifolder .cl-tabfolder-body .cl-embeddedapp`(안쪽 것은 제목줄 같은 부품).
- 로딩 `.ers_progress_content`, 왼쪽 패널 덮개 `.cl-overlay`, 모달 `.cl-dialog`.
- 포털 앱 `app/com/main/Index` 의 `dsAllMenu` 에 계정 메뉴 전체(1,300여 행: MENU_NM·CALL_PAGE·PGM_ID…)가 있다.

## 화면 열기
- **메뉴 검색**(왼쪽 아이콘 줄 `[class*=cl-button][class*=search]`)이 가장 튼튼하다. 결과 행 `.menu-find-grp` 에 전체 경로(`탭 > … > 화면`).
  - 아이콘은 **토글** — 이미 열려 있으면 누르지 않는다. 검색칸은 보이는 입력칸 중 **가장 왼쪽**(화면에도 입력칸이 있다).
  - 같은 화면이 여러 탭에 있다(교과담임·부서장…). 경로로 고른다.
- **기본 메뉴**(복무·인사·급여 등 개인 메뉴)는 메뉴 검색에 안 나온다 → 아이콘 `mymenu`(기본메뉴 및 승인사항)로 패널을 열고 `.cl-sidenavigation-item div.cl-text`("복무 0단계 메뉴항목" → "일일근무상황조회 1단계").
- 메가메뉴로 갈 때: "다른 탭 → 대상 탭" 순서(활성 탭 재클릭 무시), 항목 텍스트 "이름 N단계( 메뉴항목)", 펼침이 가끔 실패하니 다음 단계가 보일 때까지 재클릭. 펼침 상태는 프로세스 사이에 유지되지 않는다.
- 로그인 직후 공지 팝업이 여러 겹 — 닫기는 `div.cl-text` 일 때가 있고 **맨 위(last)부터**.
- 화면 탭이 **20개**면 메뉴를 눌러도 조용히 그 자리 — 결과가 엉뚱한 화면 것으로 채워진다. '탭 아이템 전체 닫기'(`.btn-close-mdi[title*="전체 닫기"]`).
- 진입만 해도 알림(예: "과목은(는) 필수 입력입니다")이 뜨는 화면이 있다 → 취소/닫기/확인 순으로 안전하게 치운다.
- 2차 인증(세특 등): `.cl-dialog` 에 "2차 인증/OTP/인증번호" — 사람이 한다. 다른 화면으로 옮길 땐 닫아야 뒤 클릭이 막히지 않는다.

## 입력
- 일자 콤보(`2026.09.11.(금)`): **점까지 한 글자씩 타이핑 + Enter** 만 먹는다. `fill` 은 Tab 때 되돌아가고, 점 없이 치면 조회 때 되돌아간다. 넣은 뒤 다시 읽어 확인.
  - 마스크 일자(`년도-월-일`, 일일근무상황)는 타이핑이 안 먹는다 → `app.lookup('dtiWorkYmd').value = 'yyyymmdd'`.
- 라디오·그리드 행·상단 탭은 **실제 마우스 클릭**이어야 한다(`dispatchEvent`·`selectRows` 는 표시만 바뀐다). 클릭 뒤 연결된 콤보 값으로 바뀌었는지 검증.
- 콤보는 컨트롤 `value` 를 넣고 [조회]를 실제 클릭하면 반영되는 경우가 많다(과목별출결 `cmbAtteSbjt`). 반영 여부를 데이터로 확인.
- 드롭다운·트리는 가상 스크롤 — 목록은 DOM 보다 DataSet 에서 읽는다. 꼭 DOM 이면 `.cl-viewport` 에 WheelEvent.
- 콤보 `aria-label` 은 "학년도, 2026" 처럼 현재값이 붙는다 → 접두 일치.

## 읽기·내려받기
- 그리드 = DataSet. 조회 전에 `clearData()`(이전 결과가 남는다), 읽은 뒤 검색조건(dm…)과 대조.
- 리포트 화면은 `cl-embeddedpage` iframe 의 **Crownix 뷰어** — 툴바 `#crownix-toolbar-save button` → `#crownix-toolbar-xls_data button`(실제 xlsx).
  렌더 끝(툴바 `crownix-toolbar-item-disable` 사라짐)까지 기다리지 않으면 클릭이 조용히 무시된다. 매번 `waitForEvent('download')` 를 먼저 건다.
- [조회]에 "개인정보 다운로드 사유" 창이 뜨는 화면이 있다 — 사람이 판단한다.

## 세션
- 약 50분 뒤 자동 로그아웃(`executeNeisLogout.do`). `neis.js session start` 가 다시 로그인한다.
- `page.reload()` 금지 — 언로드 때 세션 파기.
- 같은 브라우저 프로필은 한 브라우저만 — 남은 chrome.exe 가 프로필을 잡고 있으면 실행 실패.

## 이름 차이
- 설명서 «지필평가» = 전북 메뉴 «정기시험». 탭 이름(`부서장(나이스부)` 등)은 학교·업무분장마다 다르다.
