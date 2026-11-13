<#
쿨메신저 쪽지 발송 — 다중 수신자 + 파일첨부 지원 (커서를 뺏지 않는 창 메시지 + CDP)

    & .\send-message.ps1 `   # ※ powershell -File 로 부르면 -To a,b 배열이 문자열 하나로 넘어간다 — 반드시 & 로 호출
      -To "홍길동","인공지능실" -Title "제목" -Body "본문`n둘째 줄" `
      -Attach "C:\path\a.txt","C:\path\b.pdf"

    -BodyHtml "<p>서식 <b>본문</b></p>"   HTML 직접 지정
    -DryRun                               작성만 하고 보내지 않음
    -Confirmed                            사용자 승인 후 발송 (필수 — 없으면 거부. 승인받은 본문과 같은 내용만 보낼 것)

동작
  1) 광고 팝업 닫기
  2) 조직도에서 첫 수신자 더블클릭 → '메시지 전송' 창
  3) 수신자가 2명 이상이면 [받는사람] → '사용자 선택' 창에서 나머지 추가 → 확인
  4) 제목 WM_SETTEXT (Edit 4362)
  5) 본문 CDP setHtml()
  6) 첨부: [파일첨부] → '열기' 창 Edit(1148)에 전체 경로 → 열기(1)   ※ 파일 수만큼 반복
  7) 예약전송/나에게보내기 해제  ※ 예약전송은 기본이 ON! 끄지 않으면 ~10분 뒤 발송됨
  8) 보내기(3249) → check-sent.py 로 tbl_send 확인 (발송 직전 MessageKey 보다 큰 행이 생겼는지)

⚠️ 모달 대화상자를 여는 버튼(받는사람·파일첨부·확인·열기·보내기)은 **반드시 PostMessage**.
   SendMessage 로 누르면 대화상자가 닫힐 때까지 블록된다.
#>
param(
  [Parameter(Mandatory = $true)][string[]]$To,
  [Parameter(Mandatory = $true)][string]$Title,
  [string]$Body = '',
  [string]$BodyHtml = '',
  [string[]]$Attach = @(),
  [datetime]$ScheduleAt,          # 지정 시각까지 서버에서 대기 (앱의 예약전송)
  [int]$Port = 9222,
  [switch]$CopyToSelf,      # '나에게 보내기' 유지 (기본: 끔)
  [switch]$DryRun,
  [switch]$Confirmed       # 사용자가 초안(받는이·제목·본문)을 확인·승인했음을 선언 — 없으면 -DryRun 외에는 발송을 거부한다
)

$ErrorActionPreference = 'Stop'
# ── 발송 승인 게이트 ──────────────────────────────────────────
# 쪽지는 회수할 수 없다. 사용자가 초안을 보고 승인했다는 선언(-Confirmed) 없이는 UI 를 건드리기 전에 멈춘다.
# (작성만 하는 -DryRun 은 예외 — 창에 올린 내용을 send-held.ps1 로 확인한 뒤 -Send 한다)
if (-not $DryRun -and -not $Confirmed) {
    throw '발송 전 사용자 확인이 필요합니다. 받는 사람·제목·본문 초안을 사용자에게 보여 주고 승인을 받은 뒤 -Confirmed 를 붙여 다시 실행하세요. (작성만 하려면 -DryRun)'
}
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'native.ps1')

Add-Type -TypeDefinition @'
using System; using System.Text; using System.Runtime.InteropServices;
public class CmSend {
  [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")]
  public static extern int SendGet(IntPtr h, int msg, int wp, StringBuilder lp);
}
'@ -ErrorAction SilentlyContinue

function Read-Ctrl([IntPtr]$h) {
  $sb = New-Object System.Text.StringBuilder 1024
  [CmSend]::SendGet($h, 0x000D, 1024, $sb) | Out-Null
  $sb.ToString()
}
function Wait-Window2([string]$titleLike, [int]$sec = 20, $exclude = @()) {
  for ($i = 0; $i -lt ($sec * 2); $i++) {
    $w = Get-CmWindows | Where-Object { $_.title -like $titleLike -and $exclude -notcontains $_.hwnd } | Select-Object -First 1
    if ($w) { return $w }
    Start-Sleep -Milliseconds 500
  }
  $null
}
$BM_CLICK = 0x00F5; $WM_SETTEXT = 0x000C; $BM_GETCHECK = 0x00F0; $BM_SETCHECK = 0x00F1

# ── 0) 전제 ────────────────────────────────────────────────────
Ensure-CmRunning -Port $Port | Out-Null      # 꺼져 있을 때만 켠다 (켜진 앱은 재시작하지 않는다)
if (-not (Get-CmPid)) { throw '쿨메신저가 실행 중이 아닙니다.' }
try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 4 }
catch { throw "CDP 포트 $Port 가 닫혀 있습니다. 앱이 디버깅 포트 없이 켜져 있습니다 — .\start-coolmessenger.ps1 -Restart 로 다시 띄우세요(작성 중인 쪽지창은 사라집니다)." }
foreach ($f in $Attach) { if (-not (Test-Path $f)) { throw "첨부 파일 없음: $f" } }

Close-CmAdPopup | Out-Null
Start-Sleep -Milliseconds 400

# ★ 메인 창이 **최소화돼 있으면 조직도 더블클릭이 먹지 않는다** (2026-09-10 실측).
#   트리 좌표는 정상인데 쪽지창이 조용히 안 열린다. SW_RESTORE 로 복원만 해 두면 된다.
#   SetForegroundWindow 는 쓰지 않는다 — 포커스를 뺏으면 사용자 작업을 방해한다.
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class CmShow { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
                      [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
                      [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); }' -ErrorAction SilentlyContinue
# 트레이로 숨기면 Get-CmWindows(기본)에서 아예 빠져 '트리 없음' 으로 실패한다 → 숨은 것까지 찾는다
$mainWin = Get-CmWindows -IncludeHidden | Where-Object { $_.title -like 'COOLMESSENGER*' } | Select-Object -First 1
if ($mainWin) {
    if (-not [CmShow]::IsWindowVisible($mainWin.hwnd)) {
        Write-Host '메인 창이 숨겨져 있어 표시합니다'
        [CmShow]::ShowWindow($mainWin.hwnd, 5) | Out-Null  # SW_SHOW
        Start-Sleep -Milliseconds 500
    }
    if ([CmShow]::IsIconic($mainWin.hwnd)) { Write-Host '메인 창이 최소화돼 있어 복원합니다' }
    [CmShow]::ShowWindow($mainWin.hwnd, 9) | Out-Null      # SW_RESTORE
    Start-Sleep -Milliseconds 800
} else {
    throw '쿨메신저 메인 창을 찾지 못했습니다. 앱이 실행 중이고 로그인돼 있는지 확인하세요. 샌드박스(예: Codex 기본 샌드박스)나 다른 데스크톱 세션에서 실행 중이면 사용자 창이 보이지 않습니다 — 샌드박스 밖(full access 또는 승인 후 실행)에서 다시 실행하세요.'
}

# 조직도 검색칸에 글자가 남아 있으면 트리가 걸러져 수신자를 못 찾는다 — 먼저 풀어 둔다
Reset-CmSearch | Out-Null

# ── 0-1) 수신자 이름 해석 ──────────────────────────────────────
# 조직도 대화명이 실명이 아닌 경우가 있다 (예: 홍길동 → '(보건실)홍길동').
# 요청받은 이름을 그대로 트리에 넣으면 못 찾으므로 명부·별칭으로 실제 항목을 찾는다.
if ((Get-CmRoster).Count -eq 0) { Sync-CmRoster | Out-Null }
$ToResolved = @()
foreach ($n in $To) {
    $r = Resolve-CmName $n
    if (-not $r.ok) {
        throw ("수신자 '$n' 을 특정하지 못했습니다. $($r.why)" +
               $(if ($r.candidates -and $r.candidates.Count) { "`n  후보: " + ($r.candidates -join ', ') +
                 "`n  해결: Set-CmAlias '$n' '<대화명>'" } else { '' }))
    }
    if ($r.text -ne $n) { Write-Host "수신자 해석: '$n' → '$($r.text)'  ($($r.why))" }
    $ToResolved += $r.text
}

# ── 1) 쪽지창 열기 (첫 수신자) ─────────────────────────────────
$before = @(Get-CmWindows | Where-Object { $_.title -like '메시지 전송*' }).hwnd
Select-CmTreeItem $ToResolved[0] -DoubleClick | Out-Null
$compose = Wait-Window2 '메시지 전송*' 20 $before
if (-not $compose) { throw "'$($ToResolved[0])' 쪽지창이 열리지 않았습니다." }
$kids = Get-CmChildren $compose.hwnd
Write-Host "쪽지창 열림 | 수신자: $((($kids | Where-Object { $_.vis -and $_.text -ne '' -and $_.cls -like 'Afx*' }).text) -join ',')"

# ── 2) 추가 수신자 (사용자 선택 창) ────────────────────────────
if ($To.Count -gt 1) {
  $pickBtn = ($kids | Where-Object { $_.id -eq 1656 }).hwnd     # 받는사람
  [CmNative]::PostMessage($pickBtn, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  $dlg = Wait-Window2 '사용자 선택' 20
  if (-not $dlg) { throw "'사용자 선택' 창이 열리지 않았습니다." }
  $dk = Get-CmChildren $dlg.hwnd
  $srcTree = ($dk | Where-Object { $_.id -eq 1400 }).hwnd
  $selTree = ($dk | Where-Object { $_.id -eq 1401 }).hwnd
  $addBtn = ($dk | Where-Object { $_.id -eq 1636 }).hwnd
  $okBtn = ($dk | Where-Object { $_.id -eq 3007 }).hwnd
  foreach ($n in $ToResolved[1..($ToResolved.Count - 1)]) {
    $hit = Select-CmItemIn -TreeHwnd $srcTree -name $n
    if (-not $hit) { Write-Warning "'$n' 을 조직도에서 찾지 못했습니다 — 건너뜀"; continue }
    [CmNative]::SendMessage($addBtn, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    Start-Sleep -Milliseconds 800
    Write-Host "  추가: $($hit.text)"
  }
  $picked = (Get-CmTree -TreeHwnd $selTree | Where-Object { $_.depth -gt 0 } | ForEach-Object { $_.text }) -join ' | '
  Write-Host "  선택된 사람: $picked"
  [CmNative]::PostMessage($okBtn, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  Start-Sleep -Seconds 3
  $kids = Get-CmChildren $compose.hwnd
}

# ── 3) 제목 ────────────────────────────────────────────────────
$titleEdit = ($kids | Where-Object { $_.cls -eq 'Edit' -and $_.id -eq 4362 }).hwnd
[CmNative]::SendMessageStr($titleEdit, $WM_SETTEXT, [IntPtr]::Zero, $Title) | Out-Null
Start-Sleep -Milliseconds 300
if ((Read-Ctrl $titleEdit) -ne $Title) { Write-Warning '제목 확인 불일치' } else { Write-Host '제목 입력 확인' }

# ── 4) 본문 (CDP) ──────────────────────────────────────────────
$html = if ($BodyHtml) { $BodyHtml } else { '<p>' + ($Body -replace "`r?`n", '</p><p>') + '</p>' }
$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($html))
$expr = "(()=>{const h=new TextDecoder().decode(Uint8Array.from(atob('$b64'),c=>c.charCodeAt(0)));setHtml(h);const f=document.getElementById('editFrame');return f&&f.contentDocument?f.contentDocument.body.innerText.replace(/\s+/g,' ').slice(0,80):'(iframe 없음)';})()"
Write-Host ("본문 입력 → " + (& node (Join-Path $here 'cdp.js') eval $expr --url=richtext 2>&1))

# ── 5) 파일 첨부 ───────────────────────────────────────────────
foreach ($f in $Attach) {
  $full = (Resolve-Path $f).Path
  $attBtn = ($kids | Where-Object { $_.id -eq 1449 }).hwnd
  [CmNative]::PostMessage($attBtn, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # 모달 → Post
  $fd = Wait-Window2 '열기' 20
  if (-not $fd) { Write-Warning "'열기' 창이 안 떴습니다 — 첨부 건너뜀: $full"; continue }
  $fk = Get-CmChildren $fd.hwnd
  $nameEdit = ($fk | Where-Object { $_.cls -eq 'Edit' -and $_.id -eq 1148 -and $_.vis }).hwnd
  $openBtn = ($fk | Where-Object { $_.cls -eq 'Button' -and $_.id -eq 1 }).hwnd
  [CmNative]::SendMessageStr($nameEdit, $WM_SETTEXT, [IntPtr]::Zero, $full) | Out-Null     # 전체 경로 = 폴더 탐색 불필요
  Start-Sleep -Milliseconds 500
  [CmNative]::PostMessage($openBtn, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
  Start-Sleep -Seconds 3
  $kids = Get-CmChildren $compose.hwnd
  $chip = ($kids | Where-Object { $_.vis -and $_.text -like "*$([IO.Path]::GetFileName($full))*" }).text
  if ($chip) { Write-Host "첨부 확인: $chip" } else { Write-Warning "첨부 칩을 확인하지 못했습니다: $full" }
}

# ── 6) 예약전송 상태 확인 (건드리지 않는다) ────────────────────
# 🚨 검증 결과(SKILL.md '예약전송 함정' 참조):
#   · 새 작성창은 예약전송이 기본 ON, DTP 기본값 = 현재+10분
#   · 버튼들이 BS_OWNERDRAW 라 BM_GETCHECK/BM_SETCHECK 는 전혀 통하지 않는다.
#     실제 상태는 캡션 접두어('선택'=ON / '해제'=OFF)로만 읽을 수 있다
#   · 체크를 해제해도 앱은 DTP 시각으로 예약을 걸어 버린다 (해제 상태로 보낸 key=723 이
#     ScheduledDate 16:38:00 을 받고 정확히 그 시각에 도착)
#   · 토글하면 수신자 칩이 지워질 때가 있고, 그 상태로 보내면 아무 일도 안 일어난다
#   ⇒ 토글은 이득 없이 위험만 크므로 **건드리지 않는다.** 대신 도착 예정 시각을 알린다.
function Get-CmToggle([IntPtr]$composeHwnd, [int]$id) {
  $t = ((Get-CmChildren $composeHwnd) | Where-Object { $_.id -eq $id }).text
  if ($t -like '선택*') { 'ON' } elseif ($t -like '해제*') { 'OFF' } else { "?($t)" }
}
if ($PSBoundParameters.ContainsKey('ScheduleAt')) {
  throw @'
-ScheduleAt 은 현재 지원하지 않습니다.
DTM_SETSYSTEMTIME 으로 예약 시각을 바꾸면 값은 반영되지만 '보내기'가 무응답이 됩니다
(DTN_DATETIMECHANGE 알림이 가지 않아 앱 내부 예약시각이 어긋나는 것으로 추정).
자세한 내용은 SKILL.md 의 '예약전송 함정' 을 보세요.
'@
}
$schedState = Get-CmToggle $compose.hwnd 1660
$selfState  = Get-CmToggle $compose.hwnd 1661
$dtpCtrl = (Get-CmChildren $compose.hwnd) | Where-Object { $_.cls -eq 'SysDateTimePick32' } | Select-Object -First 1
$dtpText = ''
if ($dtpCtrl) { $sb9 = New-Object System.Text.StringBuilder 256; [CmSend]::SendGet($dtpCtrl.hwnd, 0x000D, 256, $sb9) | Out-Null; $dtpText = $sb9.ToString() }
Write-Host "  예약전송=$schedState  나에게보내기=$selfState  예약시각='$dtpText'"
if ($schedState -eq 'ON') { Write-Warning "이 쪽지는 즉시 발송되지 않고 '$dtpText' 에 도착합니다." }
$kids = Get-CmChildren $compose.hwnd

$finalTo = (($kids | Where-Object { $_.vis -and $_.cls -like 'Afx*' -and $_.text -match '\(' -and $_.text -notmatch 'KB|MB' }).text) -join ' | '
Write-Host "`n최종 수신자: $finalTo"
if ($DryRun) { Write-Host '[DryRun] 작성만 완료 — 창을 그대로 둡니다.'; return }

# ── 7) 발송 ────────────────────────────────────────────────────
# 발송 전 마지막 MessageKey 를 기록해 둔다 — 발송 후 "이보다 큰 행"이 생겼는지로 확인한다 (python 없으면 건너뜀)
$beforeKey = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $k = (& python (Join-Path $here 'check-sent.py') --max-key 2>&1) | Select-Object -Last 1
    if ("$k" -match '^\d+$') { $beforeKey = [int]$k }
}$sendBtn = ($kids | Where-Object { $_.cls -eq 'Button' -and $_.text -eq '보내기' }).hwnd
[CmNative]::PostMessage($sendBtn, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
Write-Host '보내기 클릭'
Start-Sleep -Seconds 8

# ── 8) 검증 ────────────────────────────────────────────────────
# 발송 직전의 마지막 MessageKey($beforeKey)보다 큰 보낸 쪽지가 생겼는지 check-sent.py 로 본다(읽기 전용).
# 제목은 비교하지 않는다 — tbl_send.Title 은 앞 약 29자만 저장돼 긴 제목은 늘 불일치한다.
# ⚠️ 확인 실패가 떠도 **발송은 됐을 수 있다.** 재발송 전에 check-sent.py 로 직접 확인할 것(중복 발송 방지).
if ($null -eq $beforeKey) {
    Write-Warning 'python 이 없어 발송 기록 확인을 건너뜁니다. 보낸 쪽지함 또는 check-sent.py 로 확인하세요.'
    return
}
$check = ''
for ($i = 0; $i -lt 4; $i++) {
    $check = (& python (Join-Path $here 'check-sent.py') --after $beforeKey --body-chars 60 2>&1) -join "`n"
    if ($check -match 'key=\d+') { break }
    Start-Sleep -Seconds 3
}
Write-Host "`n--- 발송 기록 ---`n$check"
if ($check -match 'key=\d+') {
    Write-Host '✅ 발송 확인'
    if ($check -match '도착 예약') { Write-Warning '예약 발송입니다 — 표시된 시각에 도착합니다.' }
} else {
    Write-Warning '발송 기록에서 새 쪽지를 확인하지 못했습니다 — check-sent.py 로 직접 확인하세요(확인 전에는 재발송하지 마세요: 중복 발송됩니다).'
}