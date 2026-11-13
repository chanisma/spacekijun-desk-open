<#
  install.ps1 · uninstall.ps1 을 **관리자 권한 없이** 시험한다. Program Files·HKLM 대신 임시 폴더와
  HKCU\Software\SpacekijunStudentIntuneTest 아래에 설치했다가 지우고, 남은 것이 없는지 본다.

    powershell -ExecutionPolicy Bypass -File deploy\intune\test-install.ps1 -Package dist\intune\stage-test
  -Package 폴더에는 SpacekijunStudent.exe · install.ps1 · uninstall.ps1 · version.txt 가 있어야 한다.
#>
param([Parameter(Mandatory = $true)][string]$Package)

$ErrorActionPreference = 'Stop'
$room = Join-Path $env:TEMP "spacekijun-intune-test-$PID"
$key  = 'HKCU:\Software\SpacekijunStudentIntuneTest'
$opts = @{ InstallDir = (Join-Path $room 'Program Files\Spacekijun Student'); MachineKey = $key
           StartMenu = (Join-Path $room 'Start Menu'); LogDir = (Join-Path $room 'log') }
$fail = @()
function Expect($ok, $what) { if ($ok) { Write-Output "  ok    $what" } else { Write-Output "  FAIL  $what"; $script:fail += $what } }

try {
    $version = (Get-Content (Join-Path $Package 'version.txt') -Raw).Trim()
    Write-Output "설치 시험 ($version)"
    & (Join-Path $Package 'install.ps1') @opts
    Expect ($LASTEXITCODE -eq 0) '설치 스크립트가 0 으로 끝남'
    $exe = Join-Path $opts.InstallDir 'SpacekijunStudent.exe'
    Expect (Test-Path $exe) '실행 파일이 설치 폴더에 있음'
    Expect (Test-Path (Join-Path $opts.StartMenu '스페이스기전 학생.lnk')) '시작 메뉴 바로가기'
    $run = (Get-ItemProperty "$key\Microsoft\Windows\CurrentVersion\Run" -Name SpacekijunStudent -ErrorAction SilentlyContinue).SpacekijunStudent
    Expect ($run -eq "`"$exe`" --autostart") '로그인 시 자동 실행 등록'
    Expect ((Get-ItemProperty "$key\SpacekijunStudent").Version -eq $version) '탐지 규칙 표식 (Version)'

    Write-Output '다시 설치 (새 판으로 바꾸는 경우)'
    & (Join-Path $Package 'install.ps1') @opts
    Expect ($LASTEXITCODE -eq 0) '덮어 설치도 0 으로 끝남'

    Write-Output '제거 시험'
    & (Join-Path $Package 'uninstall.ps1') @opts
    Expect ($LASTEXITCODE -eq 0) '제거 스크립트가 0 으로 끝남'
    Expect (-not (Test-Path $opts.InstallDir)) '설치 폴더가 지워짐'
    Expect (-not (Test-Path (Join-Path $opts.StartMenu '스페이스기전 학생.lnk'))) '바로가기가 지워짐'
    Expect (-not (Get-ItemProperty "$key\Microsoft\Windows\CurrentVersion\Run" -Name SpacekijunStudent -ErrorAction SilentlyContinue)) '자동 실행이 지워짐'
    Expect (-not (Test-Path "$key\SpacekijunStudent")) '표식이 지워짐'
}
finally {
    Remove-Item -Path $key -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $room -Recurse -Force -ErrorAction SilentlyContinue
}
if ($fail.Count) { Write-Output "실패 $($fail.Count)건"; exit 1 }
Write-Output '모두 통과'
