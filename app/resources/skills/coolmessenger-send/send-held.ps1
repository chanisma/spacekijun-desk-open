<#
대기 중인(작성만 해 둔) 쪽지창을 확인하고 발송한다.

    .\send-message.ps1 -To "홍길동" -Title "제목" -Body "본문" -DryRun   # 작성 후 대기
    .\send-held.ps1                                                      # 내용 확인만 (미발송)
    .\send-held.ps1 -Send                                                # 확인 후 발송
    .\send-held.ps1 -Discard                                             # 작성 취소(창 닫기)

-DryRun 으로 띄워 둔 '메시지 전송' 창을 찾아 수신자·제목·본문·첨부를 읽어 보여준다.
여러 창이 열려 있으면 -Index 로 고른다.
#>
param(
  [switch]$Send,
  [switch]$Discard,
  [int]$Index = 0,
  [int]$Port = 9222
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'native.ps1')

Add-Type -TypeDefinition @'
using System; using System.Text; using System.Runtime.InteropServices;
public class CmHeld {
  [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")]
  public static extern int SendGet(IntPtr h, int msg, int wp, StringBuilder lp);
}
'@ -ErrorAction SilentlyContinue

$wins = @(Get-CmWindows | Where-Object { $_.title -like '메시지 전송*' })
if ($wins.Count -eq 0) { Write-Host '대기 중인 쪽지창이 없습니다.'; return }
if ($wins.Count -gt 1) { Write-Host "쪽지창 $($wins.Count)개 — Index=$Index 사용" }
$c = $wins[$Index]
$kids = Get-CmChildren $c.hwnd

# 제목
$titleEdit = ($kids | Where-Object { $_.cls -eq 'Edit' -and $_.id -eq 4362 }).hwnd
$sb = New-Object System.Text.StringBuilder 1024
[CmHeld]::SendGet($titleEdit, 0x000D, 1024, $sb) | Out-Null
$title = $sb.ToString()

# 수신자 칩 / 첨부 칩 (둘 다 Afx 커스텀 컨트롤. 첨부는 "(NN KB)" 가 붙는다)
$chips = $kids | Where-Object { $_.vis -and $_.cls -like 'Afx*' -and $_.text -ne '' }
$to = ($chips | Where-Object { $_.text -notmatch '\((\d+(\.\d+)?)\s*(KB|MB|바이트)\)' -and $_.text -match '\(' }).text
$att = ($chips | Where-Object { $_.text -match '\((\d+(\.\d+)?)\s*(KB|MB|바이트)\)' }).text

# 본문 (CDP)
$bodyExpr = "(()=>{const f=document.getElementById('editFrame');return f&&f.contentDocument?f.contentDocument.body.innerText.replace(/\s+/g,' ').trim():'(iframe 없음)';})()"
$body = & node (Join-Path $here 'cdp.js') eval $bodyExpr --url=richtext 2>&1

# 예약전송 상태
# ⚠️ 이 버튼들은 BS_OWNERDRAW 라 BM_GETCHECK 이 항상 0 이다. 상태는 캡션 접두어로만 읽힌다.
#    '선택 예약전송' = ON / '해제 예약전송' = OFF  (SKILL.md '예약전송 함정' 참조)
$sched = ''
$schedCap = ($kids | Where-Object { $_.id -eq 1660 } | Select-Object -First 1).text
$dt = $kids | Where-Object { $_.cls -eq 'SysDateTimePick32' } | Select-Object -First 1
$sb2 = New-Object System.Text.StringBuilder 256
if ($dt) { [CmHeld]::SendGet($dt.hwnd, 0x000D, 256, $sb2) | Out-Null }
$schedOn = $schedCap -like '선택*'
$sched = if ($schedOn) { "예약전송 ON  → '$($sb2.ToString())' 에 도착" } else { "예약전송 표시상 OFF (그래도 '$($sb2.ToString())' 에 도착할 수 있음 — SKILL.md 참조)" }

Write-Host "`n─ 대기 중인 쪽지 ───────────────────────────"
Write-Host "  수신자 : $($to -join ' | ')"
Write-Host "  제목   : $title"
Write-Host "  본문   : $body"
Write-Host "  첨부   : $(if ($att) { $att -join ' | ' } else { '(없음)' })"
Write-Host "  발송   : $sched"
Write-Host "────────────────────────────────────────────`n"

if ($Discard) {
  # ⚠️ WM_CLOSE 는 '이 창을 닫으시겠습니까?' 모달을 띄운다. 응답하지 않으면 남아서 앱을 막는다.
  [CmNative]::PostMessage($c.hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # WM_CLOSE
  Start-Sleep -Seconds 2
  for ($i = 0; $i -lt 5; $i++) {
    $d = Get-CmWindows | Where-Object { $_.title -like '*닫으시겠습니까*' } | Select-Object -First 1
    if (-not $d) { break }
    $ok = (Get-CmChildren $d.hwnd | Where-Object { $_.id -eq 5025 }).hwnd     # 확인
    [CmNative]::PostMessage($ok, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
    Start-Sleep -Seconds 2
  }
  $left = [bool](Get-CmWindows | Where-Object { $_.title -like '메시지 전송*' })
  if ($left) { Write-Warning '창이 아직 남아 있습니다 — 확인 대화상자를 처리하지 못했을 수 있습니다.' }
  else { Write-Host '작성 취소 — 창을 닫았습니다.' }
  return
}
if (-not $Send) {
  Write-Host '확인만 했습니다. 보내려면 -Send, 취소하려면 -Discard 를 주세요.'
  return
}

# 발송 전 마지막 MessageKey 를 기록해 둔다 — 발송 후 "이보다 큰 행"이 생겼는지로 확인한다 (python 없으면 건너뜀)
$beforeKey = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
  $k = (& python (Join-Path $here 'check-sent.py') --max-key 2>&1) | Select-Object -Last 1
  if ("$k" -match '^\d+$') { $beforeKey = [int]$k }
}

$sendBtn = ($kids | Where-Object { $_.cls -eq 'Button' -and $_.text -eq '보내기' }).hwnd
[CmNative]::PostMessage($sendBtn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
Write-Host '보내기 클릭'
Start-Sleep -Seconds 8

# 확인은 제목이 아니라 MessageKey 증가로 한다 — tbl_send.Title 은 앞 약 29자만 저장돼 긴 제목은 늘 불일치한다.
# ⚠️ 확인 실패가 떠도 발송은 됐을 수 있다. 재발송 전에 check-sent.py 로 직접 확인할 것(중복 발송 방지).
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