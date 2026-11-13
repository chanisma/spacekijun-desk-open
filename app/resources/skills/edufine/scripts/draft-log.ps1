# draft-log.ps1 — 에듀파인 기안 기록(로그)을 남긴다.
#   기록 위치: <데이터폴더>\logs\기안로그\   (데이터폴더 = $env:EDUFINE_HOME 또는 %USERPROFILE%\.edufine)
#     기안로그.jsonl   한 줄 = 한 사건(작성·상신·취소·메모). 기계가 읽는 원본
#     기안로그.csv     같은 내용 요약(UTF-8 BOM, 엑셀에서 바로 열림)
#     문서\<날짜>_<제목>.md   문서별 상세(본문 전문·설정·사건 이력)
#
#   작성: 열린 기안기 화면을 그대로 읽어 기록 (draft.ps1 가 끝에 자동 호출)
#     powershell -File draft-log.ps1 -Event 작성 -Window 표준서식 [-Check "공통=true 기안=true"] [-Note …]
#   상신·취소·메모: 같은 제목의 마지막 '작성' 기록을 이어받아 사건만 덧붙인다(기안기가 닫혀 있어도 됨)
#     powershell -File draft-log.ps1 -Event 상신 -Title "10월 OO 운영 결과" -Note "정상적으로 처리되었습니다"
#   목록 보기:  powershell -File draft-log.ps1 -Show [-Last 20]
param(
  [ValidateSet('작성','상신','취소','메모')][string]$Event = '작성',
  [string]$Window = '표준서식',
  [string]$Title = '',
  [string]$Check = '',
  [string]$Note = '',
  [string]$Kind = '',          # 일반기안 | 지출품의 … (비우면 화면으로 추정)
  [string]$RecordFile = '',    # 작성: 화면 대신 이 JSON(같은 필드) 으로 기록 — 이미 닫힌 기안을 뒤늦게 남길 때
  [string]$At = '',            # 기록 시각 지정(yyyy-MM-dd HH:mm:ss) — 뒤늦게 남길 때
  [switch]$Show,
  [int]$Last = 20
)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$IeDom = Join-Path $here 'ie-dom.ps1'
$home0 = if ($env:EDUFINE_HOME) { $env:EDUFINE_HOME } else { Join-Path $env:USERPROFILE '.edufine' }
$dir   = Join-Path $home0 'logs\기안로그'
$docs  = Join-Path $dir '문서'
New-Item -ItemType Directory -Force -Path $docs | Out-Null
$jsonl = Join-Path $dir '기안로그.jsonl'
$csv   = Join-Path $dir '기안로그.csv'
$utf8  = New-Object Text.UTF8Encoding($false)

function Read-All { if (Test-Path -LiteralPath $jsonl) { Get-Content -LiteralPath $jsonl -Encoding utf8 | Where-Object { $_ } | ForEach-Object { $_ | ConvertFrom-Json } } }

if ($Show) {
  Read-All | Select-Object -Last $Last | ForEach-Object { "{0}  {1,-3} {2}  [{3}] {4}" -f $_.시각, $_.사건, $_.제목, $_.공개, ($_.결재선 -join '→') }
  return
}

$now = if ($At) { [datetime]$At } else { Get-Date }
if ($Event -eq '작성' -and $RecordFile) {
  $r0 = Get-Content -LiteralPath $RecordFile -Raw -Encoding utf8 | ConvertFrom-Json
  $rec = [ordered]@{}
  foreach ($p in $r0.PSObject.Properties) { $rec[$p.Name] = $p.Value }
  $rec.시각 = $now.ToString('yyyy-MM-dd HH:mm:ss'); $rec.사건 = '작성'
  if ($Check) { $rec.검증 = $Check }; if ($Note) { $rec.메모 = $Note }
} elseif ($Event -eq '작성') {
  $js = @'
var o={}; o.url=document.URL.split('?')[0]; var q=document.URL;
o.formId=(q.match(/FORMID=([^&]+)/)||[])[1]||''; o.apprId=(q.match(/APPRID=([^&]+)/)||[])[1]||'';
o.title=document.getElementById('Sj').value;
try{ o.body=String(IMPL_GetFieldText('editor1','본문')); }catch(e){ o.body=''; }
var e=domHox1.selectNodes('/hox/approvalFlow/participant'); o.line=[];
for(var i=0;i<e.length;i++) o.line.push(get_text(e[i],'name')+'('+get_text(e[i],'position')+')');
o.task=((document.getElementById('taskInfo')||{}).innerText||'').replace(/^\s+|\s+$/g,'');
o.pub={pubtype_open:'공개',pubtype_partial:'부분공개',pubtype_not:'비공개'}[get_text(domHox1,_PUBLICATION)]||get_text(domHox1,_PUBLICATION);
o.reason=get_text(domHox1,'/hox/docInfo/publication/publicationFlag');
var r=document.getElementsByName('readngLmtt'); o.readng=''; for(var k=0;k<r.length;k++) if(r[k].checked) o.readng=r[k].value;
o.recv=get_text(domHox1,'/hox/docInfo/content/receiptInfo/displayString')||'내부결재';
var fb=Attach.fileBox, rs=document.getElementsByTagName('input'), pubs=[]; o.files=[];
for(var j=0;j<rs.length;j++) if(rs[j].type=='radio'&&/^modiAttachOthbcSe/.test(rs[j].name)&&rs[j].checked) pubs.push(rs[j].value);
for(var j=0;j<fb._files.length;j++){ var f=fb._files[j]; o.files.push({name:f.name,size:Number(f.size)||0,open:pubs[j]||''}); }
// 기안기 페이지의 Prototype.js 가 Array.prototype.toJSON 을 덧씌워 배열이 이중 인코딩된다 → 잠시 떼고 직렬화
var __tj=Array.prototype.toJSON; try{ delete Array.prototype.toJSON; return JSON.stringify(o); } finally { if(__tj) Array.prototype.toJSON=__tj; }
'@
  $raw = (& $IeDom -Title $Window -UrlLike '*DoccrdWritng*' -Js $js) -join "`n"
  $raw = $raw.Trim()
  if ($raw -notlike '{*') { throw "기안기에서 읽지 못함: $raw" }
  $d = $raw | ConvertFrom-Json
  $kindGuess = if ($Kind) { $Kind } elseif ($d.files | Where-Object { $_.name -like '*.ozd' }) { '지출품의' } else { '일반기안' }
  $rec = [ordered]@{
    시각 = $now.ToString('yyyy-MM-dd HH:mm:ss'); 사건 = '작성'; 종류 = $kindGuess
    제목 = $d.title; 본문 = $d.body; 결재선 = @($d.line); 수신 = $d.recv
    과제카드 = $d.task; 공개 = $d.pub; 공개제한 = $d.reason; 직원열람제한 = $d.readng
    붙임 = @($d.files | ForEach-Object { [ordered]@{ 이름 = $_.name; 크기KB = [math]::Round($_.size / 1KB); 공개 = $_.open } })
    검증 = $Check; 메모 = $Note; 서식ID = $d.formId; 연계문서ID = $d.apprId
  }
} else {
  if (-not $Title) { throw "-Title 이 필요합니다" }
  $prev = Read-All | Where-Object { $_.제목 -eq $Title -and $_.사건 -eq '작성' } | Select-Object -Last 1
  if (-not $prev) { throw "같은 제목의 '작성' 기록이 없습니다: $Title" }
  $rec = [ordered]@{}
  foreach ($p in $prev.PSObject.Properties) { $rec[$p.Name] = $p.Value }
  $rec.시각 = $now.ToString('yyyy-MM-dd HH:mm:ss'); $rec.사건 = $Event; $rec.메모 = $Note
}

# 화면 값 → 읽기 쉬운 말
$KO = @{ none = '설정안함'; beforeComplete = '결재완료일까지'; expireDate = '지정날짜까지'; permanent = '영구'; open = '공개'; not_open = '비공개' }
function Ko($v) { if ($KO.ContainsKey([string]$v)) { $KO[[string]$v] } else { $v } }
if ($rec.직원열람제한) { $rec.직원열람제한 = Ko $rec.직원열람제한 }
foreach ($f in @($rec.붙임)) { if ($f -and $f.공개) { $f.공개 = Ko $f.공개 } }

# 1) jsonl
[IO.File]::AppendAllText($jsonl, ((ConvertTo-Json -InputObject $rec -Compress -Depth 6) + "`n"), $utf8)

# 2) csv (요약, 매번 다시 씀)
$rows = Read-All | ForEach-Object {
  [pscustomobject][ordered]@{
    시각 = $_.시각; 사건 = $_.사건; 종류 = $_.종류; 제목 = $_.제목; 결재선 = ($_.결재선 -join ' → ')
    과제카드 = $_.과제카드; 공개 = $_.공개; 공개제한 = $(if ($_.공개제한) { "$($_.공개제한)호" } else { '' })
    직원열람제한 = $_.직원열람제한; 붙임 = (($_.붙임 | ForEach-Object { "$($_.이름)($($_.공개))" }) -join '; ')
    검증 = $_.검증; 메모 = $_.메모 }
}
$csvText = ($rows | ConvertTo-Csv -NoTypeInformation) -join "`r`n"
[IO.File]::WriteAllText($csv, $csvText + "`r`n", (New-Object Text.UTF8Encoding($true)))

# 3) 문서별 md (같은 제목이면 같은 파일에 사건을 덧붙임)
$safe = ($rec.제목 -replace '[\\/:*?"<>|]', '_').Trim()
$first = Read-All | Where-Object { $_.제목 -eq $rec.제목 } | Select-Object -First 1
$day = ([datetime]$first.시각).ToString('yyyy-MM-dd')
$md = Join-Path $docs "${day}_$safe.md"
if (-not (Test-Path -LiteralPath $md)) {
  $att = ($rec.붙임 | ForEach-Object { "- $($_.이름) ($($_.크기KB)KB, $($_.공개))" }) -join "`n"
  $head = @"
# $($rec.제목)

| 항목 | 값 |
|---|---|
| 종류 | $($rec.종류) |
| 수신 | $($rec.수신) |
| 결재선 | $($rec.결재선 -join ' → ') |
| 과제카드 | $($rec.과제카드) |
| 대국민공개 | $($rec.공개)$(if ($rec.공개제한) { " ($($rec.공개제한)호)" }) |
| 직원열람제한 | $($rec.직원열람제한) |

## 본문
``````
$($rec.본문)
``````

## 붙임
$att

## 사건
"@
  [IO.File]::WriteAllText($md, $head + "`n", $utf8)
}
[IO.File]::AppendAllText($md, ("- {0} **{1}** {2} {3}`n" -f $rec.시각, $rec.사건, $(if ($rec.사건 -eq '작성' -and $rec.검증) { "(검증: $($rec.검증))" } else { '' }), $rec.메모), $utf8)

Write-Output ("기록: {0} [{1}] {2} → {3}" -f $rec.사건, $rec.종류, $rec.제목, $md)
