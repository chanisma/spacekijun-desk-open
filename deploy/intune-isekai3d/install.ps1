<#
  스페이스기전 학생 · 이세계 사회인 캐릭터 — Intune(Win32 앱) 설치 스크립트 (2026-10-19 요청). Intune 이 SYSTEM 계정으로 돌린다.

    설치 명령: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

  하는 일 (팩 형식 2, 2026-10-25 — 기본 몸 + 옷만 든 파일 + 직업복)
    1. 캐릭터 파일과 pack.json 을 Program Files\Spacekijun Isekai3D\pack 에 맞춘다 (robocopy /MIR — 새 판에 없는 옛 파일은 지운다)
    2. 표식: HKLM\SOFTWARE\SpacekijunIsekai3D  PackDir = 위 폴더, Version = (version.txt)
       학생판의 core/isekai3d_server.py 가 게임이 읽는 형식(pack.json 의 format)의 팩만 내준다.
    3. 이제 필요 없는 것을 지운다
       - 형식 1 팩(Program Files\Spacekijun Isekai3D\models)과 그 표식 ModelsDir. 형식 1 만 읽는 옛 학생판은
         ModelsDir 을 읽으니, 지우면 옛 학생판은 캐릭터 없이(도형으로) 돌다가 학생판이 업데이트되면 새 팩을 쓴다.
         (옛 학생판에 형식 2 파일을 주면 옷만 보이는 캐릭터가 된다 — 그래서 새 팩은 다른 폴더·다른 표식이다.)
       - 학생이 구글 드라이브에서 받아 직접 깐 팩(사용자마다 %LOCALAPPDATA%\Spacekijun Isekai3D\pack) 가운데
         이 판보다 새 판이 아닌 것 — 같은 캐릭터를 두 번 갖고 있지 않게.

  학생판과 다른 폴더라 학생판을 지우거나 새로 깔아도 캐릭터는 남는다.
  게임 저장(학생 프로필의 localStorage)은 건드리지 않는다.
#>
param(
    [string]$InstallDir = '',
    [string]$MachineKey = 'HKLM:\SOFTWARE',
    [string]$LogDir = ''
)

# Intune 이 32비트 PowerShell 로 부르면 Program Files·레지스트리가 32비트 자리로 돌아간다. 64비트로 다시 돈다.
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
if (-not $InstallDir) { $InstallDir = Join-Path $env:ProgramFiles 'Spacekijun Isekai3D' }
if (-not $LogDir)     { $LogDir = Join-Path $env:ProgramData 'SpacekijunStudent' }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir 'intune-isekai3d.log') -Append | Out-Null
try {
    $version = (Get-Content -Path (Join-Path $PSScriptRoot 'version.txt') -Raw).Trim()
    $source  = Join-Path $PSScriptRoot 'pack'
    $target  = Join-Path $InstallDir 'pack'
    $format  = [int]((Get-Content -Path (Join-Path $source 'pack.json') -Raw -Encoding UTF8 | ConvertFrom-Json).format)
    Write-Output "이세계 사회인 캐릭터 $version (형식 $format) 설치 → $target"

    # 1. 캐릭터 — 바뀐 파일만 복사하고, 새 판에 없는 파일은 지운다
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    & robocopy $source $target /MIR /R:3 /W:5 /NFL /NDL /NJH /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "캐릭터 파일 복사 실패 (robocopy $LASTEXITCODE)" }
    $want = @(Get-ChildItem $source -Filter '*.vrm' -File).Count
    $have = @(Get-ChildItem $target -Filter '*.vrm' -File).Count
    if ($want -ne $have) { throw "캐릭터 파일 수가 맞지 않습니다 ($have / $want)" }

    # 2. 표식
    $mark = Join-Path $MachineKey 'SpacekijunIsekai3D'
    if (-not (Test-Path $mark)) { New-Item -Path $mark -Force | Out-Null }
    Set-ItemProperty -Path $mark -Name 'PackDir' -Value $target
    Remove-ItemProperty -Path $mark -Name 'ModelsDir' -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $mark -Name 'Version' -Value $version    # 맨 마지막 — 다 깔린 뒤에만 '설치됨'으로 보이게

    # 3. 필요 없어진 것 — 형식 1 팩, 그리고 이 판보다 새 판이 아닌 학생 개인 팩
    $legacy = Join-Path $InstallDir 'models'
    for ($i = 0; $i -lt 3 -and (Test-Path $legacy); $i++) {
        Remove-Item -Path $legacy -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $legacy) { Start-Sleep -Seconds 5 }          # 옛 학생판이 파일 하나를 보내는 중일 수 있다
    }
    if (Test-Path $legacy) { Write-Output "형식 1 팩을 다 지우지 못했습니다 (다음 설치 때 다시): $legacy" }
    $mine = [version](($version -split '\.' | ForEach-Object { [int]$_ }) -join '.')
    foreach ($home_ in Get-ChildItem -Path (Join-Path $env:SystemDrive 'Users') -Directory -ErrorAction SilentlyContinue) {
        $theirs = Join-Path $home_.FullName 'AppData\Local\Spacekijun Isekai3D'
        $info = Join-Path $theirs 'pack\pack.json'
        if (-not (Test-Path $info)) { continue }
        try {
            $pack = Get-Content -Path $info -Raw -Encoding UTF8 | ConvertFrom-Json
            $their = [version](([string]$pack.version -split '\.' | ForEach-Object { [int]$_ }) -join '.')
        } catch { continue }
        if ([int]$pack.format -eq $format -and $their -le $mine) {
            Remove-Item -Path $theirs -Recurse -Force -ErrorAction SilentlyContinue
            Write-Output "개인 팩 정리: $theirs ($($pack.version))"
        }
    }

    Write-Output "설치를 마쳤습니다 (캐릭터 $have 개)."
    exit 0
}
catch {
    Write-Output "설치 실패: $_"
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
