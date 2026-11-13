<#
  스페이스기전 학생 · 이세계 사회인 캐릭터 — 학생이 직접 까는 설치 (2026-10-25 요청). 구글 드라이브에서 받은 zip 안의
  «설치하기.cmd» 가 이 스크립트를 부른다. 관리자 권한 없이 이 사용자에게만 깐다.

  Intune 팩(install.ps1)이 늦게 오는 PC 에서 새 게임이 새 캐릭터를 바로 쓰게 하려는 것이다.
    1. 이 PC 에 Intune 이 깐 팩이 같은 형식·같거나 새 판이면 깔지 않는다 (같은 캐릭터를 두 번 두지 않게).
    2. %LOCALAPPDATA%\Spacekijun Isekai3D\pack 에 맞춘다 (robocopy /MIR — 새 판에 없는 옛 파일은 지운다).
    3. 표식: HKCU\Software\SpacekijunIsekai3D  PackDir, Version — 학생판의 core/isekai3d_server.py 가 읽는다.
  나중에 Intune 이 같은 판이나 새 판을 깔면 install.ps1 이 이 개인 팩을 지운다.
#>
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'pack'
$target = Join-Path $env:LOCALAPPDATA 'Spacekijun Isekai3D\pack'

function Fail($text) {
    Write-Host ''
    Write-Host "설치하지 못했어요: $text" -ForegroundColor Red
    Write-Host '압축을 모두 푼 폴더에서 «설치하기»를 다시 실행해 주세요. 계속 안 되면 선생님께 알려 주세요.'
    exit 1
}

function Version-Of($text) {
    try { return [version](([string]$text -split '\.' | ForEach-Object { [int]$_ }) -join '.') } catch { return [version]'0.0' }
}

$infoPath = Join-Path $source 'pack.json'
if (-not (Test-Path $infoPath)) { Fail '설치할 캐릭터 파일이 없어요 (zip 의 압축을 먼저 풀어 주세요).' }
$info = Get-Content -Path $infoPath -Raw -Encoding UTF8 | ConvertFrom-Json
$mine = Version-Of $info.version
Write-Host "이세계 사회인 3D 캐릭터 팩 $($info.version) (캐릭터 $($info.files)개)"

# 1. Intune 이 이미 깐 팩
try {
    $machineDir = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\SpacekijunIsekai3D' -ErrorAction Stop).PackDir
} catch { $machineDir = $null }
if ($machineDir -and (Test-Path (Join-Path $machineDir 'pack.json'))) {
    $machine = Get-Content -Path (Join-Path $machineDir 'pack.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$machine.format -eq [int]$info.format -and (Version-Of $machine.version) -ge $mine) {
        Write-Host ''
        Write-Host "이 PC 에는 이미 같은(또는 더 새) 팩 $($machine.version) 이 깔려 있어요. 따로 설치하지 않아도 돼요." -ForegroundColor Green
        exit 0
    }
}

# 2. 캐릭터 파일
$need = [math]::Ceiling((Get-ChildItem $source -File | Measure-Object Length -Sum).Sum / 1MB)
$drive = (Get-Item $env:LOCALAPPDATA).PSDrive
if ($drive.Free -and $drive.Free / 1MB -lt $need + 200) { Fail "디스크 공간이 모자라요 (약 $need MB 필요)." }
Write-Host "설치하는 중… ($need MB, 몇 분 걸릴 수 있어요)"
New-Item -ItemType Directory -Force -Path $target | Out-Null
& robocopy $source $target /MIR /R:2 /W:3 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "파일을 복사하지 못했어요 (robocopy $LASTEXITCODE)." }
$want = @(Get-ChildItem $source -Filter '*.vrm' -File).Count
$have = @(Get-ChildItem $target -Filter '*.vrm' -File).Count
if ($want -ne $have) { Fail "캐릭터 파일 수가 맞지 않아요 ($have / $want)." }

# 3. 표식 — 맨 마지막에 판 번호(다 깔린 뒤에만 쓰이게)
$mark = 'HKCU:\Software\SpacekijunIsekai3D'
if (-not (Test-Path $mark)) { New-Item -Path $mark -Force | Out-Null }
Set-ItemProperty -Path $mark -Name 'PackDir' -Value $target
Set-ItemProperty -Path $mark -Name 'Version' -Value ([string]$info.version)

Write-Host ''
Write-Host "설치를 마쳤어요 (캐릭터 $have 개)." -ForegroundColor Green
Write-Host '이세계 사회인 창을 닫았다가 다시 열거나, 게임 안의 «다시 확인»을 누르면 3D 캐릭터로 보여요.'
Write-Host '받은 zip 파일과 압축을 푼 폴더는 이제 지워도 돼요.'
exit 0
