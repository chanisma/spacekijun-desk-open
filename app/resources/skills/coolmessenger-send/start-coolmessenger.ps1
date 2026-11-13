<#
쿨메신저를 원격 디버깅 포트(기본 9222)로 실행한다 — 쪽지 본문을 쓰는 CDP 연결에 필요하다.

    .\start-coolmessenger.ps1            # 포트가 이미 열려 있으면 확인만 하고 끝낸다
    .\start-coolmessenger.ps1 -Restart   # 포트 없이 떠 있는 앱을 종료하고 포트를 켜서 다시 띄운다
    .\start-coolmessenger.ps1 -Exe "D:\CoolMessenger\CoolMessenger.exe"   # 설치 경로가 다를 때

앱을 종료했다 켜므로 **작성 중인 쪽지창이 있으면 사라진다** — 그래서 -Restart 를 줘야만 재시작한다.
자동 로그인이 켜져 있으면 로그인 창 없이 다시 접속된다. 꺼져 있으면 로그인 창이 뜨니 직접 로그인한다.
#>
param(
    [int]$Port = 9222,
    [string]$Exe,
    [switch]$Restart
)

$ErrorActionPreference = 'Stop'

function Test-Port([int]$p) {
    try { $null = Invoke-RestMethod "http://127.0.0.1:$p/json/version" -TimeoutSec 3; $true } catch { $false }
}

if (Test-Port $Port) { Write-Host "✅ CDP 포트 $Port 가 이미 열려 있습니다."; return }

$running = Get-Process -Name CoolMessenger -ErrorAction SilentlyContinue
if ($running -and -not $Restart) {
    Write-Warning "쿨메신저가 포트 $Port 없이 실행 중입니다. 재시작하려면 -Restart 를 주세요 (작성 중인 쪽지창은 사라집니다)."
    return
}

if (-not $Exe) {
    $Exe = @(
        ($running | Select-Object -First 1).Path,
        "${env:ProgramFiles(x86)}\CoolMessenger Gentoo\CoolMessenger.exe",
        "$env:ProgramFiles\CoolMessenger Gentoo\CoolMessenger.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $Exe -or -not (Test-Path $Exe)) { throw '쿨메신저 실행 파일을 찾지 못했습니다. -Exe 로 경로를 지정하세요.' }

if ($running) {
    Stop-Process -Name CoolMessenger -Force
    Get-Process CoolSubProcess -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
}

Start-Process $Exe -ArgumentList "--remote-debugging-port=$Port"
Write-Host "쿨메신저를 시작했습니다 (포트 $Port) — 연결을 기다립니다..."

for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Port $Port) { Write-Host "✅ CDP 포트 $Port 열림. 로그인 창이 보이면 직접 로그인하세요."; return }
}
throw "40초 안에 포트 $Port 가 열리지 않았습니다."
