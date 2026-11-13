<#
  스페이스기전 학생 — build.ps1 로 만든 .intunewin 을 Intune 에 올리기. 개발 PC 에서 build.ps1 다음에 돌린다.

    powershell -ExecutionPolicy Bypass -File deploy\intune\publish-intune.ps1 -DryRun   # 로그인해 지금 상태와 할 일만 보인다
    powershell -ExecutionPolicy Bypass -File deploy\intune\publish-intune.ps1           # 올린다 (올리기 전에 한 번 묻는다)

  로그인은 브라우저 창에서 Intune 관리자 계정으로 직접 한다 — 스크립트는 계정·암호를 다루지 않는다.
  Intune 에 같은 이름의 앱이 있으면 앱 패키지 파일을 바꾸고 → 앱 버전·검색 규칙을 새 판으로 고친다 (할당은 그대로).
  순서가 중요하다: 검색 규칙을 먼저 바꾸면 학생 PC 가 옛 패키지를 받아 깔고 '검색 실패'를 되풀이한다.
  없으면 배포안내.txt 와 같은 값으로 새로 만든다 — 할당은 Intune 관리 센터에서 직접 건다 (처음엔 시험 그룹부터).

  처음 한 번 준비 — Entra 관리 센터 (https://entra.microsoft.com) > 앱 등록 > 새 등록
    1) 이름은 아무거나 (예: 스페이스기전 Intune 올리기), 지원되는 계정 유형 '이 조직 디렉터리의 계정만'
    2) 리디렉션 URI: '퍼블릭 클라이언트/네이티브(모바일 및 데스크톱)' 에 http://localhost
    3) API 사용 권한 > Microsoft Graph > 위임된 권한 > DeviceManagementApps.ReadWrite.All > 관리자 동의 허용
    4) 개요의 '디렉터리(테넌트) ID' 와 '애플리케이션(클라이언트) ID' 를 환경 변수로 넣어 둔다 (비밀 값이 아니다)
         setx SPACEKIJUN_INTUNE_TENANT <테넌트 ID>
         setx SPACEKIJUN_INTUNE_CLIENT <클라이언트 ID>
  → 2026-10-20 준비 끝: 앱 등록 «스페이스기전 Intune 올리기» (샘플고등학교 테넌트,
     테넌트 00000000-0000-0000-0000-000000000000 · 클라이언트 00000000-0000-0000-0000-000000000000, 관리자 동의함).
     개발 PC 에는 위 두 환경 변수가 들어 있다. 다른 PC 나 원격에서는 같은 두 값을 넣고 -DeviceCode 로 돌리면
     아무 기기의 브라우저에서 코드를 넣어 로그인할 수 있다.
  PowerShell 7(pwsh)로 돈다 — Windows PowerShell 5.1 로 켜면 pwsh 로 다시 연다(5.1 은 한글 앱 이름을 «?» 로 올린다).
  Graph 를 다루는 모듈은 MSEndpointMgr 의 IntuneWin32App (PowerShell Gallery) — 없으면 현재 사용자에게 설치한다.
#>
param(
    [string]$TenantId = $env:SPACEKIJUN_INTUNE_TENANT,
    [string]$ClientId = $env:SPACEKIJUN_INTUNE_CLIENT,
    [string]$Version,                          # 비우면 app\core\edition.py 의 STUDENT_VERSION
    [string]$DisplayName = '스페이스기전 데스크톱',   # Intune 의 학생판 앱 이름(학생 PC 에 깔린 앱, 2026-10-20 확인) — 정확히 같은 것만 고른다
    # 다른 앱(이세계 사회인 캐릭터 팩, deploy\intune-isekai3d\publish.ps1)이 이 스크립트를 그대로 쓸 때 (2026-10-19)
    [string]$Package,                          # 비우면 dist\intune\<판>\SpacekijunStudent-<판>.intunewin
    [string]$DetectionKey = 'SpacekijunStudent',  # 검색 규칙 HKLM\SOFTWARE\<이것> 의 Version
    [string]$Description = '스페이스기전 학생용 데스크 — 독·패널·스페이스기전 바로가기. 자동 실행·자동 업데이트.',
    [switch]$DeviceCode,                       # 브라우저 창을 못 띄울 때 — 다른 기기에서 코드로 로그인
    [switch]$DryRun,                           # 바꾸지 않고 보이기만
    [switch]$Yes                               # 올리기 전에 묻지 않는다
)

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 은 Graph 에 한글을 «?» 로 보낸다(앱 이름·설명이 깨져 올라갔다, 2026-10-20) — PowerShell 7 로 다시 연다.
if ($PSVersionTable.PSVersion.Major -lt 7) {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $pwsh) { throw 'PowerShell 7(pwsh)이 필요합니다 — Windows PowerShell 5.1 은 한글 앱 이름을 ? 로 올립니다. winget install Microsoft.PowerShell' }
    $pass = @()
    foreach ($k in $PSBoundParameters.Keys) {
        $v = $PSBoundParameters[$k]
        if ($v -is [System.Management.Automation.SwitchParameter]) { if ($v.IsPresent) { $pass += "-$k" } } else { $pass += "-$k"; $pass += "$v" }
    }
    & $pwsh.Source -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath @pass
    exit $LASTEXITCODE
}
# IntuneWin32App 1.5.0 은 토큰 만료 시각을 이 PC 의 언어로 글로 바꿨다가 영어로 읽는다 — 한국어 Windows 에서는
# «오후» 를 못 읽어 멈춘다(2026-10-20). 날짜 형식만 영어로 둔다(화면 글은 그대로 한국어).
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo('en-US')
$root   = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ModuleVersion = '1.5.0'                       # 함수 인자를 이 판에 맞춰 썼다 — 올릴 땐 Connect·Set 인자를 다시 확인

if (-not $TenantId -or -not $ClientId) {
    throw '테넌트 ID·클라이언트 ID 가 없습니다. 스크립트 머리말의 «처음 한 번 준비» 를 보고 SPACEKIJUN_INTUNE_TENANT·SPACEKIJUN_INTUNE_CLIENT 를 넣어 주세요.'
}
if (-not $Version) {
    $edition = Get-Content -Path (Join-Path $root 'app\core\edition.py') -Raw -Encoding UTF8
    if ($edition -notmatch "STUDENT_VERSION\s*=\s*'([0-9.]+)'") { throw 'edition.py 에서 STUDENT_VERSION 을 찾지 못했습니다.' }
    $Version = $Matches[1]
}
$package = if ($Package) { $Package } else { Join-Path $root "dist\intune\$Version\SpacekijunStudent-$Version.intunewin" }
if (-not (Test-Path $package)) { throw "패키지가 없습니다: $package`n먼저 deploy\intune\build.ps1 을 돌려 주세요." }
Write-Output "== $DisplayName $Version 을 Intune 에 올리기 =="
Write-Output "패키지: $package ($([math]::Round((Get-Item $package).Length / 1MB, 1)) MB)"

# 1. 모듈
if (-not (Get-Module -ListAvailable -Name IntuneWin32App | Where-Object { $_.Version -eq [version]$ModuleVersion })) {
    Write-Output "[1/4] IntuneWin32App $ModuleVersion 모듈 설치 (PowerShell Gallery, 현재 사용자)"
    Install-Module -Name IntuneWin32App -RequiredVersion $ModuleVersion -Scope CurrentUser -Repository PSGallery -Force -AllowClobber
} else {
    Write-Output "[1/4] IntuneWin32App $ModuleVersion 모듈 있음"
}
Import-Module -Name IntuneWin32App -RequiredVersion $ModuleVersion -Force

# 2. 로그인 — 앱 올리기에 필요한 권한만 청한다
Write-Output '[2/4] Intune 로그인 — 열리는 창에서 관리자 계정으로 로그인해 주세요'
$scopes = @('DeviceManagementApps.ReadWrite.All', 'offline_access')
if ($DeviceCode) {
    # 모듈의 -DeviceCode 는 PowerShell 7 에서 첫 '아직 로그인 전' 응답을 읽다 죽는다 (1.5.0, GetResponseStream —
    # 2026-10-20 확인). 같은 흐름을 여기서 하고, 받은 토큰을 모듈이 쓰는 자리($Global:AccessToken 등)에 넣는다.
    $base = "https://login.microsoftonline.com/$TenantId/oauth2/v2.0"
    $scope = (@($scopes | ForEach-Object { if ($_ -eq 'offline_access') { $_ } else { "https://graph.microsoft.com/$_" } }) -join ' ')
    $code = Invoke-RestMethod -Method Post -Uri "$base/devicecode" -Body @{ client_id = $ClientId; scope = $scope }
    Write-Output "    아무 브라우저(이미 로그인된 창도 됨)에서 $($code.verification_uri) 를 열고 코드 $($code.user_code) 를 넣어 주세요"
    $until = (Get-Date).AddSeconds([int]$code.expires_in)
    $token = $null
    while (-not $token) {
        if ((Get-Date) -gt $until) { throw '코드가 만료되었습니다. 다시 돌려 주세요.' }
        Start-Sleep -Seconds ([int]$code.interval)
        $answer = Invoke-RestMethod -Method Post -Uri "$base/token" -SkipHttpErrorCheck -Body @{
            client_id = $ClientId; grant_type = 'urn:ietf:params:oauth:grant-type:device_code'; device_code = $code.device_code }
        if ($answer.access_token) { $token = $answer }
        elseif ($answer.error -notin @('authorization_pending', 'slow_down')) { throw "로그인 실패: $($answer.error) $($answer.error_description)" }
    }
    $token | Add-Member -Force ExpiresOn ((Get-Date).AddSeconds([int]$token.expires_in).ToUniversalTime())
    $token | Add-Member -Force Scopes ($token.scope -split ' ')
    $token | Add-Member -Force AccessToken $token.access_token
    $token | Add-Member -Force client_id $ClientId
    if ($token.refresh_token) { $token | Add-Member -Force RefreshToken $token.refresh_token }
    $Global:AccessToken = $token
    $Global:AccessTokenTenantID = $TenantId
    $Global:AuthenticationHeader = @{ 'Content-Type' = 'application/json'; Authorization = "Bearer $($token.access_token)"; ExpiresOn = $token.ExpiresOn }
} else {
    Connect-MSIntuneGraph -TenantID $TenantId -ClientID $ClientId -Interactive -Scopes $scopes | Out-Null
}
# 로그인이 안 됐으면 여기서 멈춘다 — 그대로 가면 앱을 못 찾은 것으로 보고 '새로 만들기'로 빠진다
if (-not $Global:AccessToken -or -not $Global:AccessToken.AccessToken) { throw 'Intune 로그인이 되지 않았습니다 — 아무것도 바꾸지 않았습니다.' }
Write-Output '    로그인됨'

# 3. 같은 이름의 앱 찾기 — 둘 이상이면 고르지 않고 멈춘다 (엉뚱한 앱의 패키지를 바꾸면 그 앱의 학생 PC 가 모두 다시 깐다)
Write-Output "[3/4] Intune 에서 '$DisplayName' 찾는 중"
$found = @(Get-IntuneWin32App -DisplayName $DisplayName | Where-Object { $_.displayName -eq $DisplayName })
if ($found.Count -gt 1) {
    $found | ForEach-Object { Write-Output "    $($_.id)  $($_.displayName)  판 $($_.displayVersion)  만든 때 $($_.createdDateTime)" }
    throw "이름이 '$DisplayName' 인 앱이 $($found.Count) 개입니다. Intune 에서 하나만 남기거나 -DisplayName 으로 정확한 이름을 넣어 주세요."
}
$app = $found | Select-Object -First 1

$detection = New-IntuneWin32AppDetectionRuleRegistry -StringComparison `
    -KeyPath "HKEY_LOCAL_MACHINE\SOFTWARE\$DetectionKey" -ValueName 'Version' `
    -StringComparisonOperator 'equal' -StringComparisonValue $Version -Check32BitOn64System $false

if ($app) {
    $rules = @($app.detectionRules | ForEach-Object { "$($_.keyPath)\$($_.valueName) $($_.operator) '$($_.detectionValue)'" }) -join '; '
    Write-Output "    있음: $($app.id)"
    Write-Output "    지금  판 $($app.displayVersion) · 검색 규칙 $rules"
    Write-Output "    바꿀 것  앱 패키지 파일 → $Version, 앱 버전 → $Version, 검색 규칙 값 → '$Version' (할당은 그대로)"
    if ($app.displayVersion -and $app.displayVersion -match '^[0-9.]+$' -and [version]$app.displayVersion -gt [version]$Version) {
        throw "Intune 의 판($($app.displayVersion))이 올리려는 판($Version)보다 새것입니다. 판 번호를 확인해 주세요."
    }
    if ($app.displayVersion -eq $Version) {
        Write-Output "    (Intune 에 이미 $Version 이 있습니다 — 패키지 파일만 다시 올립니다)"
    }
} else {
    Write-Output '    없음 — 새로 만듭니다 (배포안내.txt 와 같은 값). 할당은 만든 뒤 Intune 관리 센터에서 직접 걸어 주세요.'
}

if ($DryRun) {
    Write-Output ''
    Write-Output '-DryRun — 아무것도 바꾸지 않았습니다.'
    return
}
if (-not $Yes) {
    $answer = Read-Host "Intune 에 $Version 을 올릴까요? 할당된 학생 PC 가 다음 동기화 때 새 판을 깝니다 (y/N)"
    if ($answer -notmatch '^(y|yes|예|ㅇ)$') { Write-Output '그만둡니다.'; return }
}

# 4. 올리기
if ($app) {
    $before = $app.committedContentVersion
    Write-Output "[4/4] 앱 패키지 파일 올리는 중 (암호화해 Azure 저장소로 — 몇 분 걸립니다)"
    Update-IntuneWin32AppPackageFile -ID $app.id -FilePath $package
    $now = Get-IntuneWin32App -ID $app.id
    if (-not $now.committedContentVersion -or $now.committedContentVersion -eq $before) {
        throw "패키지 파일이 바뀌지 않았습니다 (콘텐츠 판 $before 그대로). 검색 규칙은 건드리지 않았습니다 — 위 경고를 확인해 주세요."
    }
    Write-Output "    콘텐츠 판 $before → $($now.committedContentVersion)"
    Write-Output '    앱 버전·검색 규칙 고치는 중'
    Set-IntuneWin32App -ID $app.id -AppVersion $Version -DetectionRule $detection | Out-Null
    $id = $app.id
} else {
    Write-Output "[4/4] 새 앱 만들고 패키지 올리는 중 (몇 분 걸립니다)"
    $requirement = New-IntuneWin32AppRequirementRule -Architecture 'x64' -MinimumSupportedWindowsRelease 'W10_22H2'
    $made = Add-IntuneWin32App -FilePath $package -DisplayName $DisplayName `
        -Description $Description `
        -Publisher '스페이스기전' -AppVersion $Version `
        -InstallCommandLine 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1' `
        -UninstallCommandLine 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1' `
        -InstallExperience 'system' -RestartBehavior 'suppress' `
        -DetectionRule $detection -RequirementRule $requirement
    if (-not $made.id) { throw '앱을 만들지 못했습니다 — 위 경고를 확인해 주세요.' }
    $id = $made.id
}

# 확인 — Intune 이 기억한 값을 다시 읽는다
$now = Get-IntuneWin32App -ID $id
$value = @($now.detectionRules | ForEach-Object { $_.detectionValue })
if ($now.displayVersion -ne $Version -or $value -notcontains $Version -or -not $now.committedContentVersion) {
    throw "올린 뒤 확인 실패 — 앱 버전 '$($now.displayVersion)', 검색 규칙 값 '$($value -join ', ')', 콘텐츠 판 '$($now.committedContentVersion)'. Intune 관리 센터에서 확인해 주세요."
}
Write-Output ''
Write-Output "완료: '$DisplayName' $Version (앱 id $id, 콘텐츠 판 $($now.committedContentVersion))"
Write-Output "Intune 관리 센터: https://intune.microsoft.com/#view/Microsoft_Intune_Apps/SettingsMenu/~/0/appId/$id"
if (-not $app) { Write-Output '할당이 아직 없습니다 — 앱 > 속성 > 할당 에서 시험 그룹부터 걸어 주세요.' }
