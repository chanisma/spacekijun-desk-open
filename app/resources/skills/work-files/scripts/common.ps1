# 업무 자료 정리 — 공통 (다른 스크립트가 점 소싱한다)

function Get-WfRoot([string]$Root) {
    if ($Root) { return (Resolve-Path -LiteralPath $Root).Path }
    # 설치 위치: <자동화 업무>\.claude\skills\work-files\scripts  (Codex 는 .agents\skills)
    $guess = Split-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent) -Parent
    if ($guess -and (Test-Path -LiteralPath (Join-Path $guess 'AGENTS.md'))) { return $guess }
    return (Join-Path $env:USERPROFILE '자동화 업무')
}

function Get-WfDownloads {
    try { $p = (New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path; if ($p) { return $p } } catch { }
    return (Join-Path $env:USERPROFILE 'Downloads')
}

function Get-WfLog([string]$Root) { Join-Path (Join-Path $Root '업무') '정리 기록.csv' }

# 폴더 이름에 쓸 수 없는 글자를 뺀다
function ConvertTo-WfName([string]$Text) {
    $bad = [IO.Path]::GetInvalidFileNameChars() -join ''
    $clean = ($Text -replace "[$([regex]::Escape($bad))]", ' ').Trim().TrimEnd('.')
    return ($clean -replace '\s{2,}', ' ')
}
