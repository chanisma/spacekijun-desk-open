<#
  스페이스기전 학생 · 이세계 사회인 캐릭터 — Intune 배포 패키지(.intunewin) 만들기 (2026-10-19 요청). 개발 PC 에서 돌린다.

    powershell -ExecutionPolicy Bypass -File deploy\intune-isekai3d\build.ps1

  학생판 실행 파일과 따로인 Win32 앱이다. 학생판을 업데이트해도 캐릭터(약 500MB)는 다시 받지 않고,
  캐릭터가 바뀔 때만 이 앱의 새 판을 올린다. Intune 은 바뀐 파일만 받지 못하고 패키지를 통째로 받는다.

  캐릭터: isekai3d 저장소(SPACEKIJUN_ISEKAI3D, 없으면 %USERPROFILE%\orca\projects\isekai3d)의 models\*.vrm.
          VRoid 샘플(-sample_)은 자체 라이선스가 수정·재배포를 막아 넣지 않는다.
  판 번호: 캐릭터 파일 내용이 지난번과 같으면 그 판 그대로(새 패키지를 만들지 않는다), 다르면 오늘 날짜·시각.
  팩 형식: isekai3d package.json 의 modelsFormat (2026-10-25부터 2 — 기본 몸 + 옷만 든 파일 + 직업복). 팩 안 pack.json 에 적는다.
  나오는 것: dist\intune-isekai3d\<판>\
    SpacekijunIsekai3D-<판>.intunewin   Intune 앱 (기기 전체, Program Files)
    이세계사회인-3D캐릭터팩-<판>.zip   구글 드라이브에 올리는 학생용 설치 파일 (그 사용자에게만, 관리자 권한 없이 — install-user.ps1)
    배포안내.txt
#>
$ErrorActionPreference = 'Stop'
$root  = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$here  = $PSScriptRoot
$repo  = if ($env:SPACEKIJUN_ISEKAI3D) { $env:SPACEKIJUN_ISEKAI3D } else { Join-Path $env:USERPROFILE 'orca\projects\isekai3d' }
$dist  = Join-Path $root 'dist\intune-isekai3d'
$state = Join-Path $dist 'latest.json'

$models = @(Get-ChildItem -Path (Join-Path $repo 'models') -Filter '*.vrm' -File | Where-Object { $_.Name -notmatch '-sample_' } | Sort-Object Name)
if (-not $models.Count) { throw "캐릭터 파일이 없습니다: $repo\models (SPACEKIJUN_ISEKAI3D 를 확인해 주세요)" }
$format = [int]((Get-Content -Path (Join-Path $repo 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json).modelsFormat)
if (-not $format) { $format = 1 }
Write-Output "== 이세계 사회인 캐릭터 팩 (형식 $format): $($models.Count)개, $([math]::Round(($models | Measure-Object Length -Sum).Sum / 1MB)) MB =="

# 1. 내용 지문 — 이름·크기·SHA-256 을 모두 이어 한 번 더 해시한다
Write-Output '[1/4] 캐릭터 파일 지문 계산'
$lines = $models | ForEach-Object { "$($_.Name) $($_.Length) $((Get-FileHash $_.FullName -Algorithm SHA256).Hash)" }
$bytes = [Text.Encoding]::UTF8.GetBytes((@("format $format") + $lines) -join "`n")
$print = -join ([Security.Cryptography.SHA256]::Create().ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') })
$last  = if (Test-Path $state) { Get-Content $state -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
if ($last -and $last.fingerprint -eq $print -and (Test-Path $last.package) -and $last.zip -and (Test-Path $last.zip)) {
    Write-Output "캐릭터가 지난번($($last.version))과 같습니다 — 새 패키지를 만들지 않습니다: $($last.package)"
    return
}
$version = Get-Date -Format 'yyyy.M.d.HHmm'

# 2. 포장 도구 (학생판과 같은 것)
$tool = Join-Path $root 'deploy\intune\tools\IntuneWinAppUtil.exe'
if (-not (Test-Path $tool)) { throw "포장 도구가 없습니다: $tool`n먼저 deploy\intune\build.ps1 을 한 번 돌려 주세요 (도구를 받아 둡니다)." }

# 3. 패키지
Write-Output "[2/4] Intune 패키지 만드는 중 ($version, 몇 분 걸립니다)"
$stage = Join-Path $dist 'stage'
$out   = Join-Path $dist $version
Remove-Item -Path $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'pack'), $out | Out-Null
$models | Copy-Item -Destination (Join-Path $stage 'pack')
# 팩의 표식 — 학생판 서버가 이것으로 게임이 읽는 형식인지 본다 (BOM 없이: 파이썬 json 이 읽는다)
$packInfo = @{ format = $format; version = $version; files = $models.Count } | ConvertTo-Json -Compress
[IO.File]::WriteAllText((Join-Path $stage 'pack\pack.json'), $packInfo, (New-Object Text.UTF8Encoding $false))
Copy-Item (Join-Path $here 'install.ps1'), (Join-Path $here 'uninstall.ps1') -Destination $stage
Set-Content -Path (Join-Path $stage 'version.txt') -Value $version -Encoding ASCII
& $tool -c $stage -s 'install.ps1' -o $out -q | Out-Null
$made = Join-Path $out 'install.intunewin'
if (-not (Test-Path $made)) { throw '.intunewin 을 만들지 못했습니다.' }
$package = Join-Path $out "SpacekijunIsekai3D-$version.intunewin"
Move-Item -Path $made -Destination $package -Force

# 4. 구글 드라이브용 — 학생이 받아 압축을 풀고 «설치하기»를 실행한다 (같은 캐릭터·같은 pack.json)
Write-Output '[3/4] 학생용 설치 파일(zip) 만드는 중'
$userStage = Join-Path $dist 'stage-user'
Remove-Item -Path $userStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $userStage | Out-Null
Move-Item -Path (Join-Path $stage 'pack') -Destination $userStage
Copy-Item (Join-Path $here 'install-user.ps1'), (Join-Path $here '설치하기.cmd') -Destination $userStage
$readme = @"
이세계 사회인 3D 캐릭터 팩 $version
================================

스페이스기전 학생 독의 «고등학생이었던 내가 이세계에서는 사회인?» 에 쓰는 3D 캐릭터예요.
학교 PC 에는 자동으로 설치되는데, 아직 안 왔으면 이 파일로 직접 설치할 수 있어요.

1. 이 zip 파일을 마우스 오른쪽 단추로 눌러 «압축 풀기»(모두 압축 풀기)를 해요.
2. 압축을 푼 폴더에서 «설치하기» 를 더블클릭해요.
   «Windows 의 PC 보호» 창이 뜨면 «추가 정보» → «실행» 을 눌러요.
3. «설치를 마쳤어요» 가 나오면, 게임 창을 닫았다가 다시 열거나 게임 안의 «다시 확인» 을 눌러요.

- 관리자 권한은 필요 없어요. 이 Windows 사용자에게만 설치돼요 (%LOCALAPPDATA%\Spacekijun Isekai3D).
- 예전에 직접 설치한 팩은 새 판으로 바뀌고, 필요 없어진 파일은 지워져요.
- 나중에 학교에서 같은 판이 자동으로 설치되면, 직접 설치한 팩은 자동으로 지워져요.
- 설치가 끝나면 받은 zip 파일과 압축을 푼 폴더는 지워도 돼요.
"@
Set-Content -Path (Join-Path $userStage '읽어주세요.txt') -Value $readme -Encoding UTF8
$zip = Join-Path $out "이세계사회인-3D캐릭터팩-$version.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($userStage, $zip, [IO.Compression.CompressionLevel]::Optimal, $false, [Text.Encoding]::UTF8)
Remove-Item -Path $stage, $userStage -Recurse -Force
@{ version = $version; format = $format; fingerprint = $print; package = $package; zip = $zip; files = $models.Count } | ConvertTo-Json | Set-Content -Path $state -Encoding UTF8

Write-Output '[4/4] 배포 안내'
$guide = @"
스페이스기전 학생 · 이세계 사회인 캐릭터 $version — Intune 배포 안내
==========================================================

패키지: $package  (캐릭터 $($models.Count)개, 팩 형식 $format)
구글 드라이브: $zip
  스페이스기전 «이세계에서는 사회인 — 3D 모델 설치 파일» 카드의 링크가 가리키는 드라이브 파일을 이 zip 으로 바꾼다
  (드라이브 «버전 관리 → 새 버전 업로드»면 링크가 그대로다). 게임도 이 링크를 연다.

학생판(스페이스기전 학생)과 따로인 Win32 앱이다. 학생판 독의 «고등학생이었던 내가 이세계에서는 사회인?» 가 이 캐릭터를 쓴다.
없어도 게임은 열리고, 캐릭터는 도형으로 보인다.

[앱 정보]
  이름        스페이스기전 학생 · 이세계 사회인 캐릭터
  게시자      스페이스기전
  앱 버전     $version

[프로그램]
  설치 명령        powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
  제거 명령        powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
  설치 동작        시스템
  장치 다시 시작   특정 작업 없음

[요구 사항]
  운영 체제 아키텍처   64비트,  최소 운영 체제   Windows 10 22H2
  디스크 여유 공간     1 GB 이상

[검색 규칙]  수동으로 검색 규칙 구성 > 레지스트리
  키 경로      HKEY_LOCAL_MACHINE\SOFTWARE\SpacekijunIsekai3D
  값 이름      Version
  검색 방법    문자열 비교 > 같음 > $version

[할당]
  필수 > 학생판과 같은 학생 기기 그룹 (먼저 시험 그룹으로). 받는 양이 커서 수업 시간을 피해 거는 것이 좋다.

설치 기록: 학생 PC 의 C:\ProgramData\SpacekijunStudent\intune-isekai3d.log
설치 자리: C:\Program Files\Spacekijun Isekai3D\pack (형식 1 의 models 폴더와 학생 개인 팩은 설치할 때 지운다)

올리기: powershell -ExecutionPolicy Bypass -File deploy\intune-isekai3d\publish.ps1
"@
Set-Content -Path (Join-Path $out '배포안내.txt') -Value $guide -Encoding UTF8
Write-Output ''
Write-Output "완료: $package"
