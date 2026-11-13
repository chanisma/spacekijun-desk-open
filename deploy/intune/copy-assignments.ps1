<#
  Intune 앱의 할당을 다른 앱에 그대로 옮겨 걸기 (2026-10-20 — 이세계 사회인 캐릭터 팩을 학생판과 같은 그룹에).

    pwsh -ExecutionPolicy Bypass -File deploy\intune\copy-assignments.ps1 -From <앱 id> -To <앱 id>            # 걸기
    pwsh -ExecutionPolicy Bypass -File deploy\intune\copy-assignments.ps1 -From <앱 id> -To <앱 id> -DryRun    # 보이기만

  -From 의 할당(포함·제외 그룹, 모든 장치·모든 사용자)과 의도(필수·사용 가능·제거)를 -To 에 건다.
  -To 에 이미 할당이 있으면 아무것도 하지 않는다 (겹쳐 걸지 않게).
  학생판 «스페이스기전 데스크톱» = 00000000-0000-0000-0000-000000000000,
  캐릭터 팩 «스페이스기전 학생 · 이세계 사회인 캐릭터» = 00000000-0000-0000-0000-000000000000.
  로그인·앱 등록은 publish-intune.ps1 머리말과 같다 (SPACEKIJUN_INTUNE_TENANT·SPACEKIJUN_INTUNE_CLIENT, -DeviceCode).
#>
param(
    [Parameter(Mandatory)][string]$From,
    [Parameter(Mandatory)][string]$To,
    [string]$TenantId = $env:SPACEKIJUN_INTUNE_TENANT,
    [string]$ClientId = $env:SPACEKIJUN_INTUNE_CLIENT,
    [switch]$DeviceCode,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7(pwsh)로 돌려 주세요 — Windows PowerShell 5.1 은 Graph 에 한글을 «?» 로 보낸다.' }
# IntuneWin32App 1.5.0 은 한국어 Windows 의 날짜 글(«오후»)을 못 읽는다 — 날짜 형식만 영어로.
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo('en-US')
if (-not $TenantId -or -not $ClientId) { throw '테넌트·클라이언트 ID 가 없습니다 (publish-intune.ps1 머리말 참고).' }
Import-Module IntuneWin32App -RequiredVersion 1.5.0 -Force
$scopes = @('DeviceManagementApps.ReadWrite.All', 'offline_access')
if ($DeviceCode) { Connect-MSIntuneGraph -TenantID $TenantId -ClientID $ClientId -DeviceCode -Scopes $scopes | Out-Null }
else { Connect-MSIntuneGraph -TenantID $TenantId -ClientID $ClientId -Interactive -Scopes $scopes | Out-Null }

# 할당은 Graph 에서 바로 읽는다 (모듈의 그룹 이름 찾기는 이 앱 등록에 없는 권한이 필요하다)
$headers = @{ Authorization = "Bearer $($Global:AccessToken.access_token)" }
$read = { param($id) (Invoke-RestMethod -Uri "https://graph.microsoft.com/beta/deviceAppManagement/mobileApps/$id/assignments" -Headers $headers -Method GET).value }
$source = @(& $read $From)
foreach ($a in $source) { Write-Output ("{0}: {1} {2} {3}" -f $From, $a.intent, $a.target.'@odata.type', $a.target.groupId) }
$existing = @(& $read $To)
if ($existing.Count) { Write-Output "$To 에 이미 할당 $($existing.Count)개 — 건드리지 않았습니다."; return }
if ($DryRun) { Write-Output '-DryRun — 아무것도 바꾸지 않았습니다.'; return }

foreach ($a in $source) {
    $type = $a.target.'@odata.type'
    switch ($type) {
        '#microsoft.graph.groupAssignmentTarget' { Add-IntuneWin32AppAssignmentGroup -Include -ID $To -GroupID $a.target.groupId -Intent $a.intent -Notification 'hideAll' | Out-Null }
        '#microsoft.graph.exclusionGroupAssignmentTarget' { Add-IntuneWin32AppAssignmentGroup -Exclude -ID $To -GroupID $a.target.groupId -Intent $a.intent | Out-Null }
        '#microsoft.graph.allDevicesAssignmentTarget' { Add-IntuneWin32AppAssignmentAllDevices -ID $To -Intent $a.intent -Notification 'hideAll' | Out-Null }
        '#microsoft.graph.allLicensedUsersAssignmentTarget' { Add-IntuneWin32AppAssignmentAllUsers -ID $To -Intent $a.intent -Notification 'hideAll' | Out-Null }
        default { Write-Output "건너뜀: $type" }
    }
}
foreach ($a in (& $read $To)) { Write-Output ("{0}: {1} {2} {3}" -f $To, $a.intent, $a.target.'@odata.type', $a.target.groupId) }
