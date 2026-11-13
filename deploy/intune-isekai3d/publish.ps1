<#
  스페이스기전 학생 · 이세계 사회인 캐릭터 — build.ps1 로 만든 .intunewin 을 Intune 에 올리기 (2026-10-19 요청).

    powershell -ExecutionPolicy Bypass -File deploy\intune-isekai3d\publish.ps1 -DryRun   # 지금 상태와 할 일만 보인다
    powershell -ExecutionPolicy Bypass -File deploy\intune-isekai3d\publish.ps1           # 올린다 (올리기 전에 한 번 묻는다)

  올리는 일은 학생판의 deploy\intune\publish-intune.ps1 이 한다 — 앱 이름·패키지·검색 규칙 키만 이 앱 것으로 넘긴다.
  로그인 준비(테넌트·클라이언트 ID)도 그쪽 머리말과 같다.
#>
param([switch]$DeviceCode, [switch]$DryRun, [switch]$Yes)

$ErrorActionPreference = 'Stop'
$root  = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$state = Join-Path $root 'dist\intune-isekai3d\latest.json'
if (-not (Test-Path $state)) { throw "패키지가 없습니다. 먼저 deploy\intune-isekai3d\build.ps1 을 돌려 주세요." }
$last = Get-Content $state -Raw -Encoding UTF8 | ConvertFrom-Json

& (Join-Path $root 'deploy\intune\publish-intune.ps1') `
    -DisplayName '스페이스기전 학생 · 이세계 사회인 캐릭터' -Version $last.version -Package $last.package `
    -DetectionKey 'SpacekijunIsekai3D' `
    -Description '스페이스기전 학생 독의 «고등학생이었던 내가 이세계에서는 사회인?» 가 쓰는 VRoid 캐릭터. 학생판과 따로 깔려, 학생판을 업데이트해도 다시 받지 않는다.' `
    -DeviceCode:$DeviceCode -DryRun:$DryRun -Yes:$Yes
