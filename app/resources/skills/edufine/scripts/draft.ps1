# draft.ps1 — 열려 있는 에듀파인 기안기(WXSClient)를 spec(JSON) 대로 채우고 결재올림 검증까지 한다.
#   결재올림·임시저장은 누르지 않는다. 끝나면 사람이 화면을 보고 [결재올림] 을 누른다.
#   끝에 draft-log.ps1 로 '작성' 기록을 남긴다. 상신하면: draft-log.ps1 -Event 상신 -Title <제목> -Note <결과>
#
#   powershell -ExecutionPolicy Bypass -File draft.ps1 -Spec draft.json [-Only title,body,...]
#
#   draft.json (UTF-8):
#   {
#     "window": "표준서식",                       기안기 창 제목 일부
#     "title": "2026년 … 결과 보고",
#     "bodyFile": "C:\\…\\body.txt",             본문(줄바꿈 그대로). 없으면 건너뜀
#     "approvers": ["검토자 이름", "결재권자 이름"], 기안자 다음 순서대로(검토→결재) — 실행 전에 사용자에게 확인
#     "taskCard": "일과운영관리",                  과제카드 목록의 이름(일부)
#     "publication": "partial",                   open | partial | not
#     "reasons": [6],                             부분공개·비공개 사유(1~8호). 6호 = 개인정보
#     "attachments": [ { "path": "C:\\…\\a.pdf", "open": false } ]  자동으로 넣지 않는다 — 안내·공개여부·누락 확인만
#   }
param([Parameter(Mandatory)][string]$Spec, [string[]]$Only = @())
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$IeDom = Join-Path $here 'ie-dom.ps1'
$S = Get-Content -LiteralPath $Spec -Raw -Encoding utf8 | ConvertFrom-Json
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
function Want($k) { -not $Only -or $Only -contains $k }
function Log($m) { Write-Output ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $m) }
function J($o) { if ($null -eq $o) { 'null' } else { ConvertTo-Json -InputObject $o -Compress -Depth 5 } }
function Js([string]$title, [string]$code, $argsObj = $null, [int]$wait = 0, [switch]$quiet) {
  $p = @{ Title = $title; Js = $code; ArgsJson = (J $argsObj); WaitMs = $wait }
  if ($title -eq $W) { $p.UrlLike = '*DoccrdWritng*' }   # 같은 제목의 로그인/오류 창이 섞여 있어도 작성 화면을 고른다
  if ($quiet) { $p.Quiet = $true }
  (& $IeDom @p) -join "`n"
}
function Wait-Window([string]$pat, [int]$ms = 15000) {
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalMilliseconds -lt $ms) {
    $w = (& $IeDom -List) | Where-Object { $_ -like "*$pat*" }
    if ($w) { return $w }
    Start-Sleep -Milliseconds 400
  }
  throw "창이 뜨지 않음: $pat"
}
function Wait-Gone([string]$pat, [int]$ms = 15000) {
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalMilliseconds -lt $ms) {
    if (-not ((& $IeDom -List) | Where-Object { $_ -like "*$pat*" })) { return }
    Start-Sleep -Milliseconds 400
  }
  throw "창이 닫히지 않음: $pat"
}
# '웹 페이지 메시지'(alert/confirm) 가 떠 있으면 문구를 남기고 지정 버튼으로 닫는다 — 떠 있는 동안은 execScript 가 멈춘다
function Close-WebMsg([string]$button = '취소') {
  $r = (& $IeDom -CloseMsg $button) -join ' / '
  if ($r -ne 'NONE') { Log "메시지: $r" }
}

$W = if ($S.window) { $S.window } else { '표준서식' }
# 기안기가 막 열렸으면 로그인 페이지(wxsLogin.do)를 거쳐 작성 화면이 뜨기까지 시간이 걸리고,
# 그사이 '자동저장문서를 읽어오시겠습니까?' 가 뜰 수 있다 → 작성 화면 준비될 때까지 기다리며 그 메시지는 취소
$ready = $false
for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
  if ((& $IeDom -List) -match '웹 페이지 메시지') { Close-WebMsg '취소'; Start-Sleep -Milliseconds 800; continue }
  $r = (& $IeDom -Title $W -UrlLike '*DoccrdWritng*' -Js 'return (/retrieveDoccrdWritng|DoccrdWritng/.test(document.URL) && document.getElementById("Sj") && typeof IMPL_PutFieldText=="function" && typeof domHox1!="undefined") ? "READY" : "WAIT";') -join ''
  if ($r -eq 'READY') { $ready = $true } else { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw "기안기 작성 화면이 준비되지 않음 (창 제목에 '$W' 가 들어 있는지, 로그인됐는지 확인)" }
Start-Sleep -Milliseconds 1500
if ((& $IeDom -List) -match '웹 페이지 메시지') { Close-WebMsg '취소'; Start-Sleep -Milliseconds 800 }
Log ("기안기: " + (Js $W 'return document.URL.split("?")[0];'))

# ── 제목 ───────────────────────────────────────────
if ((Want 'title') -and $S.title) {
  Log ("제목: " + (Js $W 'var s=document.getElementById("Sj"); s.value=ARGS; input_changed(s); return s.value;' $S.title))
}

# ── 본문 (본문 필드에 직접) ─────────────────────────
if ((Want 'body') -and $S.bodyFile) {
  $body = (Get-Content -LiteralPath $S.bodyFile -Raw -Encoding utf8).TrimEnd() -replace "`r?`n", "`r`n"
  Log ("본문: " + (Js $W 'IMPL_PutFieldText("editor1","본문",ARGS); var t=String(IMPL_GetFieldText("editor1","본문")); return t.length+"자 / "+t.substr(0,40);' $body))
}

# ── 결재선 ─────────────────────────────────────────
if ((Want 'route') -and $S.approvers) {
  Js $W 'setTimeout(function(){fncReportCours();},10); return "open";' | Out-Null
  Wait-Window '결재경로설정' | Out-Null; Start-Sleep -Milliseconds 800
  foreach ($name in $S.approvers) {
    $r = Js '결재경로설정' @'
var box=document.getElementById('userNm'), sel=document.getElementById('searchUser');
if (!box) return 'ERR 사용자명 입력칸(userNm) 없음';
if (sel && sel.selectedIndex!=0){ sel.selectedIndex=0; try{ $(sel).change(); }catch(e){} }
var uid=document.getElementById('userId'); if (uid) uid.value='';
box.value=ARGS; fncRetrieveReprsntInsttOrgnztUserList();
var n=0; (function poll(){ n++; try{ var d=document.frames[1].document; var rs=d.getElementsByName('partSelRadio');
  var hit=[]; for(var k=0;k<rs.length;k++) if(rs[k].value==ARGS) hit.push(rs[k]);
  if (d.readyState=='complete' && rs.length){ if(hit.length!=1) return __done((function(){var t=[];for(var z=0;z<rs.length;z++)t.push(rs[z].title);return 'ERR '+ARGS+' 검색 '+hit.length+'명: '+t.join(', ');})());
    hit[0].checked=true; hit[0].parentNode.parentNode.click(); fncAdd();
    var pl=PrtcpList.toArray(), s=[]; for(var q=0;q<pl.length;q++) s.push(pl[q].name+'/'+pl[q].positionName); return __done(s.join(' → ')); } }catch(e){}
  if (n<40) setTimeout(poll,250); else __done('ERR 검색 시간초과'); })();
'@ $name 12000
    Log "결재선 + $name : $r"
    if ($r -like 'ERR*') { throw $r }
  }
  Js '결재경로설정' 'setTimeout(function(){fncVerify();},10); return "verify";' | Out-Null
  Wait-Gone '결재경로설정'
  Log ("결재선 반영: " + (Js $W 'var e=domHox1.selectNodes("/hox/approvalFlow/participant"), s=[]; for(var i=0;i<e.length;i++) s.push(get_text(e[i],"name")+"("+get_text(e[i],"approvalType")+")"); return s.join(" → ");'))
}

# ── 과제카드 (Nexacro 팝업) ─────────────────────────
if ((Want 'task') -and $S.taskCard) {
  Js $W 'setTimeout(function(){fncChooseTkcrd();},10); return "open";' | Out-Null
  Wait-Window 'K-에듀파인 -- 웹 페이지 대화 상자' | Out-Null
  $r = Js 'K-에듀파인 -- 웹 페이지 대화 상자' @'
var n=0; (function poll(){ n++; try{ var f=nexacro.getApplication().mainframe.frame.form, ds=f.dsAList;
  if (ds && ds.getRowCount()>0){ var hit=-1, all=[]; for(var r=0;r<ds.getRowCount();r++){ var nm=ds.getColumn(r,'tkcrdNm'); all.push(nm); if(hit<0 && nm.indexOf(ARGS)>=0) hit=r; }
    if (hit<0) return __done('ERR 과제카드 없음. 목록: '+all.join(', '));
    f.fnSelectUnitTkcrd(hit); var nm2=ds.getColumn(hit,'tkcrdNm');
    setTimeout(function(){ f.Tab00_Tabpage1_divAuth_btnAuthC01_onclick(null,null); },300); return __done(nm2); } }catch(e){}
  if (n<40) setTimeout(poll,250); else __done('ERR 과제카드 목록 시간초과'); })();
'@ $S.taskCard 12000
  Log "과제카드 선택: $r"
  if ($r -like 'ERR*') { throw $r }
  Wait-Gone 'K-에듀파인 -- 웹 페이지 대화 상자'
  Log ("과제카드 반영: " + (Js $W 'return document.getElementById("taskInfo").innerText;'))
}

# ── 대국민 공개여부 ────────────────────────────────
if ((Want 'pub') -and $S.publication) {
  $r = Js $W @'
var idx={open:1,partial:2,not:3}[ARGS.p]; if(!idx) return 'ERR publication 값';
document.getElementById('othbcLmtt'+idx).click();
if (idx>1){ for(var k=1;k<=8;k++){ var c=document.getElementById('othbcAt'+k), want=(ARGS.r||[]).indexOf(k)>=0; if(c.checked!=want) c.click(); } }
if (idx==1){ var rl=document.getElementById('readngLmtt0'); if(rl && !rl.checked) rl.click(); }   // 공개면 직원열람제한 '설정안함' 이어야 검증 통과
// 이미 붙어 있는 파일(재정문서 지출품의서.ozd 등)의 공개여부: 공개 문서면 open, 아니면 not_open
var want=(idx==1)?'open':'not_open', rs=document.getElementsByTagName('input'), n=0;
for (var j=0;j<rs.length;j++) if(rs[j].type=='radio' && /^modiAttachOthbcSe/.test(rs[j].name) && rs[j].value==want && !rs[j].checked){ rs[j].click(); n++; }
return get_text(domHox1,_PUBLICATION)+' 사유='+get_text(domHox1,'/hox/docInfo/publication/publicationFlag')+' 열람제한='+(function(){var r=document.getElementsByName('readngLmtt');for(var q=0;q<r.length;q++)if(r[q].checked)return r[q].value;})()+' 파일공개='+want+'('+n+')';
'@ @{ p = $S.publication; r = @($S.reasons) } 0 -quiet
  Log "공개여부: $r"
}

# ── 붙임 ───────────────────────────────────────────
# ⚠ 붙임은 자동으로 넣지 않는다. `Attach.fileBox.addFiles([new HsFile(경로,…)], undefined, true)`
#   (= 첨부 컨트롤 AddItemByGroup) 로 넣은 PC 파일은 화면·컨트롤 등록은 정상인데 상신 뒤 결재자에게
#   "아예 안 열리는" 파일로 올라갔다(2026-11-10, 원본과 바이트가 같은 PDF — [파일 추가] 로 다시 붙이니 정상).
#   그 통로는 서버에 이미 있는 파일(FID/TRID 주소)을 다시 붙일 때 쓰는 것이다. PC 파일은 사람이 [파일 추가] 로 넣는다.
#   이 단계는 넣을 파일을 안내하고, 이미 들어 있는 파일(같은 이름)의 공개여부만 맞추고 빠진 것을 알린다.
#   사람이 넣은 뒤 `-Only attach` 로 다시 돌려 공개여부·누락을 확인한다.
if ((Want 'attach') -and $S.attachments) {
  $files = foreach ($a in $S.attachments) { $fi = Get-Item -LiteralPath $a.path; @{ path = $fi.FullName; name = $fi.Name; size = $fi.Length; open = [bool]$a.open } }
  $r = Js $W @'
var fb=Attach.fileBox, lim=(doccfg.inDocMaxFileSize||10)*1024*1024, out=[], have={};
for (var g=0; g<fb._files.length; g++) have[fb._files[g].name]=true;
for (var i=0;i<ARGS.length;i++){ var a=ARGS[i];
  if (a.size>lim) out.push('용량초과 '+a.name+' ('+Math.round(a.size/1048576)+'MB > '+doccfg.inDocMaxFileSize+'MB) — 줄여서 넣을 것');
  else if (!have[a.name]) out.push('직접 넣을 것: '+a.path); }
var groups={}, order=[], rs=document.getElementsByTagName('input');
for (var j=0;j<rs.length;j++) if(rs[j].type=='radio' && /^modiAttachOthbcSe/.test(rs[j].name)){ if(!groups[rs[j].name]){groups[rs[j].name]=[];order.push(rs[j].name);} groups[rs[j].name].push(rs[j]); }
for (var g=0; g<order.length; g++){ var nm=fb._files[g]?fb._files[g].name:'', want=null;
  for (var i=0;i<ARGS.length;i++) if(ARGS[i].name==nm) want=ARGS[i].open?'open':'not_open';
  if (!want) { out.push(nm+' (spec 에 없음 — 그대로 둠)'); continue; }
  var grp=groups[order[g]]; for(var q=0;q<grp.length;q++) if(grp[q].value==want && !grp[q].checked) grp[q].click(); out.push(nm+' 공개='+want); }
return out.join(' | ')+' | 붙임 '+fb._files.length+'개 / 컨트롤 '+fb._hsAttach.getFilesCount()+'개';
'@ @($files) 0 -quiet
  Log "붙임: $r"
  if ($r -match '직접 넣을 것|용량초과') { Log '붙임은 기안기 [파일 추가] 로 사람이 넣는다(자동 첨부 금지) — 넣은 뒤 -Only attach 로 다시 확인.' }
}

# ── 결재올림 전 검증(올리지는 않음) ────────────────────
$v = Js $W 'var a=fncValidateComn(); var b=(a===true)?fncValidate():"skip"; return "공통="+a+" 기안="+b;' $null 0 -quiet
Log "검증: $v"
# 기안 기록(로그) — 화면에 실제로 들어간 값을 읽어 남긴다
try { $chk = ($v -split "`n")[0]; Log ((& (Join-Path $here 'draft-log.ps1') -Event 작성 -Window $W -Check $chk) -join ' ') } catch { Log "기록 실패: $($_.Exception.Message)" }
Log '끝 — [결재올림] 은 사람이 화면을 확인한 뒤 누른다.'
