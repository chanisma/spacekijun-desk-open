<#
알림 문자 문체 프로필 관리 — 처음 쓰는 사용자에게 말투·구조를 인터뷰해서 얻은 지식을 저장해 두고, 이후 모든 문자 초안에 적용한다.

    .\style.ps1 exists          # 프로필이 있으면 yes(종료코드 0), 없으면 no(종료코드 1) → 없으면 인터뷰부터 한다
    .\style.ps1 path            # 프로필 파일 경로
    .\style.ps1 show            # 프로필 내용
    .\style.ps1 init            # 빈 양식(message-style.template.md)을 프로필 위치에 복사 (이미 있으면 덮어쓰지 않음)
    .\style.ps1 init -Force     # 덮어쓰기 (기존 프로필은 .bak 으로 보관)

프로필은 스킬 폴더가 아니라 **사용자 데이터 폴더**에 둔다 — 스킬을 다시 설치·갱신해도 사라지지 않고 사람마다 따로 갖는다.
  기본 위치  %LOCALAPPDATA%\RiroSms\message-style.md   (환경변수 RIRO_SMS_DATA_DIR 로 바꿀 수 있다)
프로필에는 말투·구조 규칙만 적는다. **학생·학부모 이름, 전화번호, 실제로 보낸 문자 본문은 적지 않는다.**
#>
param(
    [Parameter(Position = 0)][string]$Command = 'exists',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$data = if ($env:RIRO_SMS_DATA_DIR) { $env:RIRO_SMS_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'RiroSms' }
$path = Join-Path $data 'message-style.md'
$template = Join-Path $PSScriptRoot 'message-style.template.md'

switch ($Command.ToLower()) {
    'exists' {
        if (Test-Path -LiteralPath $path) { Write-Output 'yes'; exit 0 }
        Write-Output 'no'; exit 1
    }
    'path' { Write-Output $path }
    'show' {
        if (-not (Test-Path -LiteralPath $path)) { Write-Error "문체 프로필이 없습니다: $path (먼저 인터뷰 후 init)"; exit 1 }
        Get-Content -LiteralPath $path -Raw -Encoding UTF8
    }
    'init' {
        if ((Test-Path -LiteralPath $path) -and -not $Force) {
            Write-Warning "이미 있습니다: $path  (덮어쓰려면 -Force — 기존 파일은 .bak 으로 보관)"
            exit 1
        }
        New-Item -ItemType Directory -Force -Path $data | Out-Null
        if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination "$path.bak" -Force }
        Copy-Item -LiteralPath $template -Destination $path -Force
        Write-Output "양식을 만들었습니다: $path"
    }
    default {
        Write-Host "알 수 없는 명령: $Command"
        Write-Host '사용 가능: exists | path | show | init'
        exit 2
    }
}
