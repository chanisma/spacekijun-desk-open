<#
쿨메신저 조직도 명부·별칭 관리.

    .\roster.ps1 sync                    # 조직도를 읽어 명부 갱신 (인사이동·대화명 변경 후)
    .\roster.ps1 list [검색어]           # 명부 보기
    .\roster.ps1 find 홍길동             # 이 이름이 누구로 해석되는지 확인
    .\roster.ps1 alias 홍길동 보건실     # 별칭 지정 (요청이름 → 대화명)
    .\roster.ps1 unalias 홍길동          # 별칭 삭제
    .\roster.ps1 aliases                 # 별칭 목록

왜 필요한가
  조직도 표시는 `(대화명)메모` 형식인데 **대화명이 실명이 아닌 경우가 있다.**
  예) 홍길동 선생님 → `(보건실)홍길동` — 대화명은 '보건실', 실명은 메모에 있다.
  이름만 주고 보내라고 하면 못 찾을 수 있어서, 명부를 떠 두고 요청 이름을 실제 항목으로 바꾼다.

해석 순서: 별칭 → 대화명 완전일치 → 메모(실명) 완전일치 → 부분일치(유일할 때만)
  부분일치가 여러 건이면 **고르지 않고 후보를 보여준다** — 엉뚱한 사람에게 보내는 것보다 낫다.
#>
param(
    [Parameter(Position = 0)][string]$Command = 'list',
    [Parameter(Position = 1)][string]$Arg1,
    [Parameter(Position = 2)][string]$Arg2
)

$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'native.ps1')

switch ($Command.ToLower()) {
    'sync' {
        Ensure-CmRunning | Out-Null
        Restore-CmMainWindow | Out-Null
        Reset-CmSearch | Out-Null
        Sync-CmRoster
    }
    'list' {
        $r = Get-CmRoster
        if ($r.Count -eq 0) { Write-Host '명부가 비어 있습니다. .\roster.ps1 sync 를 먼저 실행하세요.'; break }
        $rows = if ($Arg1) { $r | Where-Object { $_.text -like "*$Arg1*" } } else { $r }
        Write-Host ("명부 {0}명{1}" -f @($rows).Count, $(if ($Arg1) { " (검색: $Arg1)" } else { '' }))
        $rows | ForEach-Object {
            "  {0,-14} {1}" -f $_.display, $(if ($_.note) { "· $($_.note)" } else { '' })
        }
    }
    'find' {
        if (-not $Arg1) { Write-Host '이름을 주세요:  .\roster.ps1 find 홍길동'; break }
        $res = Resolve-CmName $Arg1
        if ($res.ok) {
            Write-Host "✅ '$Arg1' → '$($res.text)'   ($($res.why))"
        } else {
            Write-Host "❌ $($res.why)"
            if ($res.candidates -and $res.candidates.Count) {
                Write-Host '   후보:'
                $res.candidates | ForEach-Object { "     $_" }
                Write-Host "   해결:  .\roster.ps1 alias $Arg1 <대화명>"
            }
        }
    }
    'alias' {
        if (-not $Arg1 -or -not $Arg2) { Write-Host '사용법:  .\roster.ps1 alias 홍길동 보건실'; break }
        Set-CmAlias $Arg1 $Arg2
        $res = Resolve-CmName $Arg1
        if ($res.ok) { Write-Host "  확인: '$Arg1' → '$($res.text)'" }
        else { Write-Warning "  아직 해석되지 않습니다: $($res.why)" }
    }
    'unalias' {
        if (-not $Arg1) { Write-Host '사용법:  .\roster.ps1 unalias 홍길동'; break }
        Remove-CmAlias $Arg1
    }
    'aliases' {
        $h = Get-CmAliases
        if ($h.Count -eq 0) { Write-Host '등록된 별칭이 없습니다.'; break }
        Write-Host "별칭 $($h.Count)개"
        $h.GetEnumerator() | Sort-Object Name | ForEach-Object { "  {0,-14} → {1}" -f $_.Key, $_.Value }
    }
    default {
        Write-Host "알 수 없는 명령: $Command"
        Write-Host '사용 가능: sync | list | find | alias | unalias | aliases'
    }
}
