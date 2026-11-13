<#
  스페이스기전 학생 — Intune(Win32 앱) 설치 스크립트. Intune 이 SYSTEM 계정으로 돌린다.

    설치 명령: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

  하는 일
    1. 켜져 있는 스페이스기전 학생을 닫는다 (새 판으로 바꿀 때 파일이 잠겨 있지 않게)
    2. 실행 파일을 Program Files 에 놓는다 — 학생은 바꾸거나 지울 수 없다
    3. 시작 메뉴 바로가기 (모든 사용자)
    4. Windows 로그인 시 자동 실행 (모든 사용자, HKLM Run) — 앱 설정의 스위치는 '학교에서 관리' 로 잠긴다
    5. 탐지 규칙용 표식: HKLM\SOFTWARE\SpacekijunStudent  Version = (version.txt)

  학생 각자의 기록(계정·캡처·클립보드)은 %LOCALAPPDATA%\SpacekijunStudent 에 따로 쌓이며 건드리지 않는다.
  인자는 시험할 때만 바꾼다 (deploy/intune/test-install.ps1).
#>
param(
    [string]$InstallDir = '',
    [string]$MachineKey = 'HKLM:\SOFTWARE',
    [string]$StartMenu = '',
    [string]$LogDir = ''
)

# Intune 이 32비트 PowerShell 로 부르면 Program Files·레지스트리가 32비트 자리로 돌아간다. 64비트로 다시 돈다.
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
if (-not $InstallDir) { $InstallDir = Join-Path $env:ProgramFiles 'Spacekijun Student' }
if (-not $StartMenu)  { $StartMenu = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs' }
if (-not $LogDir)     { $LogDir = Join-Path $env:ProgramData 'SpacekijunStudent' }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir 'intune-install.log') -Append | Out-Null
try {
    $source  = Join-Path $PSScriptRoot 'SpacekijunStudent.exe'
    $version = (Get-Content -Path (Join-Path $PSScriptRoot 'version.txt') -Raw).Trim()
    $exe     = Join-Path $InstallDir 'SpacekijunStudent.exe'
    Write-Output "스페이스기전 학생 $version 설치 → $InstallDir"

    # 1. 켜져 있으면 닫는다 (한 파일 실행 파일이라 같은 이름의 프로세스가 둘 뜬다)
    $running = Get-Process -Name 'SpacekijunStudent' -ErrorAction SilentlyContinue
    if ($running) {
        $running | Stop-Process -Force
        Start-Sleep -Seconds 2
    }

    # 2. 실행 파일
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item -Path $source -Destination $exe -Force
    if ((Get-FileHash $source).Hash -ne (Get-FileHash $exe).Hash) { throw '실행 파일 복사가 끝나지 않았습니다.' }

    # 3. 시작 메뉴 바로가기
    New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $StartMenu '스페이스기전 학생.lnk'))
    $link.TargetPath = $exe
    $link.WorkingDirectory = $InstallDir
    $link.Description = '스페이스기전 학생 — 바로가기·시간표·캡처 독'
    $link.Save()

    # 4. 로그인 시 자동 실행 (--autostart: 이미 켜져 있어도 안내 창을 띄우지 않는다)
    $run = Join-Path $MachineKey 'Microsoft\Windows\CurrentVersion\Run'
    if (-not (Test-Path $run)) { New-Item -Path $run -Force | Out-Null }
    Set-ItemProperty -Path $run -Name 'SpacekijunStudent' -Value "`"$exe`" --autostart"

    # 5. 탐지 규칙용 표식
    $mark = Join-Path $MachineKey 'SpacekijunStudent'
    if (-not (Test-Path $mark)) { New-Item -Path $mark -Force | Out-Null }
    Set-ItemProperty -Path $mark -Name 'Version' -Value $version
    Set-ItemProperty -Path $mark -Name 'InstallDir' -Value $InstallDir

    Write-Output '설치를 마쳤습니다.'
    exit 0
}
catch {
    Write-Output "설치 실패: $_"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
