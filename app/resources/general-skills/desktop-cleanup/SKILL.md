---
name: desktop-cleanup
description: Windows 바탕화면의 파일을 종류·날짜별 폴더로 정리한다. 먼저 둘러보고 계획을 보여 준 뒤 사용자가 승인하면 옮기고, 옮긴 기록을 남겨 언제든 되돌린다. 지우지 않는다. "바탕화면 정리", "바탕화면 파일 정리", "바탕화면 둘러보기", "바탕화면 되돌리기", "중복 파일 찾기" 요청 시 사용.
---

# 바탕화면 정리 (스페이스기전 데스크 기본 스킬)

어느 폴더에서 연 에이전트든 쓸 수 있는 스킬이다(데스크가 사용자 범위에 깐다 — `~/.claude/skills`, `~/.codex/skills`).

## 지켜야 할 것

- **지우지 않는다.** 휴지통으로도 보내지 않는다. 옮기기만 한다.
- **옮기기 전에 계획을 보여 주고 승인을 받는다.** 승인 없이 옮기지 않는다.
- 옮긴 것은 모두 **기록 파일**에 남긴다 — 되돌리기는 이 기록으로 한다.
- 바로 가기(`.lnk`·`.url`)·`desktop.ini`·숨김/시스템 파일·**지금 열려 있는 파일**(옮기기 실패)은 그대로 둔다.
- 같은 이름이 이미 있으면 덮어쓰지 말고 ` (2)` 를 붙인다.
- 파일 이름·내용에 학생·교직원 개인정보가 보여도 내용을 읽거나 요약해 밖으로 보내지 않는다 — 이름과 종류로만 정리한다.

## 바탕화면 위치

OneDrive 로 옮겨진 PC 가 많다. 경로를 짐작하지 말고 Windows 에 묻는다.

```powershell
$desk = [Environment]::GetFolderPath('Desktop')
```

정리 폴더와 기록 파일:

```
$root = Join-Path $desk '바탕화면 정리'
$log  = Join-Path $root '정리 기록.csv'     # 시각,원래 경로,옮긴 경로
```

## 1. 둘러보기 (옮기지 않는다)

```powershell
Get-ChildItem -LiteralPath $desk -Force |
  Where-Object { -not $_.Attributes.HasFlag([IO.FileAttributes]::Hidden) -and $_.Name -ne '바탕화면 정리' -and $_.Extension -notin '.lnk','.url' -and $_.Name -ne 'desktop.ini' } |
  Select-Object Name, Extension, Length, LastWriteTime, LastAccessTime, PSIsContainer
```

종류별 개수·크기, 오래된 것(마지막으로 쓴 지 90일 넘은 것), 폴더 수를 표로 보여 준다.

## 2. 계획 → 승인 → 옮기기

종류 분류(확장자):

| 폴더 | 확장자 |
|---|---|
| 문서 | .hwp .hwpx .doc .docx .pdf .txt .md .rtf .odt |
| 표 | .xls .xlsx .xlsm .csv .cell |
| 발표 | .ppt .pptx .show |
| 사진 | .png .jpg .jpeg .gif .bmp .webp .heic |
| 동영상·소리 | .mp4 .avi .mov .wmv .mkv .mp3 .wav .m4a |
| 압축 | .zip .7z .rar .alz .egg |
| 설치 파일 | .exe .msi .msix |
| 기타 | 그 밖의 파일 |
| 폴더 | 바탕화면의 폴더 (사용자가 원할 때만) |

- 기본은 `바탕화면 정리\<종류>\` 로. 사용자가 날짜별을 원하면 `바탕화면 정리\<YYYY-MM>\<종류>\`.
- «오래된 파일 정리»는 `바탕화면 정리\보관\` 로.
- 계획은 «어느 파일 → 어느 폴더» 표로 보여 주고, 개수를 요약한다. 승인을 받은 뒤에만 옮긴다.

옮길 때(파일 하나마다 기록):

```powershell
New-Item -ItemType Directory -Force -Path $target | Out-Null
$dest = Join-Path $target $item.Name
$n = 2
while (Test-Path -LiteralPath $dest) { $dest = Join-Path $target ("{0} ({1}){2}" -f $item.BaseName, $n, $item.Extension); $n++ }
Move-Item -LiteralPath $item.FullName -Destination $dest -ErrorAction Stop
"{0},`"{1}`",`"{2}`"" -f (Get-Date -Format s), $item.FullName, $dest | Add-Content -LiteralPath $log -Encoding utf8
```

옮기지 못한 것(열려 있음 등)은 모아서 마지막에 알린다.

## 3. 되돌리기

`정리 기록.csv` 를 **끝에서부터** 읽어, 옮긴 경로에 파일이 아직 있고 원래 경로가 비어 있으면 원래 자리로 옮긴다.
되돌린 줄은 기록에서 지운다. 원래 자리에 같은 이름이 생겼으면 덮어쓰지 말고 사용자에게 묻는다.

## 4. 중복 파일 찾기 (지우지 않는다)

크기가 같은 것끼리 `Get-FileHash -Algorithm SHA256` 로 비교해 같은 파일 묶음을 보여 준다. 무엇을 남길지는 사용자가 정한다.

## 마치며

무엇을 몇 개 옮겼는지, 어디로 갔는지, 못 옮긴 것, 되돌리는 방법(«지난번 바탕화면 정리를 되돌려 줘»)을 짧게 알린다.
