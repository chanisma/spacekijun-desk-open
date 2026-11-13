# 고른 파일을 <자동화 업무>\업무\<날짜>_<업무명>\ 으로 옮긴다(복사 아님). 덮어쓰지 않는다. 기록: 업무\정리 기록.csv
#   & .\move.ps1 -Task "업무명" [-Date 2026-10-30] -Files "a","b" [-Root <폴더>] [-WhatIf]
param([Parameter(Mandatory)][string]$Task, [string]$Date, [Parameter(Mandatory)][string[]]$Files, [string]$Root, [switch]$WhatIf)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$root = Get-WfRoot $Root
if (-not $Date) { $Date = (Get-Date).ToString('yyyy-MM-dd') }
if ($Date -notmatch '^\d{4}-\d{2}-\d{2}$') { throw "날짜는 YYYY-MM-DD 로 주세요: $Date" }
$name = ConvertTo-WfName $Task
if (-not $name) { throw '업무명이 비었습니다.' }
$folderName = "${Date}_$name"
$dest = Join-Path (Join-Path $root '업무') $folderName
$log = Get-WfLog $root

Write-Host "작업 폴더: $root"
Write-Host "옮길 곳  : $dest$(if (Test-Path -LiteralPath $dest) { '  (이미 있음 — 그 안에 더함)' })"
$moved = 0; $skipped = @()
foreach ($src in $Files) {
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { $skipped += "$src — 파일 없음"; continue }
    $file = Get-Item -LiteralPath $src
    $target = Join-Path $dest $file.Name
    if ($file.DirectoryName -eq $dest) { $skipped += "$($file.Name) — 이미 그 폴더에 있음"; continue }
    if (Test-Path -LiteralPath $target) { $skipped += "$($file.Name) — 같은 이름이 있어 건너뜀(덮어쓰지 않음)"; continue }
    if ($WhatIf) { Write-Host "  [미리보기] $($file.FullName) → $target"; $moved++; continue }
    try {
        if (-not (Test-Path -LiteralPath $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
        Move-Item -LiteralPath $file.FullName -Destination $target
    } catch { $skipped += "$($file.Name) — 옮기지 못함(열려 있나요?): $($_.Exception.Message)"; continue }
    $line = [pscustomobject]@{ 시각 = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'); 업무폴더 = $folderName; 원래경로 = $file.FullName; 옮긴경로 = $target }
    $line | Export-Csv -LiteralPath $log -Append -NoTypeInformation -Encoding UTF8
    Write-Host "  옮김: $($file.Name)"
    $moved++
}
$verb = if ($WhatIf) { '옮길 예정' } else { '옮김' }
Write-Host "결과: $verb $moved 개$(if ($skipped) { ", 건너뜀 $($skipped.Count) 개" })"
$skipped | ForEach-Object { Write-Host "  건너뜀: $_" }
if (-not $WhatIf -and $moved) { Write-Host "기록: $log" }
