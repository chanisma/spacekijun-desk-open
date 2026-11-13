# 쿨메신저 네이티브 UI 조작 도구 (창 메시지 기반 — 커서를 뺏지 않는다)
#
#   . .\native.ps1                       # 함수 로드
#   Get-CmWindows                        # 창 목록
#   Get-CmTree                           # 조직도 트리 항목 열거
#   Select-CmTreeItem "홍길동"           # 트리에서 선택 + 더블클릭(쪽지창 열기)
#   Close-CmAdPopup                      # 광고 팝업 닫기
#
# 쿨메신저는 32비트 MFC 앱이라 TVITEM 구조체를 **32비트 레이아웃(40바이트)** 로 맞춰야 한다.
# 접근성(UIA)으로는 아무것도 안 나오므로 TVM_* 메시지를 직접 보낸다.

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class CmNative {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc p, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")] public static extern IntPtr SendMessageStr(IntPtr h, int msg, IntPtr wp, string lp);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, int msg, IntPtr wp, IntPtr lp);
  [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int access, bool inherit, int pid);
  [DllImport("kernel32.dll")] public static extern IntPtr VirtualAllocEx(IntPtr h, IntPtr addr, IntPtr size, int type, int protect);
  [DllImport("kernel32.dll")] public static extern bool VirtualFreeEx(IntPtr h, IntPtr addr, IntPtr size, int type);
  [DllImport("kernel32.dll")] public static extern bool WriteProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr written);
  [DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr read);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
'@ -ErrorAction SilentlyContinue

$script:WM_SETTEXT = 0x000C; $script:WM_GETTEXT = 0x000D
$script:BM_CLICK = 0x00F5
$script:TVM_GETNEXTITEM = 0x1100 + 10
$script:TVM_GETITEMW = 0x1100 + 62
$script:TVM_SELECTITEM = 0x1100 + 11
$script:TVM_GETITEMRECT = 0x1100 + 4
$script:TVM_EXPAND = 0x1100 + 2
$script:TVGN_ROOT = 0; $script:TVGN_NEXT = 1; $script:TVGN_CHILD = 4; $script:TVGN_CARET = 9
$script:TVGN_FIRSTVISIBLE = 5   # 이 항목이 맨 위에 오도록 스크롤
$script:TVE_EXPAND = 2
$script:TVM_ENSUREVISIBLE = 0x1100 + 20
$script:TVIF_TEXT = 1
$script:WM_LBUTTONDBLCLK = 0x0203; $script:WM_LBUTTONDOWN = 0x0201; $script:WM_LBUTTONUP = 0x0202

function Get-CmPid { (Get-Process CoolMessenger -ErrorAction SilentlyContinue | Select-Object -First 1).Id }

function Get-CmWindows {
  # -IncludeHidden : 트레이로 숨긴 창까지 본다. 메인 창을 되살릴 때 필요하다.
  param([switch]$IncludeHidden)
  $t = Get-CmPid
  $rows = New-Object System.Collections.ArrayList
  $cb = [CmNative+EnumProc]{ param($h, $l)
    $p = 0; [CmNative]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
    if ($p -ne $t) { return $true }
    if (-not $IncludeHidden -and -not [CmNative]::IsWindowVisible($h)) { return $true }
    $tt = New-Object System.Text.StringBuilder 256; [CmNative]::GetWindowText($h, $tt, 256) | Out-Null
    $c = New-Object System.Text.StringBuilder 128; [CmNative]::GetClassName($h, $c, 128) | Out-Null
    $r = New-Object CmNative+RECT; [CmNative]::GetWindowRect($h, [ref]$r) | Out-Null
    $null = $rows.Add([pscustomobject]@{ hwnd = $h; cls = $c.ToString(); title = $tt.ToString(); w = $r.Right - $r.Left; h = $r.Bottom - $r.Top })
    return $true }
  [CmNative]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
  $rows
}

function Get-CmChildren([IntPtr]$parent) {
  $rows = New-Object System.Collections.ArrayList
  $cb = [CmNative+EnumProc]{ param($h, $l)
    $c = New-Object System.Text.StringBuilder 128; [CmNative]::GetClassName($h, $c, 128) | Out-Null
    $tt = New-Object System.Text.StringBuilder 256; [CmNative]::GetWindowText($h, $tt, 256) | Out-Null
    $null = $rows.Add([pscustomobject]@{ hwnd = $h; id = [CmNative]::GetDlgCtrlID($h); cls = $c.ToString(); text = $tt.ToString(); vis = [CmNative]::IsWindowVisible($h) })
    return $true }
  [CmNative]::EnumChildWindows($parent, $cb, [IntPtr]::Zero) | Out-Null
  $rows
}

function Find-CmControl([string]$titleLike, [string]$cls) {
  foreach ($w in Get-CmWindows) {
    if ($titleLike -and $w.title -notlike $titleLike) { continue }
    $hit = Get-CmChildren $w.hwnd | Where-Object { $_.cls -eq $cls -and $_.vis } | Select-Object -First 1
    if ($hit) { return $hit }
  }
  $null
}

# ── 조직도(SysTreeView32) 원격 열거 ─────────────────────────────
function Get-CmTree([int]$max = 400, [IntPtr]$TreeHwnd = 0) {
  if ($TreeHwnd -ne [IntPtr]::Zero) { $tv = [pscustomobject]@{ hwnd = $TreeHwnd } }
  else {
    $tv = Find-CmControl -titleLike 'COOLMESSENGER*' -cls 'SysTreeView32'
    if (-not $tv) { Write-Error '조직도 트리를 찾지 못함'; return }
  }
  $pid2 = Get-CmPid
  $hProc = [CmNative]::OpenProcess(0x1F0FFF, $false, $pid2)     # PROCESS_ALL_ACCESS
  if ($hProc -eq [IntPtr]::Zero) { Write-Error 'OpenProcess 실패 (권한)'; return }
  $bufSize = 1024
  $rem = [CmNative]::VirtualAllocEx($hProc, [IntPtr]::Zero, [IntPtr](40 + $bufSize), 0x3000, 4)  # COMMIT|RESERVE, RW
  $remText = [IntPtr]($rem.ToInt64() + 40)
  $items = New-Object System.Collections.ArrayList
  try {
    $h = [CmNative]::SendMessage($tv.hwnd, $TVM_GETNEXTITEM, [IntPtr]$TVGN_ROOT, [IntPtr]::Zero)
    $stack = New-Object System.Collections.Stack
    $depth = 0
    while ($h -ne [IntPtr]::Zero -and $items.Count -lt $max) {
      # TVITEM(32bit): mask, hItem, state, stateMask, pszText, cchTextMax, iImage, iSelectedImage, cChildren, lParam
      $b = New-Object byte[] 40
      [BitConverter]::GetBytes([int]$TVIF_TEXT).CopyTo($b, 0)
      [BitConverter]::GetBytes([int]$h.ToInt32()).CopyTo($b, 4)
      [BitConverter]::GetBytes([int]$remText.ToInt32()).CopyTo($b, 16)
      [BitConverter]::GetBytes([int]($bufSize / 2)).CopyTo($b, 20)
      $w = [IntPtr]::Zero
      [CmNative]::WriteProcessMemory($hProc, $rem, $b, [IntPtr]40, [ref]$w) | Out-Null
      [CmNative]::SendMessage($tv.hwnd, $TVM_GETITEMW, [IntPtr]::Zero, $rem) | Out-Null
      $tb = New-Object byte[] $bufSize
      $r = [IntPtr]::Zero
      [CmNative]::ReadProcessMemory($hProc, $remText, $tb, [IntPtr]$bufSize, [ref]$r) | Out-Null
      $txt = [Text.Encoding]::Unicode.GetString($tb); $z = $txt.IndexOf([char]0); if ($z -ge 0) { $txt = $txt.Substring(0, $z) }
      $null = $items.Add([pscustomobject]@{ hItem = $h; depth = $depth; text = $txt })

      $child = [CmNative]::SendMessage($tv.hwnd, $TVM_GETNEXTITEM, [IntPtr]$TVGN_CHILD, $h)
      if ($child -ne [IntPtr]::Zero) { $stack.Push(@{ h = $h; d = $depth }); $h = $child; $depth++ ; continue }
      $next = [CmNative]::SendMessage($tv.hwnd, $TVM_GETNEXTITEM, [IntPtr]$TVGN_NEXT, $h)
      while ($next -eq [IntPtr]::Zero -and $stack.Count -gt 0) {
        $up = $stack.Pop(); $depth = $up.d
        $next = [CmNative]::SendMessage($tv.hwnd, $TVM_GETNEXTITEM, [IntPtr]$TVGN_NEXT, $up.h)
      }
      $h = $next
    }
  } finally {
    [CmNative]::VirtualFreeEx($hProc, $rem, [IntPtr]::Zero, 0x8000) | Out-Null
    [CmNative]::CloseHandle($hProc) | Out-Null
  }
  $items
}

function Expand-CmTreeAll {
  $tv = Find-CmControl -titleLike 'COOLMESSENGER*' -cls 'SysTreeView32'
  if (-not $tv) { return }
  foreach ($it in (Get-CmTree)) {
    [CmNative]::SendMessage($tv.hwnd, $TVM_EXPAND, [IntPtr]$TVE_EXPAND, $it.hItem) | Out-Null
  }
}

# 트리 항목 선택 후 더블클릭 (쪽지 창 열기)
function Select-CmTreeItem([string]$name, [switch]$DoubleClick) {
  $tv = Find-CmControl -titleLike 'COOLMESSENGER*' -cls 'SysTreeView32'
  if (-not $tv) { Write-Error '트리 없음'; return }
  $hit = Get-CmTree | Where-Object { $_.text -like "*$name*" } | Select-Object -First 1
  if (-not $hit) { Write-Error "트리에서 '$name' 못 찾음"; return }
  # ★ 항목이 스크롤되어 화면 밖이면 GetItemRect 가 **음수 y** 를 주고 더블클릭이 트리 밖으로 나간다.
  #   ENSUREVISIBLE 만으로는 부족했던 사례가 있어(2026-09-09, y=-11), 대상 항목을
  #   **맨 위로 스크롤**(TVGN_FIRSTVISIBLE)해서 좌표가 항상 양수가 되게 한다.
  [CmNative]::SendMessage($tv.hwnd, $TVM_ENSUREVISIBLE, [IntPtr]::Zero, $hit.hItem) | Out-Null
  Start-Sleep -Milliseconds 300
  [CmNative]::SendMessage($tv.hwnd, $TVM_SELECTITEM, [IntPtr]$TVGN_FIRSTVISIBLE, $hit.hItem) | Out-Null
  Start-Sleep -Milliseconds 400
  [CmNative]::SendMessage($tv.hwnd, $TVM_SELECTITEM, [IntPtr]$TVGN_CARET, $hit.hItem) | Out-Null
  Start-Sleep -Milliseconds 500
  if ($DoubleClick) {
    # 선택된 항목의 사각형을 얻어 그 좌표로 더블클릭 메시지 전송 (커서는 움직이지 않는다)
    $pid2 = Get-CmPid
    $hProc = [CmNative]::OpenProcess(0x1F0FFF, $false, $pid2)
    $rem = [CmNative]::VirtualAllocEx($hProc, [IntPtr]::Zero, [IntPtr]16, 0x3000, 4)
    $b = New-Object byte[] 16
    [BitConverter]::GetBytes([int]$hit.hItem.ToInt32()).CopyTo($b, 0)
    $w = [IntPtr]::Zero
    [CmNative]::WriteProcessMemory($hProc, $rem, $b, [IntPtr]16, [ref]$w) | Out-Null
    [CmNative]::SendMessage($tv.hwnd, $TVM_GETITEMRECT, [IntPtr]1, $rem) | Out-Null   # wParam=1: 텍스트 영역만
    $rb = New-Object byte[] 16; $r = [IntPtr]::Zero
    [CmNative]::ReadProcessMemory($hProc, $rem, $rb, [IntPtr]16, [ref]$r) | Out-Null
    $left = [BitConverter]::ToInt32($rb, 0); $top = [BitConverter]::ToInt32($rb, 4)
    $right = [BitConverter]::ToInt32($rb, 8); $bottom = [BitConverter]::ToInt32($rb, 12)
    [CmNative]::VirtualFreeEx($hProc, $rem, [IntPtr]::Zero, 0x8000) | Out-Null
    [CmNative]::CloseHandle($hProc) | Out-Null
    if ($top -lt 0 -or $bottom -le 0) {
      # 그래도 화면 밖이면 한 번 더 스크롤한 뒤 좌표를 다시 읽는다
      [CmNative]::SendMessage($tv.hwnd, $TVM_SELECTITEM, [IntPtr]$TVGN_FIRSTVISIBLE, $hit.hItem) | Out-Null
      Start-Sleep -Milliseconds 500
      $hProc2 = [CmNative]::OpenProcess(0x1F0FFF, $false, $pid2)
      $rem2 = [CmNative]::VirtualAllocEx($hProc2, [IntPtr]::Zero, [IntPtr]16, 0x3000, 4)
      [CmNative]::WriteProcessMemory($hProc2, $rem2, $b, [IntPtr]16, [ref]$w) | Out-Null
      [CmNative]::SendMessage($tv.hwnd, $TVM_GETITEMRECT, [IntPtr]1, $rem2) | Out-Null
      $rb2 = New-Object byte[] 16; $r2 = [IntPtr]::Zero
      [CmNative]::ReadProcessMemory($hProc2, $rem2, $rb2, [IntPtr]16, [ref]$r2) | Out-Null
      $left = [BitConverter]::ToInt32($rb2, 0); $top = [BitConverter]::ToInt32($rb2, 4)
      $right = [BitConverter]::ToInt32($rb2, 8); $bottom = [BitConverter]::ToInt32($rb2, 12)
      [CmNative]::VirtualFreeEx($hProc2, $rem2, [IntPtr]::Zero, 0x8000) | Out-Null
      [CmNative]::CloseHandle($hProc2) | Out-Null
    }
    $x = [int](($left + $right) / 2); $y = [int](($top + $bottom) / 2)
    $lp = [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF))
    [CmNative]::PostMessage($tv.hwnd, $WM_LBUTTONDOWN, [IntPtr]1, $lp) | Out-Null
    [CmNative]::PostMessage($tv.hwnd, $WM_LBUTTONUP, [IntPtr]0, $lp) | Out-Null
    Start-Sleep -Milliseconds 150
    [CmNative]::PostMessage($tv.hwnd, $WM_LBUTTONDBLCLK, [IntPtr]1, $lp) | Out-Null
    [CmNative]::PostMessage($tv.hwnd, $WM_LBUTTONUP, [IntPtr]0, $lp) | Out-Null
    "더블클릭 전송: '$($hit.text)' (트리 좌표 $x,$y)"
  } else { "선택: '$($hit.text)'" }
}

# ── 광고 팝업 자동 닫기 ────────────────────────────────────────
# 팝업은 CEF 페이지(coolmessenger.com/popup/...)이며 네이티브 #32770 창에 얹혀 있다.
function Close-CmAdPopup {
  $closed = 0
  foreach ($w in Get-CmWindows) {
    if ($w.cls -ne '#32770') { continue }
    if ($w.title -eq '' -or $w.title -like '*COOLMESSENGER*' -or $w.title -like '*로그인*') { continue }
    [CmNative]::PostMessage($w.hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # WM_CLOSE
    "팝업 닫음: '$($w.title)'"
    $closed++
  }
  if ($closed -eq 0) { "닫을 팝업 없음" }
}


# 임의의 SysTreeView32 에서 이름으로 항목 선택 (사용자 선택 대화상자용)
function Select-CmItemIn([IntPtr]$TreeHwnd, [string]$name) {
  $hit = Get-CmTree -TreeHwnd $TreeHwnd | Where-Object { $_.text -like "*$name*" } | Select-Object -First 1
  if (-not $hit) { Write-Error "'$name' 없음"; return $null }
  [CmNative]::SendMessage($TreeHwnd, $TVM_ENSUREVISIBLE, [IntPtr]::Zero, $hit.hItem) | Out-Null
  Start-Sleep -Milliseconds 200
  [CmNative]::SendMessage($TreeHwnd, $TVM_SELECTITEM, [IntPtr]$TVGN_CARET, $hit.hItem) | Out-Null
  Start-Sleep -Milliseconds 400
  $hit
}

# ── SysListView32 원격 읽기 (메시지 관리함 목록) ────────────────
# 32비트 앱이므로 LVITEM 도 32비트 레이아웃(40바이트)으로 맞춘다.
$script:LVM_GETITEMCOUNT = 0x1000 + 4
$script:LVM_GETITEMTEXTW = 0x1000 + 115
$script:LVM_SETITEMSTATE = 0x1000 + 43
$script:LVM_GETSELECTEDCOUNT = 0x1000 + 50
$script:LVIS_SELECTED = 2

function Get-CmListRows([IntPtr]$ListHwnd, [int]$Cols = 4, [int]$Max = 300) {
  $pid2 = Get-CmPid
  $hProc = [CmNative]::OpenProcess(0x1F0FFF, $false, $pid2)
  if ($hProc -eq [IntPtr]::Zero) { Write-Error 'OpenProcess 실패'; return }
  $buf = 1024
  $rem = [CmNative]::VirtualAllocEx($hProc, [IntPtr]::Zero, [IntPtr](40 + $buf), 0x3000, 4)
  $remText = [IntPtr]($rem.ToInt64() + 40)
  $n = [CmNative]::SendMessage($ListHwnd, $LVM_GETITEMCOUNT, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32()
  $rows = New-Object System.Collections.ArrayList
  try {
    for ($i = 0; $i -lt [Math]::Min($n, $Max); $i++) {
      $cells = @()
      for ($c = 0; $c -lt $Cols; $c++) {
        $b = New-Object byte[] 40
        [BitConverter]::GetBytes([int]$i).CopyTo($b, 4)              # iItem
        [BitConverter]::GetBytes([int]$c).CopyTo($b, 8)              # iSubItem
        [BitConverter]::GetBytes([int]$remText.ToInt32()).CopyTo($b, 20)  # pszText
        [BitConverter]::GetBytes([int]($buf / 2)).CopyTo($b, 24)     # cchTextMax
        $w = [IntPtr]::Zero
        [CmNative]::WriteProcessMemory($hProc, $rem, $b, [IntPtr]40, [ref]$w) | Out-Null
        [CmNative]::SendMessage($ListHwnd, $LVM_GETITEMTEXTW, [IntPtr]$i, $rem) | Out-Null
        $tb = New-Object byte[] $buf; $r = [IntPtr]::Zero
        [CmNative]::ReadProcessMemory($hProc, $remText, $tb, [IntPtr]$buf, [ref]$r) | Out-Null
        $t = [Text.Encoding]::Unicode.GetString($tb); $z = $t.IndexOf([char]0); if ($z -ge 0) { $t = $t.Substring(0, $z) }
        $cells += $t
      }
      $null = $rows.Add([pscustomobject]@{ index = $i; cells = $cells })
    }
  } finally {
    [CmNative]::VirtualFreeEx($hProc, $rem, [IntPtr]::Zero, 0x8000) | Out-Null
    [CmNative]::CloseHandle($hProc) | Out-Null
  }
  $rows
}

# 지정한 인덱스들만 선택 (나머지는 해제) — 오삭제 방지를 위해 명시적으로 다룬다
function Set-CmListSelection([IntPtr]$ListHwnd, [int[]]$Indexes) {
  $pid2 = Get-CmPid
  $hProc = [CmNative]::OpenProcess(0x1F0FFF, $false, $pid2)
  $rem = [CmNative]::VirtualAllocEx($hProc, [IntPtr]::Zero, [IntPtr]40, 0x3000, 4)
  try {
    # 전체 해제
    $b = New-Object byte[] 40
    [BitConverter]::GetBytes([int]0).CopyTo($b, 12)                  # state = 0
    [BitConverter]::GetBytes([int]$LVIS_SELECTED).CopyTo($b, 16)     # stateMask
    $w = [IntPtr]::Zero
    [CmNative]::WriteProcessMemory($hProc, $rem, $b, [IntPtr]40, [ref]$w) | Out-Null
    [CmNative]::SendMessage($ListHwnd, $LVM_SETITEMSTATE, [IntPtr](-1), $rem) | Out-Null
    # 지정 항목 선택
    $b2 = New-Object byte[] 40
    [BitConverter]::GetBytes([int]$LVIS_SELECTED).CopyTo($b2, 12)
    [BitConverter]::GetBytes([int]$LVIS_SELECTED).CopyTo($b2, 16)
    [CmNative]::WriteProcessMemory($hProc, $rem, $b2, [IntPtr]40, [ref]$w) | Out-Null
    foreach ($i in $Indexes) { [CmNative]::SendMessage($ListHwnd, $LVM_SETITEMSTATE, [IntPtr]$i, $rem) | Out-Null }
  } finally {
    [CmNative]::VirtualFreeEx($hProc, $rem, [IntPtr]::Zero, 0x8000) | Out-Null
    [CmNative]::CloseHandle($hProc) | Out-Null
  }
  [CmNative]::SendMessage($ListHwnd, $LVM_GETSELECTEDCOUNT, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32()
}

# ── 조직도 명부 · 별칭 ─────────────────────────────────────────
# 조직도 표시는 `(대화명)메모` 형식이다. 대화명이 실명이 아닌 경우가 있다 —
# 예: 홍길동 선생님은 `(보건실)홍길동` 으로, 대화명이 '보건실' 이고 실명은 메모에 있다.
# 그래서 "이름으로 보내달라"는 요청을 그대로 트리에 넣으면 못 찾을 수 있다.
# 명부를 떠 두고(Sync-CmRoster), 요청 이름을 실제 트리 항목으로 바꿔(Resolve-CmName) 쓴다.
$script:CmDataDir  = if ($env:CM_SEND_DATA_DIR) { $env:CM_SEND_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'CoolMessengerSend' }   # 명부·별칭·문체 프로필 저장 위치 (스킬 폴더 밖)
$script:CmRosterPath = Join-Path $script:CmDataDir 'roster.json'
$script:CmAliasPath  = Join-Path $script:CmDataDir 'aliases.json'

function Sync-CmRoster {
  <#  조직도를 읽어 명부 파일로 저장한다. 인사이동·대화명 변경 뒤에 다시 돌리면 된다. #>
  $tree = Get-CmTree -max 2000
  $rows = foreach ($t in $tree) {
    if ($t.text -notmatch '^\(([^)]*)\)(.*)$') { continue }
    [pscustomobject]@{
      text    = $t.text                    # 트리 원문  '(보건실)홍길동'
      display = $Matches[1].Trim()         # 대화명      '보건실'
      note    = $Matches[2].Trim()         # 메모(실명)  '홍길동'
      depth   = $t.depth
    }
  }
  $rows = $rows | Sort-Object text -Unique
  $before = @(Get-CmRoster).Count
  if ($before -ge 10 -and @($rows).Count -lt $before * 0.5) {
    throw "조직도에서 읽은 사람이 $(@($rows).Count)명뿐입니다 (기존 명부 ${before}명). 조직도가 검색 결과로 걸러졌거나 접혀 있을 수 있어 명부를 덮어쓰지 않습니다. 검색칸을 비우고(Reset-CmSearch) 다시 시도하세요."
  }
  New-Item -ItemType Directory -Force -Path $script:CmDataDir | Out-Null
  $rows | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $script:CmRosterPath -Encoding UTF8
  "명부 저장: $($rows.Count)명 → $($script:CmRosterPath)"
}

function Get-CmRoster {
  if (-not (Test-Path $script:CmRosterPath)) { return @() }
  @(Get-Content -LiteralPath $script:CmRosterPath -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-CmAliases {
  if (-not (Test-Path $script:CmAliasPath)) { return @{} }
  $o = Get-Content -LiteralPath $script:CmAliasPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $h = @{}
  foreach ($p in $o.PSObject.Properties) { $h[$p.Name] = $p.Value }
  $h
}

function Set-CmAlias([string]$Name, [string]$Target) {
  <#  '홍길동' 을 '보건실' 로 보낸다는 식의 수동 매핑. Resolve-CmName 이 가장 먼저 본다. #>
  $h = Get-CmAliases
  $h[$Name] = $Target
  New-Item -ItemType Directory -Force -Path $script:CmDataDir | Out-Null
  ($h | ConvertTo-Json -Depth 3) | Set-Content -LiteralPath $script:CmAliasPath -Encoding UTF8
  "별칭 저장: '$Name' → '$Target'"
}

function Remove-CmAlias([string]$Name) {
  $h = Get-CmAliases
  if (-not $h.ContainsKey($Name)) { return "별칭 없음: '$Name'" }
  $h.Remove($Name)
  ($h | ConvertTo-Json -Depth 3) | Set-Content -LiteralPath $script:CmAliasPath -Encoding UTF8
  "별칭 삭제: '$Name'"
}

function Resolve-CmName([string]$Name) {
  <#
    요청 이름 → 실제 트리 항목 텍스트.
    반환: @{ ok; text; why; candidates }
    순서: 별칭 → 대화명 완전일치 → 메모(실명) 완전일치 → 부분일치(유일할 때만)
    부분일치가 여러 건이면 **고르지 않고 후보를 돌려준다** — 엉뚱한 사람에게 보내는 것보다 낫다.
  #>
  $roster = Get-CmRoster
  if ($roster.Count -eq 0) { return @{ ok = $false; why = '명부가 비어 있습니다. Sync-CmRoster 를 먼저 실행하세요.'; candidates = @() } }

  $alias = Get-CmAliases
  $q = $Name.Trim()
  $via = ''
  if ($alias.ContainsKey($q)) { $via = " (별칭 '$q' → '$($alias[$q])')"; $q = $alias[$q] }

  $hit = @($roster | Where-Object { $_.display -eq $q })
  if ($hit.Count -eq 1) { return @{ ok = $true; text = $hit[0].text; why = "대화명 일치$via" } }

  $hit = @($roster | Where-Object { $_.note -eq $q })
  if ($hit.Count -eq 1) { return @{ ok = $true; text = $hit[0].text; why = "메모(실명) 일치$via" } }

  $hit = @($roster | Where-Object { $_.text -like "*$q*" })
  if ($hit.Count -eq 1) { return @{ ok = $true; text = $hit[0].text; why = "부분일치$via" } }
  if ($hit.Count -gt 1) {
    return @{ ok = $false; why = "'$q' 후보가 여러 명입니다. 별칭을 지정하세요."; candidates = @($hit.text) }
  }
  @{ ok = $false; why = "'$q' 를 조직도에서 찾지 못했습니다."; candidates = @() }
}

function Restore-CmMainWindow {
  <#  메인 창이 트레이로 숨겨졌거나 최소화돼 있으면 조직도 트리를 읽을 수도(Get-CmTree: '조직도 트리를 찾지 못함'),
      더블클릭할 수도 없다. 복원만 하고 SetForegroundWindow 는 쓰지 않는다 — 포커스를 뺏으면 사용자 작업을 방해한다. #>
  Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class CmWinShow { [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
                         [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); }' -ErrorAction SilentlyContinue
  $w = Get-CmWindows -IncludeHidden | Where-Object { $_.title -like 'COOLMESSENGER*' } | Select-Object -First 1
  if (-not $w) { throw '쿨메신저 메인 창을 찾지 못했습니다. 앱이 실행 중이고 로그인돼 있는지 확인하세요. 샌드박스(예: Codex 기본 샌드박스)나 다른 데스크톱 세션에서 실행 중이면 사용자 창이 보이지 않습니다 — 샌드박스 밖(full access 또는 승인 후 실행)에서 다시 실행하세요.' }
  if (-not [CmWinShow]::IsWindowVisible($w.hwnd)) { [CmWinShow]::ShowWindow($w.hwnd, 5) | Out-Null; Start-Sleep -Milliseconds 500 }  # SW_SHOW
  [CmWinShow]::ShowWindow($w.hwnd, 9) | Out-Null                                                                                    # SW_RESTORE
  Start-Sleep -Milliseconds 800
  $w
}

function Ensure-CmRunning([int]$Port = 9222, [int]$WaitSec = 90) {
  <#  쿨메신저가 **꺼져 있을 때만** 디버깅 포트로 켜고, 로그인(접속)이 끝나 메인 창이 뜰 때까지 기다린다.
      이미 켜져 있으면 아무것도 하지 않고 $false 를 돌려준다 — 켜진 앱을 재시작하면 작성 중인 쪽지창이 사라지므로
      그건 start-coolmessenger.ps1 -Restart 로 **사람이 결정**한다.
      자동 로그인이 켜져 있으면 로그인 창 없이 접속된다(2026-09-11 확인). 꺼져 있으면 로그인 창이 뜨므로 직접 로그인해야 한다. #>
  if (Get-CmPid) { return $false }
  # 디버깅 포트는 열려 있는데 프로세스가 안 보이면 "꺼진 것"이 아니라 "내가 못 보는 것"이다 — 켜려고 90초를 기다리지 말고 원인을 알린다
  $portOpen = $false
  try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 2; $portOpen = $true } catch {}
  if ($portOpen) { throw "쿨메신저 디버깅 포트($Port)는 열려 있는데 프로세스가 보이지 않습니다. 샌드박스(예: Codex 기본 샌드박스)나 다른 데스크톱 세션에서 실행 중이면 사용자 창이 보이지 않습니다 — 샌드박스 밖(full access 또는 승인 후 실행)에서 다시 실행하세요." }
  Write-Host '쿨메신저가 꺼져 있어 실행합니다...'
  & (Join-Path $PSScriptRoot 'start-coolmessenger.ps1') -Port $Port
  for ($i = 0; $i -lt $WaitSec; $i++) {
    $wins  = @(Get-CmWindows -IncludeHidden)
    $login = $wins | Where-Object { $_.title -eq '로그인' }                 # 로그인 창: 제목 '로그인' (메인 창도 #32770 이라 클래스로는 못 가른다)
    $main  = $wins | Where-Object { $_.title -like 'COOLMESSENGER*' }
    if ($main -and -not $login) { Start-Sleep -Seconds 5; Write-Host '쿨메신저 접속 완료.'; return $true }   # 조직도 로딩 여유
    if ($i -eq 15 -and $login) { Write-Host '로그인 창이 떠 있습니다 — 직접 로그인해 주세요. 기다리는 중...' }
    Start-Sleep -Seconds 1
  }
  throw "쿨메신저 접속을 ${WaitSec}초 안에 확인하지 못했습니다. 로그인 창이 떠 있으면 직접 로그인한 뒤 다시 실행하세요."
}

function Reset-CmSearch {
  <#  조직도 위 **검색칸에 검색어가 남아 있으면 조직도가 검색 결과로 걸러져** 수신자를 못 찾는다
      (2026-10-22: 동료과 쪽지를 주고받은 뒤 검색칸이 남아 `학교 > 부서 > 동료 1명` 한 명만 보였고, 6명 발송이 전부 '트리에서 못 찾음'으로 멈췄다).
      🚨 검색칸은 **비어 있어도 안내 문구('이름(아이디) 또는 그룹명 검색', 31자)가 들어 있다** — 글자 수만 보면 늘 '남아 있다'로 오판한다.
         그래서 안내 문구는 빈 것으로 본다. 또 칸의 글자를 직접 지우면(WM_SETTEXT '') 앱의 안내 문구 상태가 깨지므로 **건드리지 않고**,
         앱의 `검색초기화(ESC)` 단추(3278)만 누른다.
      돌려주는 것: 걸러져 있던 것을 풀었으면 $true. #>
  $main = Get-CmWindows -IncludeHidden | Where-Object { $_.title -like 'COOLMESSENGER*' } | Select-Object -First 1
  if (-not $main) { return $false }
  $kids = Get-CmChildren $main.hwnd
  $edit  = $kids | Where-Object { $_.cls -eq 'Edit' -and $_.id -eq 1708 } | Select-Object -First 1
  $reset = $kids | Where-Object { $_.cls -eq 'Button' -and $_.id -eq 3278 } | Select-Object -First 1
  if (-not $edit -or -not $reset) { return $false }
  Add-Type -TypeDefinition 'using System;using System.Text;using System.Runtime.InteropServices;
public class CmEditRead { [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")] public static extern int Get(IntPtr h, int m, int w, StringBuilder l); }' -ErrorAction SilentlyContinue
  $sb = New-Object System.Text.StringBuilder 512
  [void][CmEditRead]::Get($edit.hwnd, 0x000D, 512, $sb)               # WM_GETTEXT
  $text = $sb.ToString().Trim()
  if (-not $text -or $text -match '그룹명\s*검색$') { return $false }   # 비었거나 안내 문구뿐
  Write-Host "조직도 검색칸에 검색어($($text.Length)자)가 남아 있어 검색을 초기화합니다 (걸러진 조직도로는 수신자를 못 찾습니다)"
  [CmNative]::PostMessage($reset.hwnd, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # BM_CLICK (모달 아님이라 Post)
  for ($i = 0; $i -lt 20; $i++) {                                      # 조직도가 다시 펼쳐질 때까지 (최대 약 6초)
    Start-Sleep -Milliseconds 300
    [void][CmEditRead]::Get($edit.hwnd, 0x000D, 512, $sb)
    if (@(Get-CmTree -max 200).Count -gt 5) { break }
  }
  return $true
}