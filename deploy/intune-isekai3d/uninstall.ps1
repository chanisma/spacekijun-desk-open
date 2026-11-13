<#
  스페이스기전 학생 · 이세계 사회인 캐릭터 — Intune(Win32 앱) 제거 스크립트 (2026-10-19 요청). Intune 이 SYSTEM 계정으로 돌린다.

    제거 명령: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1

  install.ps1 이 만든 것(캐릭터 폴더·표식)만 지운다. 학생판과 게임 저장은 남는다 — 게임은 도형 캐릭터로 돈다.
#>
param(
    [string]$InstallDir = '',
    [string]$MachineKey = 'HKLM:\SOFTWARE',
    [string]$LogDir = ''
)

if ($env:PROCESSOR_ARCHITEW6432 -eq 'AMD64') {
    $ps = Join-Path $env:WINDIR 'sysnative\WindowsPowerShell\v1.0\powershell.exe'
    $pass = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
    foreach ($name in 'InstallDir', 'MachineKey', 'LogDir') {
        $value = Get-Variable -Name $name -ValueOnly
        if ($value) { $pass += @("-$name", $value) }
    }
    & $ps @pass
    exit $LASTEXITCODE
}

$ErrorActionPreference = 'Stop'
$mark = Join-Path $MachineKey 'SpacekijunIsekai3D'
if (-not $InstallDir) { $InstallDir = Join-Path $env:ProgramFiles 'Spacekijun Isekai3D' }
if (-not $LogDir)     { $LogDir = Join-Path $env:ProgramData 'SpacekijunStudent' }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir 'intune-isekai3d.log') -Append | Out-Null
try {
    Write-Output "이세계 사회인 캐릭터 제거 ← $InstallDir"
    Remove-Item -Path $mark -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $InstallDir) { throw "폴더를 지우지 못했습니다: $InstallDir" }
    Write-Output '제거를 마쳤습니다.'
    exit 0
}
catch {
    Write-Output "제거 실패: $_"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
