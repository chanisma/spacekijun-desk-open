# ie-dom.ps1 — 에듀파인 기안기(WXSClient, IE 내장) 창의 DOM 에 붙어 JS 를 실행한다.
#   WM_HTML_GETOBJECT → IHTMLDocument → parentWindow.execScript. 화면 좌표·클릭이 필요 없다.
#   Windows PowerShell 5.1(powershell.exe) 로 실행한다(COM late binding).
#
#   powershell -File ie-dom.ps1 -Title '결재경로설정' -Js 'return PrtcpList.toArray().length'
#   powershell -File ie-dom.ps1 -Hwnd 51845166 -JsFile step.js -ArgsJson '{"name":"홍길동"}'
#
#   JS 본문은 함수 안에서 돈다: return 값이 결과. 비동기면 return 하지 말고 __done(값) 을 부른다(-WaitMs 까지 기다림).
#   ARGS 변수로 -ArgsJson 이 들어온다. -Quiet 이면 alert/confirm 을 막고 메시지를 결과 뒤에 붙인다(confirm 은 true).
#   ⚠ 결재올림(fncSanctn)·임시저장(fncSaveTmpr/fncSaveCnsltTmp)·발송 함수는 부르지 않는다 — 사람이 누른다.
param(
  [long]$Hwnd = 0,
  [string]$Title = '',
  [string]$Js = '',
  [string]$JsFile = '',
  [string]$ArgsJson = 'null',
  [int]$Index = 0,
  [int]$WaitMs = 0,
  [switch]$Quiet,
  [switch]$List,
  [string]$CloseMsg = '',
  [string]$UrlLike = ''      # 같은 제목 창이 여럿이면 문서 주소가 이 패턴(-like)인 창을 고른다 (예: *DoccrdWritng*)
)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
if (-not ('IED' -as [type])) {
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public static class IED {
 public delegate bool P(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(P p, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, P cb, IntPtr l);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern uint RegisterWindowMessage(string s);
 [DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr h, uint m, IntPtr w, IntPtr l, uint f, uint t, out IntPtr r);
 [DllImport("oleacc.dll")] public static extern int ObjectFromLresult(IntPtr l, ref Guid iid, IntPtr w, [MarshalAs(UnmanagedType.IUnknown)] out object o);
 public static string Cls(IntPtr h){ var s=new StringBuilder(128); GetClassName(h,s,128); return s.ToString(); }
 public static string Txt(IntPtr h){ var s=new StringBuilder(256); GetWindowText(h,s,256); return s.ToString(); }
 public static List<IntPtr> Tops(uint pid){ var L=new List<IntPtr>(); EnumWindows((h,l)=>{ uint p; GetWindowThreadProcessId(h,out p); if(p==pid && IsWindowVisible(h)) L.Add(h); return true; }, IntPtr.Zero); return L; }
 public static List<IntPtr> Servers(IntPtr top){ var L=new List<IntPtr>(); EnumChildWindows(top,(h,l)=>{ if(Cls(h)=="Internet Explorer_Server") L.Add(h); return true; }, IntPtr.Zero); return L; }
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
 public static List<IntPtr> Kids(IntPtr top){ var L=new List<IntPtr>(); EnumChildWindows(top,(h,l)=>{ L.Add(h); return true; }, IntPtr.Zero); return L; }
 public static object Doc(IntPtr h){ uint m=RegisterWindowMessage("WM_HTML_GETOBJECT"); IntPtr r; SendMessageTimeout(h,m,IntPtr.Zero,IntPtr.Zero,2,5000,out r); Guid g=new Guid("626FC520-A41E-11CF-A731-00A0C9082637"); object o; ObjectFromLresult(r,ref g,IntPtr.Zero,out o); return o; }
}
"@
}

function Get-WxsWindows {
  $out = @()
  foreach ($p in Get-Process WXSClient -ErrorAction SilentlyContinue) {
    foreach ($h in [IED]::Tops([uint32]$p.Id)) {
      $out += [pscustomobject]@{ Hwnd = [long]$h; Class = [IED]::Cls($h); Title = [IED]::Txt($h) }
    }
  }
  $out
}

# 웹 페이지 메시지(alert/confirm) 닫기: 문구 출력 후 지정 버튼(확인/취소/예/아니요) 클릭
if ($CloseMsg) {
  $n = 0
  foreach ($w in (Get-WxsWindows | Where-Object { $_.Title -eq '웹 페이지 메시지' })) {
    $kids = [IED]::Kids([IntPtr]$w.Hwnd)
    $txt = ($kids | Where-Object { [IED]::Cls($_) -eq 'Static' } | ForEach-Object { [IED]::Txt($_) } | Where-Object { $_ }) -join ' '
    $btn = $kids | Where-Object { [IED]::Cls($_) -eq 'Button' -and ([IED]::Txt($_) -replace '&','') -like "$CloseMsg*" } | Select-Object -First 1
    # BM_CLICK(PostMessage)은 모달 alert 에서 무시될 때가 있어 UIA Invoke 로 누른다
    if ($btn) {
      Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
      $how = ''
      try { $el = [Windows.Automation.AutomationElement]::FromHandle($btn)
            $el.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke(); $how = 'uia' } catch { }
      if (-not $how) { try { $el.GetCurrentPattern([Windows.Automation.LegacyIAccessiblePattern]::Pattern).DoDefaultAction(); $how = 'acc' } catch { } }
      if (-not $how) { [IED]::PostMessage($btn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null; $how = 'bm' }
      $n++; Write-Output "CLOSED[$CloseMsg/$how] $txt" }
    else { Write-Output "NOBUTTON[$CloseMsg] $txt" }
  }
  if (-not $n) { Write-Output 'NONE' }
  return
}

if ($List) { Get-WxsWindows | ForEach-Object { "$($_.Hwnd)`t$($_.Class)`t$($_.Title)" }; return }

$doc = $null
$cands = if ($Hwnd) { @([pscustomobject]@{ Hwnd = $Hwnd }) } else { @(Get-WxsWindows | Where-Object { $_.Title -like "*$Title*" -and $_.Class -ne 'Internet Explorer_Hidden' }) }
if (-not $cands) { Write-Output "ERR no WXSClient window matching '$Title'"; exit 2 }
foreach ($c in $cands) {
  $sv = [IED]::Servers([IntPtr]$c.Hwnd)
  if ($sv.Count -le $Index) { continue }
  try { $d = [IED]::Doc($sv[$Index]) } catch { continue }
  if (-not $d) { continue }
  if ($UrlLike -and ([string]$d.url) -notlike $UrlLike) { continue }
  $doc = $d; $Hwnd = $c.Hwnd; break
}
if (-not $doc) { Write-Output "ERR no document in '$Title' window$(if ($UrlLike) { " matching $UrlLike" })"; exit 2 }

if (-not $ArgsJson) { $ArgsJson = 'null' }
if ($JsFile) { $Js = Get-Content -LiteralPath $JsFile -Raw -Encoding utf8 }
if (-not $Js) { Write-Output "url=$($doc.url)"; return }

$q = if ($Quiet) { 'true' } else { 'false' }
$wrap = @"
(function(){
  var B=document.body; B.removeAttribute('data-cr'); var __m=[];
  function __done(v){ B.setAttribute('data-cr', String(v) + (__m.length ? '\n[msgs] ' + __m.join(' // ') : '')); }
  var __oa=window.alert, __oc=window.confirm;
  if ($q){ window.alert=function(m){__m.push('ALERT:'+m);}; window.confirm=function(m){__m.push('CONFIRM:'+m); return true;}; }
  try { var ARGS = $ArgsJson; var __v = (function(ARGS, __done){ $Js
  })(ARGS, __done); if (__v !== undefined) __done(__v); }
  catch(e){ __done('ERR ' + e.message); }
  finally { if ($q){ window.alert=__oa; window.confirm=__oc; } }
})();
"@
$doc.parentWindow.execScript($wrap, 'JScript')
$res = $doc.body.getAttribute('data-cr')
$t0 = Get-Date
while (($null -eq $res -or $res -eq '') -and ((Get-Date) - $t0).TotalMilliseconds -lt $WaitMs) {
  Start-Sleep -Milliseconds 250
  try { $res = $doc.body.getAttribute('data-cr') } catch { $res = 'CLOSED'; break }
}
Write-Output $res
