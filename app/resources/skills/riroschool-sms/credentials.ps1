<#
리로스쿨 계정 보관 — Windows DPAPI 로 **이 PC 의 이 사용자만** 풀 수 있게 암호화한다.

    .\credentials.ps1 status      # 어디의 어떤 계정을 쓰게 되는지 (아이디만 — 비밀번호는 보여 주지 않는다)
    .\credentials.ps1 save        # 직접 저장 (아이디·비밀번호를 이 창에서 입력 — 에이전트 대화창에 쓰지 말 것)
    .\credentials.ps1 clear       # 직접 저장한 계정 삭제 (스페이스기전 데스크의 것은 건드리지 않는다)
    .\credentials.ps1 get         # ⚠️ 내부용 — riro-sms.mjs 가 부른다. 비밀번호가 그대로 출력되므로 사람·에이전트가 직접 부르지 말 것

어느 계정을 쓰나 (위에서부터)
  1) 이 스킬에 직접 저장한 계정        %LOCALAPPDATA%\RiroSms\credentials.dat
  2) 스페이스기전 데스크(교사판)에 저장된 리로스쿨 계정   %LOCALAPPDATA%\SpacekijunDesk\credentials.dat
     — 읽기만 한다. 파일에서 `riro_id`·`riro_password` 두 값만 꺼내 쓰고 나머지(인증서 암호 등)는 쓰지 않는다.
     데스크에서 리로스쿨 자동 로그인을 이미 설정해 두었다면 다시 입력할 필요가 없다.

비밀번호는 한 번만 넣는다 — 리로스쿨은 5번 틀리면 계정을 잠근다. 틀린 값이 저장돼 있으면 로그인 시도가 실패하므로
riro-sms.mjs 는 **로그인을 한 번만 시도하고 다시 시도하지 않는다.**
#>
param(
    [Parameter(Position = 0)][ValidateSet('status', 'save', 'clear', 'get')][string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$data = if ($env:RIRO_SMS_DATA_DIR) { $env:RIRO_SMS_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'RiroSms' }
$own = Join-Path $data 'credentials.dat'
$desk = Join-Path $env:LOCALAPPDATA 'SpacekijunDesk\credentials.dat'

function Unprotect-Json([string]$path) {
    $bytes = [IO.File]::ReadAllBytes($path)
    $plain = [Security.Cryptography.ProtectedData]::Unprotect($bytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    [Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
}

# 쓸 계정 찾기 — 돌려주는 것: @{ source; id; password } 또는 $null
function Find-Account {
    if (Test-Path -LiteralPath $own) {
        try {
            $v = Unprotect-Json $own
            if ($v.id -and $v.password) { return @{ source = 'own'; id = [string]$v.id; password = [string]$v.password } }
        } catch { }
    }
    if (Test-Path -LiteralPath $desk) {
        try {
            $v = Unprotect-Json $desk
            if ($v.riro_id -and $v.riro_password) { return @{ source = 'desk'; id = [string]$v.riro_id; password = [string]$v.riro_password } }
        } catch { }
    }
    return $null
}

switch ($Action) {
    'status' {
        $a = Find-Account
        if (-not $a) {
            Write-Output '저장된 리로스쿨 계정이 없습니다.'
            Write-Output "  직접 저장:  .\credentials.ps1 save"
            Write-Output "  또는 스페이스기전 데스크 설정에서 리로스쿨 계정을 저장하면 그것을 읽어 씁니다."
            exit 3
        }
        $where = if ($a.source -eq 'own') { '이 스킬에 직접 저장한 계정' } else { '스페이스기전 데스크에 저장된 계정(읽기만 함)' }
        Write-Output "사용할 계정: $where"
        Write-Output "  아이디: $($a.id)"
        Write-Output '  비밀번호: 저장돼 있음 (표시하지 않음)'
    }
    'get' {
        $a = Find-Account
        if (-not $a) { [Console]::Error.WriteLine('NO_ACCOUNT'); exit 3 }
        Write-Output ($a | ConvertTo-Json -Compress)
    }
    'save' {
        Write-Output '리로스쿨 계정을 저장합니다. 이 PC 의 이 Windows 사용자만 풀 수 있게 암호화됩니다.'
        $id = Read-Host '리로스쿨 아이디'
        $secure = Read-Host '리로스쿨 비밀번호 (화면에 보이지 않습니다)' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        if (-not $id.Trim() -or -not $password) { Write-Error '아이디와 비밀번호를 모두 입력하세요.'; exit 2 }
        $json = @{ id = $id.Trim(); password = $password } | ConvertTo-Json -Compress
        $blob = [Security.Cryptography.ProtectedData]::Protect([Text.Encoding]::UTF8.GetBytes($json), $null,
                                                               [Security.Cryptography.DataProtectionScope]::CurrentUser)
        New-Item -ItemType Directory -Force -Path $data | Out-Null
        [IO.File]::WriteAllBytes($own, $blob)
        Write-Output "저장했습니다: $own"
    }
    'clear' {
        if (Test-Path -LiteralPath $own) { Remove-Item -LiteralPath $own -Force; Write-Output '직접 저장한 계정을 지웠습니다.' }
        else { Write-Output '직접 저장한 계정이 없습니다.' }
    }
}
