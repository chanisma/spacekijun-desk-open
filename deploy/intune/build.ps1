<#
  스페이스기전 학생 — Intune 배포 패키지(.intunewin) 만들기. 개발 PC 에서 돌린다.

    powershell -ExecutionPolicy Bypass -File deploy\intune\build.ps1            # 실행 파일부터 새로 만든다
    powershell -ExecutionPolicy Bypass -File deploy\intune\build.ps1 -SkipExe   # dist\SpacekijunStudent.exe 를 그대로 쓴다

  나오는 것: dist\intune\<판>\SpacekijunStudent-<판>.intunewin 와 Intune 에 넣을 값을 적은 배포안내.txt
  판 번호는 app\core\edition.py 의 STUDENT_VERSION 이다. 새로 내보낼 때마다 올린다 — Intune 이 그 값으로
  학생 PC 의 옛 판을 알아보고 다시 설치한다.
#>
param([switch]$SkipExe)

$ErrorActionPreference = 'Stop'
$root   = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$here   = $PSScriptRoot
$exe    = Join-Path $root 'dist\SpacekijunStudent.exe'
# PyInstaller 가 깔린 파이썬을 찾는다 (SPACEKIJUN_PYTHON 으로 정할 수도 있다)
$python = $env:SPACEKIJUN_PYTHON
if (-not $python -and -not $SkipExe) {
    foreach ($candidate in @('python', (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))) {
        try { & $candidate -m PyInstaller --version *> $null } catch { continue }
        if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
    }
    if (-not $python) { throw 'PyInstaller 가 깔린 파이썬을 찾지 못했습니다. SPACEKIJUN_PYTHON 에 경로를 넣어 주세요.' }
}

$edition = Get-Content -Path (Join-Path $root 'app\core\edition.py') -Raw -Encoding UTF8
if ($edition -notmatch "STUDENT_VERSION\s*=\s*'([0-9.]+)'") { throw 'edition.py 에서 STUDENT_VERSION 을 찾지 못했습니다.' }
$version = $Matches[1]
Write-Output "== 스페이스기전 학생 $version 배포 패키지 =="

# 1. 실행 파일
if (-not $SkipExe) {
    Write-Output '[1/4] 실행 파일 만드는 중 (몇 분 걸립니다)'
    Push-Location $root
    try {
        # 이세계 사회인 게임 파일(약 5MB)을 isekai3d 저장소에서 빌드해 넣는다 — 캐릭터는 deploy\intune-isekai3d 의 따로 앱 (2026-10-19)
        & $python deploy\isekai3d\sync.py
        if ($LASTEXITCODE -ne 0) { throw '이세계 사회인 게임 파일을 넣지 못했습니다 (deploy\isekai3d\sync.py).' }
        & $python -m PyInstaller --noconfirm --clean SpacekijunStudent.spec
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 가 실패했습니다.' }
    } finally { Pop-Location }
} else {
    Write-Output '[1/4] 실행 파일은 있는 것을 씁니다'
}
if (-not (Test-Path $exe)) { throw "실행 파일이 없습니다: $exe" }

# 2. 실행 파일 자체 점검 — 창을 띄우지 않고 번들이 제대로 묶였는지 본다
Write-Output '[2/4] 실행 파일 자체 점검'
$report = Join-Path $env:TEMP "spacekijun-student-selftest-$PID.json"
Start-Process -FilePath $exe -ArgumentList @('--self-test', $report) -Wait -WindowStyle Hidden
$check = Get-Content -Path $report -Raw -Encoding UTF8 | ConvertFrom-Json
Remove-Item $report -Force -ErrorAction SilentlyContinue
if (-not $check.ok) { throw "자체 점검 실패:`n$($check.error)" }
$check.checks | ForEach-Object { Write-Output "    ok  $_" }

# 3. 포장 도구 (Microsoft Win32 Content Prep Tool) — 없으면 Microsoft 저장소에서 받는다
$tool = Join-Path $here 'tools\IntuneWinAppUtil.exe'
if (-not (Test-Path $tool)) {
    Write-Output '[3/4] 포장 도구 받는 중 (github.com/microsoft/Microsoft-Win32-Content-Prep-Tool)'
    New-Item -ItemType Directory -Force -Path (Split-Path $tool) | Out-Null
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -OutFile $tool `
        -Uri 'https://raw.githubusercontent.com/microsoft/Microsoft-Win32-Content-Prep-Tool/master/IntuneWinAppUtil.exe'
    $sign = Get-AuthenticodeSignature $tool
    if ($sign.Status -ne 'Valid' -or $sign.SignerCertificate.Subject -notmatch 'Microsoft') {
        Remove-Item $tool -Force
        throw '받은 포장 도구의 Microsoft 서명을 확인하지 못했습니다.'
    }
} else {
    Write-Output '[3/4] 포장 도구 있음'
}

# 4. 패키지 — 실행 파일·설치/제거 스크립트·판 번호를 한 폴더에 모아 포장한다
Write-Output '[4/4] 패키지 만드는 중'
$stage = Join-Path $root 'dist\intune\stage'
$out   = Join-Path $root "dist\intune\$version"
Remove-Item -Path $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stage, $out | Out-Null
Copy-Item $exe, (Join-Path $here 'install.ps1'), (Join-Path $here 'uninstall.ps1') -Destination $stage
Set-Content -Path (Join-Path $stage 'version.txt') -Value $version -Encoding ASCII
& $tool -c $stage -s 'install.ps1' -o $out -q | Out-Null
$made = Join-Path $out 'install.intunewin'
if (-not (Test-Path $made)) { throw '.intunewin 을 만들지 못했습니다.' }
$package = Join-Path $out "SpacekijunStudent-$version.intunewin"
Move-Item -Path $made -Destination $package -Force
Remove-Item -Path $stage -Recurse -Force

$guide = @"
스페이스기전 학생 $version — Intune 배포 안내
==========================================

패키지: $package

Intune 관리 센터 (https://intune.microsoft.com)
  앱 > Windows > 추가 > 앱 유형 'Windows 앱(Win32)' > 위 .intunewin 선택

[앱 정보]
  이름        스페이스기전 데스크톱   (Intune 에 이미 있는 학생판 앱 — 새로 만들지 말고 이 앱의 패키지를 바꾼다)
  게시자      스페이스기전
  앱 버전     $version

[프로그램]
  설치 명령        powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
  제거 명령        powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
  설치 동작        시스템
  장치 다시 시작   특정 작업 없음

[요구 사항]
  운영 체제 아키텍처   64비트
  최소 운영 체제       Windows 10 22H2 (Windows 10 PC 가 있으면 WebView2 런타임도 배포해 종속성으로 거세요)

[검색 규칙]  규칙 형식: 수동으로 검색 규칙 구성 > 추가 > 레지스트리
  키 경로      HKEY_LOCAL_MACHINE\SOFTWARE\SpacekijunStudent
  값 이름      Version
  검색 방법    문자열 비교 > 같음 > $version
  32비트 앱과 연결   아니요

[할당]
  필수 > 학생 기기 그룹 (먼저 2~3대 시험 그룹으로)

설치 기록: 학생 PC 의 C:\ProgramData\SpacekijunStudent\intune-install.log

새 판 내보내기
  1) app\core\edition.py 의 STUDENT_VERSION 을 올린다
  2) deploy\intune\build.ps1 을 다시 돌린다
  3) deploy\intune\publish-intune.ps1 로 올린다 — 앱 패키지 파일을 바꾸고 앱 버전·검색 규칙 값을 새 판 번호로 고친다
     (손으로 할 땐 Intune 의 같은 앱에서 '앱 패키지 파일'을 먼저 바꾸고, 그다음 검색 규칙 값을 고친다)
"@
Set-Content -Path (Join-Path $out '배포안내.txt') -Value $guide -Encoding UTF8
Write-Output ''
Write-Output "완료: $package"
Write-Output "안내: $(Join-Path $out '배포안내.txt')"
