# 지출품의 — tasks/pumui.js

품의등록(`A00FAA0104001001`, 폼 `FADMANGEXCN001M01`, Nexacro)도 폼 함수·데이터셋을 직접 다룬다.

| 단계 | 함수·데이터 |
|---|---|
| 예산 목록 | `divAuth1_btnBgtDtl_onclick` → 팝업 `nexacro.getPopupFrames()['FADMANGEXCN004P01'].form.dsMain` (`sclDetlBsnsNm` 세부사업, `detlIemNm` 세부항목, `cptBasisCn` 산출내역, `bgtBlce` 잔액). `edufine.js budgets` |
| 예산선택 | 해당 행 `choise='1'` → `btnCnfirm_onclick` (메시지는 **확인 전에** 읽는다 — 확인하면 팝업이 닫힘) |
| 제목·개요 | `dsCnsulRegist.sj` / `cnsulPurpsCn` + `divMain.form.edtCnsulSj` / `txtareaCnsulSumrCn` |
| 품목 | `divAuth2_btnRowAdit_onclick` → `dsPrdlstDtlList`(`prdlstCn` 품명, `stndrd` 규격, `qty`, `expectUntpc`) → `fnExpectAmtCreat()` |
| 저장 | `fnSaveValidationChk()` true 후 `fnSaveExpdCnsulWrtgList()` → 상태 **101 품의저장**, 품의번호 `sclCnsulNo` |
| 결재요청 | `fn_inputChk='Y'` 후 `fnSanctnRequstChk()` → `saveSanctnRequstPrcs.do` → 상태 **102** → `wxsclient://` → 기안기 |
| 기안기 | 제목·본문(개요)·**지출품의서.ozd** 가 이미 들어 있음 → `draft.ps1 -Only route,task,pub` |

- 물품 품의는 개인정보가 없으면 보통 공개 → 직원열람제한 '설정안함'(draft.ps1 이 자동).
- **삭제·결재취소요청은 구현하지 않는다.** `[결재취소요청]`(`fnSanctnCanclRequst`)은 되돌리기가 아니라 '[결재취소] …' 결재문서를 새로 올린다.
  결재요청(102)을 되돌릴 때는 사람이: **업무관리 › 문서관리 › 재정문서 에서 반송 → 품의목록에서 품의 삭제.**
- `page.evaluate` 에 JS 를 템플릿 문자열로 넣으면 `\n`·따옴표가 깨지기 쉽다 → 함수 + 인자로 넘기고 폼은 `eval(FF(name))` 로 잡는다.
