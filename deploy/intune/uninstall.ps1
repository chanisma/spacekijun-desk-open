<#
  스페이스기전 학생 — Intune(Win32 앱) 제거 스크립트. Intune 이 SYSTEM 계정으로 돌린다.

    제거 명령: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1

  install.ps1 이 만든 것(실행 파일·바로가기·자동 실행·표식)을 지운다.
  학생 각자의 기록(%LOCALAPPDATA%\SpacekijunStudent)은 남긴다 — 다시 설치하면 이어서 쓴다.
#>
param(
    [string]$InstallDir = '',
    [string]$MachineKey = 'HKLM:\SOFTWARE',
    [string]$StartMenu = '',
    [string]$LogDir = ''
)

if ($env:PROCESSOR_ARCHITEW6432 -eq 'AMD64') {
    $ps = Join-Path $env:WINDIR 'sysnative\WindowsPowerShell\v1.0\powershell.exe'
    # 빈 인자는 넘기지 않는다 (Windows PowerShell 은 빈 문자열 인자를 빼 버려 다음 이름이 값으로 들어간다)
    $pass = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
    foreach ($name in 'InstallDir', 'MachineKey', 'StartMenu', 'LogDir') {
        $value = Get-Variable -Name $name -ValueOnly
        if ($value) { $pass += @("-$name", $value) }
    }
    & $ps @pass
    exit $LASTEXITCODE
}

$ErrorActionPreference = 'Stop'
$mark = Join-Path $MachineKey 'SpacekijunStudent'
if (-not $InstallDir) {
    $saved = (Get-ItemProperty -Path $mark -Name 'InstallDir' -ErrorAction SilentlyContinue).InstallDir
    $InstallDir = if ($saved) { $saved } else { Join-Path $env:ProgramFiles 'Spacekijun Student' }
}
if (-not $StartMenu) { $StartMenu = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs' }
if (-not $LogDir)    { $LogDir = Join-Path $env:ProgramData 'SpacekijunStudent' }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir 'intune-install.log') -Append | Out-Null
try {
    Write-Output "스페이스기전 학생 제거 ← $InstallDir"
    Get-Process -Name 'SpacekijunStudent' -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2

    $run = Join-Path $MachineKey 'Microsoft\Windows\CurrentVersion\Run'
    Remove-ItemProperty -Path $run -Name 'SpacekijunStudent' -ErrorAction SilentlyContinue
    Remove-Item -Path (Join-Path $StartMenu '스페이스기전 학생.lnk') -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $mark -Recurse -Force -ErrorAction SilentlyContinue

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
