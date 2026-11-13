# 서버(서류함·업무 지식)에 올리기 전에 업무 요약에서 개인정보로 보이는 것을 찾는다 (읽기만).
#   & .\summary-check.ps1 -Path "<업무 폴더>\업무 요약.md"
#   & .\summary-check.ps1 -Path "…\업무 요약.md" -Names "홍길동","김○○"    # 작업 중 본 사람 이름도 찾는다
# 찾은 것이 있으면 줄 번호와 종류를 보이고 종료 코드 1. 글자 패턴만 보므로, 통과해도 사람 이름은 눈으로 한 번 더 본다.
param([Parameter(Mandatory)][string]$Path, [string[]]$Names = @())
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$rules = [ordered]@{
    '주민등록번호'   = '(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)'
    '휴대전화'       = '(?<!\d)01[016789][\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)'
    '전화번호'       = '(?<!\d)0[2-6]\d?[\s.)-]\s?\d{3,4}[\s.-]\d{4}(?!\d)'
    '이메일'         = '[\w.+-]+@[\w-]+(\.[\w-]+)+'
    '학년·반·번호'   = '\d\s*학년\s*\d{1,2}\s*반\s*\d{1,2}\s*번|(?<!\d)\d{1,2}\s*반\s*\d{1,2}\s*번'
    '학번(5자리)'    = '(?<![\d.-])[1-3](0[1-9]|1[0-9])(0[1-9]|[1-4][0-9])(?!\d|[.-]\d)'
    '생년월일'       = '(?<!\d)(19|20)\d{2}[./-]\s?\d{1,2}[./-]\s?\d{1,2}\s*(생|출생)'
    '점수·등급'      = '\d{1,3}(\.\d+)?\s*점(?!검)|(?<!\w)[1-9]\s*등급'
    '내 PC 경로'     = '[A-Za-z]:\\Users\\[^\\\s]+'
}
$hits = @()
$lines = Get-Content -LiteralPath $Path -Encoding UTF8
for ($i = 0; $i -lt $lines.Count; $i++) {
    foreach ($kind in $rules.Keys) {
        foreach ($m in [regex]::Matches($lines[$i], $rules[$kind])) { $hits += [pscustomobject]@{ 줄 = $i + 1; 종류 = $kind; 찾은것 = $m.Value } }
    }
    foreach ($name in $Names | Where-Object { $_ -and $_.Trim().Length -ge 2 }) {
        if ($lines[$i].Contains($name.Trim())) { $hits += [pscustomobject]@{ 줄 = $i + 1; 종류 = '사람 이름'; 찾은것 = $name.Trim() } }
    }
}
if ($hits) {
    Write-Host "개인정보로 보이는 것 $($hits.Count)곳 — 지우거나 «담임»«담당 선생님»«학생 ○명»처럼 바꾼 뒤 다시 검사한다:"
    $hits | Format-Table -AutoSize | Out-String -Width 300 | Write-Host
    exit 1
}
Write-Host "글자 패턴으로는 찾은 것이 없습니다 ($($lines.Count)줄). 사람 이름·학생을 알아볼 수 있는 내용은 눈으로 한 번 더 확인하세요."
exit 0
