---
name: neis
description: 나이스(NEIS 4세대)를 조회 중심으로 다룬다 — "어느 화면에서 하나"·화면 사용법·"왜 비어 보이나"를 지식으로 답하고(로그인 불필요), 인증서로 로그인해 화면을 찾아 열고 글·표(DataSet)를 읽는다. 교사용: 과목별출결 수집·통계, 일일근무상황(출장·연가). 부장용: 학생부 항목별 일괄 XLSX, 학생별 시간표, 문항정보표, 정기시험 학생답. 기본은 저장·마감·삭제 같은 자료를 바꾸는 버튼을 누르지 않고, 검증된 화면(동아리 이수시간기준등록·누가기록 일괄등록·수정)만 사용자 승인 뒤 저장한다(references/write-*.md). "나이스", "NEIS", "어느 메뉴", "출결 통계", "과목별출결", "일일근무상황", "누가 출장", "생기부 다운로드", "학생부 일괄", "시간표 받아줘", "문항정보표", "학생 답안", "동아리 누가기록 입력", "동아리 봉사활동 입력" 요청 시 사용. Windows + 교육행정 인증서 필요.
---

# 나이스 (neis) — 조회 (+ 검증된 화면 쓰기)

화면을 사람처럼 누르지 않고, **메뉴 검색으로 화면을 열고 화면 뒤 데이터(DataSet)를 읽는다.** 쓰기는 기본으로 하지 않고, 아래 «쓰기» 절의 검증된 화면만 한다.

## 지킬 것 (반드시)
1. **기본은 조회 전용.** `저장·삭제·마감·확정·반영·등록·적용·승인·취소·…` 처럼 자료를 바꿀 수 있는 버튼은 누르지 않는다.
   `click` 은 이름으로 성격을 판정해 쓰기 버튼을 거절한다(모르는 이름도 쓰기로 본다). 되묻는 창은 **취소**로 닫는다.
   예외는 «쓰기» 절의 검증된 화면뿐 — 저장할 내용(부서·날짜·학생 수·시간·문구)을 사용자에게 보여 **승인받은 뒤**, 한 건 먼저 저장 → 다시 조회로 확인 → 나머지.
2. **2차 인증(세특 등)은 사람이 한다.** 창이 뜨면 멈추고 알린다.
3. **학생·교직원 개인정보.** 결과 파일(`%USERPROFILE%\.neis\out`)에 이름·학번·출결 사유·건강(병가) 정보가 있다.
   - 보고는 **건수·통계 중심**, 개인 명단은 사용자가 요청할 때만. 외부 서비스로 보내지 않는다. 쓰고 나면 지우라고 안내한다.
   - 스크린샷(`shot`)에 학생 정보가 보이면 쓰고 나서 지운다.
4. 자격증명(인증서 암호)은 채팅으로 받지 않는다 — 사용자가 `credentials.json` 에 직접 적는다(스페이스기전 데스크를 쓰면 없어도 데스크에 저장한 인증서 정보를 쓴다).
5. 화면 이름·메뉴는 학교의 **업무분장(상단 탭)** 과 학교급에 따라 다르다. `tabs`·`menu` 로 이 계정에 있는지 먼저 확인하고, 없으면 권한 문제라고 알린다.

## 준비 (처음 한 번 — README.md)
```
npm install && npx playwright install chromium
node scripts/neis.js setup [--from-edufine]     # %USERPROFILE%\.neis, edufine 스킬을 쓰면 인증서 암호를 가져온다
```
- `config.json` 의 `baseUrl` 기본은 전북(`https://jbe.neis.go.kr`). 다른 시·도는 `https://<시도>.neis.go.kr` 로(전북 외 미검증).
- **스킬 폴더 경로에 한글이 없어야 한다**(일부 Node 버전이 한글 경로에서 모듈을 불러오다 죽는다).
- 첫 로그인 때 브라우저에서 인증서 프로그램 권한 허용을 한 번.

## 세션
```
node scripts/neis.js session start      # 백그라운드로 — 5분마다 확인, 약 50분 로그아웃되면 다시 로그인
node scripts/neis.js session status     # 로그인 사용자·상단 탭
```
⚠ `page.reload()` 금지(NEIS 가 세션을 파기해 로그아웃). 붙은 브라우저를 `close()` 하지 않는다.

## 1. 지식 — 로그인 없이 바로 답한다
```
node scripts/neis.js find 세특 입력            # 하고 싶은 말 → 화면·경로·역할(교과/학급/동아리담임·업무분장)·용도
node scripts/neis.js find 출결 --role 학급
node scripts/neis.js guide 과목별출결관리       # 먼저 할 일·순서·주의·다음 할 일·FAQ
node scripts/neis.js rules 마감                 # «A 를 안 하면 B 가 비어 보인다» 화면 사이 규칙
node scripts/neis.js workflow 학기말            # 시기별(학년초·학기초·학기중·학기말·학년말) 업무
```
- 카탈로그 1,384 화면(고등학교 교무 중심), 사용법 안내 215, 규칙 36. 2026-10 기준 — 개편되면 이름이 다를 수 있다.
- 질문이 "왜 안 보여요/비어 있어요"면 `rules` 와 그 화면 `guide` 의 «먼저 할 일»부터 본다.

## 2. 화면 열고 읽기
```
node scripts/neis.js tabs                        # 이 계정 상단 탭(업무분장)
node scripts/neis.js menu 교사별시간표조회        # 메뉴 검색 결과(경로)
node scripts/neis.js open 교사별시간표조회 --path 교과담임   # 같은 이름이 여러 탭에 있으면 --path 로
node scripts/neis.js buttons                      # 버튼과 성격(조회/출력/이동/쓰기)
node scripts/neis.js date 2026.10.26.             # 일자 칸(한 글자씩 타이핑 + Enter 로 넣고 다시 읽어 확인)
node scripts/neis.js click 조회                   # 조회·출력 계열만
node scripts/neis.js text                         # 화면 글
node scripts/neis.js data [--only dsX] [--rows 5] [--cols a,b]   # 화면 뒤 DataSet(그리드는 가상 스크롤이라 이쪽이 정확)
```
- 기본 메뉴(복무 등 개인 메뉴)는 메뉴 검색에 안 나온다 → 사이드바로 연다(`lib/nav.js openSidebar`, 일일근무상황은 자동).
- 화면 탭이 20개 차면 조용히 안 열린다 → 14개에서 자동으로 전체 닫기(`close-screens` 로도).

## 3. 교사용
```
node scripts/neis.js attendance --list                                   # 내 과목(반)
node scripts/neis.js attendance --subject "정보과제연구" --until 20261023  # 수업일별 출결 수집·종류별 통계
node scripts/neis.js absence --date 2026-10-26                           # 그날 출장·연가·외출·조퇴 … (근무상황별 건수)
```
- 과목별출결: `결과(/)` = 교과 교사가 표시한 결과, `출결정보` = 일일출결 사유. 둘을 따로 센다. 미래 수업일은 제외. 학생 이름은 저장하지 않는다.
- 일일근무상황: 신청자가 목적지·기간을 비공개로 하면 빈칸이다. 결과 파일에 이름·사유가 있다.

## 4. 부장용 일괄 (해당 탭 권한 필요 — 학교마다 탭 이름이 달라 메뉴 검색으로 자동 판단, `--tab` 으로 지정 가능)
```
node scripts/neis.js records --grades 1 --classes 1,2 --sections sewteuk,creative   # 학생부 항목별 XLSX
node scripts/neis.js records-merge "<폴더>"                                         # 세특·창체·교과 등 → 정리 엑셀(반·학년·학기·번호·성명·과목·내용)
node scripts/neis.js timetable --grades 1                                          # 반별 시간표 XLSX + timetable.csv
node scripts/neis.js questions --exams "1차 정기시험,2차 정기시험" --grades 1,2,3    # 문항정보표 CSV
node scripts/neis.js answers --exams "1차 정기시험" --grades 3 --long               # 학생별 답안 CSV(+문항별)
```
- 항목 키: history 학년반이력 · hakjeok 학적 · attend 출결 · volunteer 봉사 · creative 창체 · subject 교과 · sewteuk 세특 · reading 독서 · behavior 행특
- 오래 걸린다(학생부 한 반 9항목 20~45초, 시간표 한 반 20~30초, 학생답 과목당 약 1분). 백그라운드로 돌리고 범위를 나눈다.
- 검증: 반×항목 수와 파일 수 대조, 같은 크기 파일이 여럿이면 빈 리포트 의심(원래 자료가 없을 수도). 학생답은 `답안`·`정오` 길이 일치, 한 학생이 두 강의실에 나오면 오귀속.
- 세부: references/bulk.md

## 쓰기 — 검증된 화면만 (사용자 승인 뒤)
`scripts/write/` 스크립트가 저장 버튼을 누른다(`neis.js click` 은 여전히 쓰기 버튼을 거절한다). 화면마다 방법·함정은 references 에:
- 동아리활동(동아리담임) — 이수시간기준등록, 누가기록 일괄등록(최대·직접 시간·학생 골라 넣기·봉사활동실적), 이미 넣은 기록 고치기: **references/write-club.md**
```
node scripts/write/nx.js scripts/write/bulk.js     # env: DEPT DAY TEXT [HOURS] [ONLY|EXCLUDE] [EXPECT] [VOL=1] — SAVE 없이 먼저 미리보기
```
- 저장 전 변경이 의도한 것뿐인지 `data` 로, 저장 뒤 다시 조회로 확인한다. 결시(결과) 학생 칸은 나이스가 잠근다 — 출결은 바꾸지 않고 사람에게 넘긴다.
- 새 화면 쓰기를 검증하면 `references/write-<화면>.md` 와 `scripts/write/` 에 더하고 이 목록에 적는다.

## 그 밖
- 화면별 함정·내부 구조: references/internals.md
- 원하는 작업이 명령에 없으면: `menu` → `open` → `date`/`click 조회` → `data`/`text` 조합으로 읽는다. 쓰기가 필요하면(«쓰기» 절에 없는 화면) 사람에게 넘긴다.
