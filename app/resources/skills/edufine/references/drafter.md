# 기안기(WXSClient) 함수 지도 — draft.ps1 / ie-dom.ps1

기안기는 IE 내장 창이라 **화면 클릭·키 입력이 거의 안 먹는다**(알림창이 뜨면 뒤 입력이 전부 막힌다).
`ie-dom.ps1` 이 창의 `Internet Explorer_Server` 에 `WM_HTML_GETOBJECT` 로 붙어 페이지 함수를 그대로 부른다.
반드시 **Windows PowerShell 5.1(`powershell.exe`)** 로 실행하고, ps1 은 **UTF-8 BOM** 이어야 한글이 안 깨진다.

| 항목 | 방법 |
|---|---|
| 서식 열기 | 공용서식 `fncFormDraft(formId, 분류, 이름)` → `wxsclient://` 가로채 `WXSClient.exe` 실행 (`edufine.js draft-open --form 이름`) |
| 제목 | `#Sj` value → `input_changed(el)` |
| 본문 | `IMPL_PutFieldText('editor1','본문', text)` (줄바꿈 `\r\n`), 확인 `IMPL_GetFieldText` |
| 결재선 | `fncReportCours()` → 창 '결재경로설정': `#userNm` 에 이름 → `fncRetrieveReprsntInsttOrgnztUserList()` → `frames[1]` 의 `partSelRadio`(value=이름) 행 click → `fncAdd()` → 끝나면 `fncVerify()` |
| 과제카드 | `fncChooseTkcrd()` → Nexacro 창: `nexacro.getApplication().mainframe.frame.form.dsAList`(tkcrdNm) → `fnSelectUnitTkcrd(row)` → `Tab00_Tabpage1_divAuth_btnAuthC01_onclick()` |
| 대국민공개 | `#othbcLmtt1/2/3`(공개/부분공개/비공개) click, 사유 `#othbcAt1~8` click. 공개면 직원열람제한 `#readngLmtt0`(설정안함)이어야 검증 통과 |
| 붙임 | **자동으로 넣지 않는다 — 사람이 [파일 추가](`Attach.onadd` → 컨트롤 `Attach()` 대화상자)로 넣는다.** `addFiles([new HsFile(경로,…)], undefined, true)`(= 컨트롤 `AddItemByGroup`)는 서버에 이미 있는 파일(FID/TRID 주소)을 다시 붙이는 통로라, PC 파일을 넣으면 등록은 정상으로 보여도 상신 뒤 안 열리는 파일이 된다(2026-11-10: 스크립트로 넣은 PDF 가 화면·컨트롤 등록은 정상인데 상신 뒤 결재자에게 아예 안 열렸다. 원본과 바이트가 같은 파일을 [파일 추가] 로 다시 붙이니 정상). 넣은 목록 확인은 `Attach.fileBox._files`·`_hsAttach.getFilesCount()`. 파일당 `doccfg.inDocMaxFileSize`MB(보통 10MB) |
| 파일 공개 | 파일마다 라디오 `modiAttachOthbcSe*` → `open` / `not_open` |
| 검증 | `fncValidateComn()` → `fncValidate()` (값만 본다). 수신자 없으면 confirm '내부결재로 처리' |
| 결재올림 | `fncSanctn()` → confirm(내부결재) → 창 '문서처리 | 업무관리시스템'. **그 창의 [확인] = `fncVerify()` 가 실제 상신** |
| 금지 | 임시저장 `fncSaveTmpr`/`fncSaveCnsltTmp`, 결재올림 창 `fncVerify` 는 사용자 승인 없이 부르지 않는다 |

## 함정
- 웹 페이지 메시지(alert/confirm)가 떠 있는 동안 execScript 가 멈춘다 → 모달을 여는 함수는 `setTimeout(fn,10)` 으로 부르고, 메시지는 문구를 읽은 뒤 `ie-dom.ps1 -CloseMsg 확인|취소`(UIA Invoke)로 닫는다.
- 기안기를 새로 열면 늦게 '자동저장문서를 읽어오시겠습니까?' 가 뜬다 → 보통 **취소**(draft.ps1 이 처리).
- 창 닫히는 동작 직후 결과 읽기의 `E_ACCESSDENIED` 는 정상(창이 이미 닫힘).
- 작성 중 창은 `taskkill /IM WXSClient.exe` 로 닫으면 서버에 아무것도 남지 않는다(자동저장은 로컬).
- 기안기를 막 열면 `wxsLogin.do` 를 거쳐 작성 화면(`retrieveDoccrdWritng.do`)이 뜬다 — 준비될 때까지 기다린다(draft.ps1 가 `Sj`·`IMPL_PutFieldText`·`domHox1` 확인).
- 같은 제목 창이 여럿이면 `-UrlLike '*DoccrdWritng*'` 로 고른다. '사용자 정보를 불러오지 못하였습니다' 창은 닫는다.
- 기안기 페이지의 Prototype.js 가 `Array.prototype.toJSON` 을 덧씌워 `JSON.stringify(배열)` 이 이중 인코딩된다 → 직렬화할 때 잠시 떼어 낸다.
- 화면이 비어 보이는 스크린샷은 다시 그리기 지연일 때가 많다 — 값은 DOM 으로 확인한다.
