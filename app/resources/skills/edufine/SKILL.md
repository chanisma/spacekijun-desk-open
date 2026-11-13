---
name: edufine
description: K-에듀파인 업무포털(klef)에서 공문을 찾고(문서등록대장 검색), 본문(ODT)·첨부를 공식 권한 그대로 내려받고, 기안기(WXSClient)로 공문을 기안하고, 학교회계 지출품의를 작성해 결재요청까지 준비한다. 화면 클릭 대신 포털·기안기 자체 함수를 불러 빠르고 정확하다. 결재올림(상신)은 사용자가 내용을 확인·승인한 뒤에만 한다. "에듀파인", "업무포털", "공문 찾아줘", "공문 받아줘", "문서등록대장", "기안해줘", "결재 올려", "품의", "지출품의", "예산 잔액" 요청 시 사용. Windows + 인증서 로그인 필요.
---

# K-에듀파인 (edufine)

화면을 마우스로 누르지 않고 **포털과 기안기가 버튼에 걸어 둔 함수를 직접 부른다.** 같은 검증·권한·기록을 거치면서 결과를 값으로 돌려받는다.
(기안기는 IE 내장 창이라 클릭·키 입력이 잘 안 먹고, 알림창 하나에 전체가 막힌다 — 함수 호출이 훨씬 안정적이다.)

## 지킬 것 (반드시)
1. **상신·발송은 사용자 승인 뒤에만.** 결재올림 창의 마지막 [확인](`fncVerify`)을 누르기 전에 제목·본문·결재선·공개여부·붙임을 보여 주고 "올려도 된다"는 답을 받는다.
2. **기안 전에 한 번에 묻는다:** 결재선(검토·결재자), 대국민공개(공개/부분공개/비공개 + 사유 호수), 과제카드. 문서 내용을 보고 제안하되 추측해 넣지 않는다.
   - 개인정보(이름·연락처·IP 등)가 본문이나 붙임에 있으면 **부분공개 6호 + 해당 붙임 비공개**를 제안한다.
3. **기안 내용은 먼저 보여 주고 검토받는다.** 예전에 올린 같은 종류 문서가 있으면 `search`·`get` 으로 찾아 형식을 따른다.
4. **붙임은 자동으로 넣지 않는다.** 사용자가 기안기 [파일 추가] 로 직접 넣는다 (2026-11-10: 스크립트로 넣은 PDF 가 화면·컨트롤 등록은 정상인데 상신 뒤 결재자에게 아예 안 열렸다. 원본과 바이트가 같은 파일을 [파일 추가] 로 다시 붙이니 정상).
5. 임시저장·삭제·결재취소요청·발송 함수는 부르지 않는다. 품의 되돌리기는 사람이 한다(references/pumui.md).
6. 자격증명(인증서 암호)은 채팅으로 받지 않는다. 사용자가 `credentials.json` 에 직접 적는다.
7. 상신했으면 `draft-log.ps1 -Event 상신` 으로 기록을 남긴다.
8. 받은 공문에 든 학생·교직원 개인정보를 외부 서비스로 보내지 않는다.

## 준비 (처음 한 번 — README.md 참고)
```
cd <이 스킬 폴더>
npm install                      # playwright
npx playwright install chromium
node scripts/edufine.js setup    # %USERPROFILE%\.edufine 에 config.json · credentials.json 틀
```
- `credentials.json`: `{"id": "업무포털 아이디", "certPassword": "인증서 암호", "certMatch": "(인증서가 여럿이면 이름 일부)"}`
  - 스페이스기전 데스크(교사판)에 인증서 정보를 저장해 두었으면 `credentials.json` 없이 그것을 읽어 쓴다(이 PC·이 사용자만 풀 수 있게 암호화됨).
- `node_modules` 가 없다는 오류(`Cannot find module 'playwright'`)가 나면 이 스킬 폴더에서 `npm install` 을 다시 한다.
- `config.json` 의 `baseUrl` 기본은 전북(`https://klef.jbe.go.kr`). 다른 시·도는 그 주소로 바꾼다(전북 외는 미검증).
- **Node 22.11·22.12 는 경로에 한글이 든 `.js` 를 읽자마자 죽는다**(Segmentation fault / 종료 코드 -1073741819, 2026-10-26 실측 — 22.23.4 는 된다).
  스킬 폴더 경로에 한글이 있으면 Node 를 최신 LTS 로 올린다. 스페이스기전 데스크의 `자동화 업무` 폴더는 데스크가 Node 를 점검해 새 판을 깔아 준다.
- 기안·품의 기안기는 에듀파인 기안기(`WXSClient.exe`)가 설치돼 있어야 한다. 첫 로그인 때 브라우저에서 **인증서 프로그램 권한 허용**을 한 번 해 준다.

## 세션 (먼저 열어 둔다)
```
node scripts/edufine.js session start     # 백그라운드로 실행해 둘 것 — 로그인 후 20분마다 연장
node scripts/edufine.js session status
```
다른 명령은 열린 세션에 붙는다(없으면 새로 띄워 로그인하고 끝나면 닫는다).

## 1. 공문 찾기
```
node scripts/edufine.js ledger update                       # 문서등록대장 CSV를 캐시 이후~오늘 받기 (처음엔 --from 2026-03-01)
node scripts/edufine.js search 무선망 협조 --from 2026-07-01 # 제목 낱말 AND, 'KT|통신자산' 처럼 정규식 OR
node scripts/edufine.js search 사이버보안 --type 생산
node scripts/edufine.js find 11447 --year 2026
```
- 검색은 **제목 기준**. 결과의 `상대`=보낸 기관, 접수 공문의 실제 담당은 대장의 `결재권자`.
- 날짜·방문 일정 같은 세부는 제목에 없으니 후보를 `get` 으로 받아 본문·붙임을 읽는다.

## 2. 공문 받기
```
node scripts/edufine.js info 11447:2026-09-11
node scripts/edufine.js get 2392 8111 11447 --year 2026 --out "<폴더>"     # 본문 ODT + 첨부
```
- 공식 [PC저장]과 같은 권한 확인·접근 기록을 거친다. 권한 없는 문서는 '열람 권한 없음'으로 건너뛴다.
- 본문 ODT 텍스트: `content.xml` 에서 태그를 걷어 읽는다. HWP 첨부는 한글 COM 으로 텍스트 추출(references/download.md).

## 3. 공문 기안 (일반)
1. 사용자와 정한다: 제목·본문·붙임 + **결재선·공개여부·과제카드**(위 '지킬 것' 2).
2. `node scripts/edufine.js draft-open --form "표준서식(결재4인,협조4인)"` (서식 목록: `forms`)
3. spec 작성(UTF-8, 경로는 `/`):
```json
{ "window": "표준서식",
  "title": "10월 OO 운영 결과",
  "bodyFile": "C:/…/body.txt",
  "approvers": ["검토자", "결재권자"],
  "taskCard": "과제카드 이름 일부",
  "publication": "partial", "reasons": [6],
  "attachments": [ { "path": "C:/…/붙임.pdf", "open": false } ] }
```
4. `powershell -ExecutionPolicy Bypass -File scripts/draft.ps1 -Spec spec.json`
   → 제목·본문·결재선·과제카드·공개를 넣고 `fncValidateComn`/`fncValidate` 로 검증, 기록(`작성`)을 남긴다. **상신하지 않는다.**
   → 붙임은 넣지 않고 `직접 넣을 것: <경로>` 로 안내만 한다. 사용자가 [파일 추가] 로 넣은 뒤 `draft.ps1 -Spec spec.json -Only attach` 로
     파일별 공개여부를 맞추고 빠진 붙임이 없는지 확인한다(`붙임 N개 / 컨트롤 N개`).
5. 화면에 들어간 값을 그대로 읽어(`ie-dom.ps1`) 사용자에게 **기안문과 설정 전체를 보여 주고 검토**받는다.
6. 승인하면 결재올림: `ie-dom.ps1 -Title 표준서식 -Js 'setTimeout(function(){fncSanctn();},10); return 1;'`
   → '내부결재로 처리됩니다' 등 메시지는 문구를 읽고 `-CloseMsg 확인` → '문서처리' 창 값 확인 → **사용자 최종 승인** →
   `ie-dom.ps1 -Title 문서처리 -Js 'setTimeout(function(){fncVerify();},10); return 1;'` → '정상적으로 처리되었습니다' 확인
7. `powershell -File scripts/draft-log.ps1 -Event 상신 -Title "<제목>" -Note "<결과 문구>"`

- 같은 제목의 기안기 창이 여럿(로그인 오류 창 등)이면 `ie-dom.ps1 -UrlLike '*DoccrdWritng*'` 로 작성 화면을 고른다(draft.ps1 는 자동).

세부 함수·함정: references/drafter.md

## 4. 지출품의
1. `node scripts/edufine.js budgets` 로 쓸 수 있는 예산(세부사업/세부항목/산출내역/잔액)을 보여 주고 고른다.
2. spec: `{ "budget": {"detlBsns":"세부사업","detlIem":"세부항목","cpt":"산출내역 일부"}, "title":"…", "summary":"1. 관련: …\n2. … 아래와 같이 구입하고자 합니다.", "items":[{"name":"품명","spec":"규격","qty":1,"price":10000}] }`
3. `pumui spec.json --step fill` (화면만) → 확인 → `--step save` (품의저장, 품의번호) → `--step request` (결재요청 → 기안기 열림)
4. 기안기에서 `draft.ps1 -Spec <window: "기안기", approvers, taskCard, publication>` 와 `-Only route,task,pub` 로 마무리 → 3번 기안의 5~7과 같다.
- `save`·`request` 는 서버에 품의를 만든다. 사용자에게 먼저 확인한다. 되돌리기는 사람이 한다(references/pumui.md).
5. **SPACEKIJUN 구매 신청에서 온 품의면 그 품의 차수에 에듀파인 품의를 적어 둔다** (2026-11-12): `save` 가 준 품의번호(`sclCnsulNo`, 예 `2026P100000419201392` — 문서등록대장 문서번호 아님)와 품의 제목(spec 의 `title` 그대로)을
   SPACEKIJUN MCP `update_purchase_order_batch(batch_id, edufine_title, edufine_no)` 로 남긴다(`batch_id` = `list_purchase_orders`). 데스크의 에듀파인 «바로보기»가 품의목록에서 이것으로 차수를 찾아 «구매 신청» 표시와 바로 열기를 붙인다. 적지 못했으면 품의목록의 «+ 연결»로 사람이 한 번 고른다.

## 5. 기안 기록
`draft.ps1` 이 끝에서 자동으로 `작성` 기록을 남긴다. 위치: `%USERPROFILE%\.edufine\logs\기안로그\`
(`기안로그.csv` 엑셀용, `문서\<날짜>_<제목>.md` 문서별 본문·설정·사건). `draft-log.ps1 -Show` 로 목록.

## 그 밖
- 사용자 작업: `node scripts/edufine.js run my-task.js` — `module.exports = async ({ ctx, page, log }) => { … }` (page = 포털 탭)
- 업무화면은 Nexacro 셸 안의 **HTML/JSP** 라 `scripts/lib/menus.json` 의 경로로 직접 열린다(`lib/portal.js openScreen`).
- 세션이 끊기는 흔한 원인: 열어 둔 창에 Nexacro 모달(공지 팝업 등)이 남아 [연장] 클릭이 막힘 → 팝업은 쓰고 닫는다.
