# 공문 찾기·받기 — 백엔드 지도

## 문서등록대장 캐시
- 화면: 문서등록대장(`bms/.../문서등록대장`, menus.json). 조회는 AJAX — `aform` 값(`basicReportDe`/`reportDe`, `basicReportDe3`/`reportDe3`) 세팅 후 `fncRealSearch()`.
- CSV: `fncIseIseXlsDwl('a')` → 현재 조회 조건 **전체**가 EUC-KR CSV 로 내려온다(페이지 단위 아님).
- 주요 열: 문서번호(`기관명-번호`), 결재유형(생산/접수), 제목, 기안(접수)자, 결재권자, 등록일자, 처리상태, 공개구분, 공개제한근거, 수신(발신)자.
  - 접수 공문의 `기안(접수)자`는 문서 접수 담당 한 사람이다. **실제 처리 담당은 `결재권자`** 칸.
- **문서번호는 해마다 1부터 다시 시작**한다 → 번호만으로는 모호하다. `번호:YYYY-MM-DD` 또는 `--year` 로 고른다.

## 받기 (`get`) — 공식 [PC저장]과 같은 길
1. 문서등록대장을 그 날짜로 조회 → 목록 체크박스(`input[name=docinfo]`, value 의 17번째 값이 문서번호) 체크
2. `doCallFileManagerExtra` 를 태우고 `connectWXSClient.do` POST 를 가로채 **APPRIDLIST(열람 허용 목록)·USERID·APPRDEPTID** 를 얻는다. 목록에 없으면 열람 권한 없음.
3. 같은 요청의 `path`(다건 저장 페이지 `retrieveDocListBdtStre.do`)를 열면 `Capi`, `mk_apprid`, `createAccesLogHist` 가 있는 문맥이 생긴다.
4. `Capi.getApprovalInfo(id)` → 제목·문서번호·`fileNames[]`·`fileObjectIDs[]`
5. 본문 `retrieveDocFile.do?UID&DID&apprID=mk_apprid(id,'01')&fileType=attach` (ODT), 첨부는 apprID 에 fileObjectID.
   제외: fileObjectID 끝 `060`(이관용 PDF 변환본), 파일명 `HOX_file`.
6. 받을 때마다 `createAccesLogHist(id, fid, 'hwpsave'|'attsave')` — 접근 기록을 공식 경로와 똑같이 남긴다.

## 알아 둘 것
- 본문은 **ODT**. 윈도에서 `.odt` 가 Word 에 연결돼 있으면 머리·결재란·표가 깨져 보인다 → 한컴 ODTEditor(한글이 .odt 를 넘기는 프로그램)로 연다. 파일이 깨진 게 아니다.
- `.ozd`(지출품의서 등)는 OZ 뷰어 전용 암호화 파일이라 텍스트로 못 읽는다.
- HWP 본문 텍스트가 필요하면 한글 COM: `HWPFrame.HwpObject` → `Open(path,'HWP','forceopen:true')` → `GetTextFile('UNICODE','')`.
