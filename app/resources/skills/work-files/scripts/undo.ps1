# 정리 되돌리기 — 업무\정리 기록.csv 로 «옮긴 경로 → 원래 경로». 원래 자리에 같은 이름이 있으면 건너뛴다.
#   & .\undo.ps1                      기록에 있는 업무 폴더 목록
#   & .\undo.ps1 -Folder "<날짜_업무명>" [-WhatIf]
param([string]$Folder, [string]$Root, [switch]$WhatIf)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$root = Get-WfRoot $Root
$log = Get-WfLog $root
if (-not (Test-Path -LiteralPath $log)) { Write-Host "정리 기록이 없습니다: $log"; return }
$rows = @(Import-Csv -LiteralPath $log -Encoding UTF8)
if (-not $Folder) {
    $rows | Group-Object 업무폴더 | ForEach-Object { [pscustomobject]@{ 업무폴더 = $_.Name; 파일수 = $_.Count; 마지막 = ($_.Group | Select-Object -Last 1).시각 } } |
        Format-Table -AutoSize | Out-String -Width 300 | Write-Host
    return
}
$mine = @($rows | Where-Object { $_.업무폴더 -eq $Folder })
if (-not $mine) { throw "기록에 '$Folder' 이(가) 없습니다. -Folder 없이 실행해 목록을 보세요." }
$back = 0; $skipped = @(); $done = @()
foreach ($r in $mine) {
    if (-not (Test-Path -LiteralPath $r.옮긴경로)) { $skipped += "$(Split-Path $r.옮긴경로 -Leaf) — 업무 폴더에 없음(이미 되돌렸거나 옮겨짐)"; continue }
    if (Test-Path -LiteralPath $r.원래경로) { $skipped += "$(Split-Path $r.원래경로 -Leaf) — 원래 자리에 같은 이름이 있음"; continue }
    if ($WhatIf) { Write-Host "  [미리보기] $($r.옮긴경로) → $($r.원래경로)"; $back++; continue }
    $parent = Split-Path $r.원래경로 -Parent
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Move-Item -LiteralPath $r.옮긴경로 -Destination $r.원래경로
    Write-Host "  되돌림: $(Split-Path $r.원래경로 -Leaf)"
    $done += $r; $back++
}
if (-not $WhatIf -and $done) {
    # 되돌린 줄은 기록에서 뺀다
    $keep = $rows | Where-Object { $row = $_; -not ($done | Where-Object { $_.옮긴경로 -eq $row.옮긴경로 -and $_.시각 -eq $row.시각 }) }
    if ($keep) { $keep | Export-Csv -LiteralPath $log -NoTypeInformation -Encoding UTF8 } else { Remove-Item -LiteralPath $log }
    $dir = Join-Path (Join-Path $root '업무') $Folder
    if ((Test-Path -LiteralPath $dir) -and -not (Get-ChildItem -LiteralPath $dir -Force)) { Remove-Item -LiteralPath $dir; Write-Host "  빈 업무 폴더 지움: $Folder" }
}
Write-Host "결과: $(if ($WhatIf) { '되돌릴 예정' } else { '되돌림' }) $back 개$(if ($skipped) { ", 건너뜀 $($skipped.Count) 개" })"
$skipped | ForEach-Object { Write-Host "  건너뜀: $_" }
