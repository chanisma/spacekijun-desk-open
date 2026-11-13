# 최근에 바뀐 파일 후보 (읽기만). 다운로드·바탕화면·자동화 업무 폴더(스킬·업무 폴더 제외).
#   & .\candidates.ps1 -Since "2026-10-30 08:00"     또는  -Hours 6
param([string]$Since, [double]$Hours = 0, [string]$Root, [string[]]$Extra = @())
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$root = Get-WfRoot $Root
$from = if ($Since) { [datetime]$Since } elseif ($Hours -gt 0) { (Get-Date).AddHours(-$Hours) } else { (Get-Date).Date }
$places = @(
    @{ Name = '다운로드'; Path = (Get-WfDownloads); Deep = $false },
    @{ Name = '바탕화면'; Path = [Environment]::GetFolderPath('Desktop'); Deep = $false },
    @{ Name = '자동화 업무'; Path = $root; Deep = $true }
) + ($Extra | ForEach-Object { @{ Name = $_; Path = $_; Deep = $false } })
$skip = '\\(\.claude|\.agents|\.git|node_modules|업무)(\\|$)'

$rows = foreach ($p in $places) {
    if (-not (Test-Path -LiteralPath $p.Path)) { continue }
    $items = if ($p.Deep) { Get-ChildItem -LiteralPath $p.Path -File -Recurse -Force -ErrorAction SilentlyContinue }
             else { Get-ChildItem -LiteralPath $p.Path -File -Force -ErrorAction SilentlyContinue }
    foreach ($f in $items) {
        if ($f.LastWriteTime -lt $from -and $f.CreationTime -lt $from) { continue }
        if ($f.Attributes -band [IO.FileAttributes]::Hidden) { continue }
        if ($f.Extension -in '.lnk', '.url', '.tmp', '.crdownload', '.partial' -or $f.Name -eq 'desktop.ini') { continue }
        $rel = $f.FullName.Substring($p.Path.Length)
        if ($p.Deep -and ($rel -match $skip -or $f.DirectoryName -eq $root)) { continue }   # 작업 폴더 맨 위(AGENTS.md 등)는 뺀다
        [pscustomobject]@{ 위치 = $p.Name; 이름 = $f.Name; 크기KB = [math]::Ceiling($f.Length / 1KB); 바뀐때 = $f.LastWriteTime.ToString('MM-dd HH:mm'); 경로 = $f.FullName }
    }
}
Write-Host "기준: $($from.ToString('yyyy-MM-dd HH:mm')) 이후 · 작업 폴더: $root"
if (-not $rows) { Write-Host '(해당 파일 없음)'; return }
$rows | Sort-Object 위치, 바뀐때 | Format-Table -AutoSize -Wrap | Out-String -Width 400 | Write-Host
