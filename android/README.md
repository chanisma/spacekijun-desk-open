# 스페이스기전 교실 — 안드로이드(전자칠판)판

Windows 교실판(`app/classroom.py`, `app/CLASSROOM.md`)과 같은 서버·같은 흐름을 안드로이드 전자칠판에서.
칠판에 QR 이 떠 있고, 교사가 휴대폰으로 찍어 스페이스기전에서 세팅을 고르면 칠판에 **수업 화면(타일)** 이 놓인다.
아무것도 저절로 열지 않는다. 수업이 끝나면(정해 둔 시간 · [수업 끝] · 휴대폰의 «여기서 수업 끝내기») 고친 파일을 올리고
받은 파일·로그인을 지운 뒤 다시 QR.

최종 확인: 2026-10-14 (1.3.0) — JVM 시험 40개(Robolectric 앱 띄우기 포함), 화면 미리 보기(브라우저 + 가짜 다리), 에뮬레이터는 아래 «검증» 참조.

## 구조

| 파일 | 하는 일 |
|---|---|
| `Link.kt` | 서버(DB RPC `classroom_device_call`, anon 키 — 2026-11-10 까지 Edge Function `classroom-link`) — start·poll·extend·end. 밤·주말엔 QR 을 10분 뒤 쉰다(Controller.kt). platform `android` → 승인 화면에 «전자칠판» |
| `Device.kt` | 연결 키(AndroidKeyStore AES 로 감싸 앱 전용 저장소에) · 기기 이름 |
| `Controller.kt` | qr → session → ending → qr. Windows `core/classroom_controller.py` 를 옮김 |
| `Session.kt` | 수업 한 번 — 타일 열기, 구글 앱, 끝낼 때 정리. 프로그램 키 → 안드로이드 앱(`Programs`) |
| `Drive.kt` | 드라이브 API · 연 파일 되올리기 · 못 올린 파일 상자. Windows `core/classroom_drive.py` 를 옮김 |
| `MainActivity.kt` + `assets/web/board.*` | 화면(QR·수업·드라이브 탐색기·설정). HTML 은 `Bridge.kt` 로만 앱을 부른다 |
| `BrowserActivity.kt` | 앱 안 브라우저 — 사이트·구글 앱·스페이스기전(받은 세션을 심는다). **따로 도는 프로세스 `:web`** |
| `WebVault.kt` | 앱 안 브라우저 로그인 보관(1.3.0) — 선생님마다 암호화해 이 칠판에 |
| `Bubble.kt` | 다른 앱(PowerPoint 등) 위에 «◀ 수업 화면» 단추 |
| `Updater.kt` | 자동 업데이트(받아 두기 → QR 화면의 [새 판 설치]) |

글꼴·아이콘은 Windows 판 `app/web/{fonts,icons}` 을 빌드할 때 복사한다(`copySharedWeb`) — 한 곳만 고친다.
세팅 키(프로그램·구글 앱)는 웹 `presetItems.ts` 와 같아야 한다 — spacekijun `scripts/classroom-link-test` 가 확인한다.

## 화면 배치 (2026-10-14, 1.0.1)

- **누르는 단추는 모두 아래에** — 수업 화면(세팅 이름·남은 시간·+10분·수업 끝), 드라이브 탐색기(← 수업 화면·출처·올리기 등),
  앱 안 브라우저(← → ⟳·수업 화면). 큰 칠판은 위쪽에 손이 닿기 어렵다.
- QR 화면은 1.0.0 보다 조금 작게(QR 최대 380px).
- **기기 이름을 바꾸면 QR 을 바로 새로 만든다** — 서버는 QR 을 만들 때의 이름을 적으므로, 떠 있던 옛 QR 로 연결하면
  옛 이름이 저장됐다(1.0.0 버그, 2026-10-14 사용자 보고). 서버의 기기 이름은 다음 승인 때 새 이름으로 바뀐다.

## 1.3.0 (2026-10-14) — 사이트 로그인 보관 (사용자 결정 ①+②)

패들렛 같은 사이트가 다음 수업에도 로그인된 채로 열리게. Windows 판 A+(`core/classroom_vault.py`)와 같은 방식·같은 파일 모양.
- ① 구글에 로그인돼 있으면 사이트의 «Google 계정으로 계속»으로 — 코드 없음. ② 앱 안 브라우저의 로그인(쿠키·저장소)을 통째로 보관.
- **앱 안 브라우저는 따로 도는 프로세스 `:web`**(매니페스트) — `WebView.setDataDirectorySuffix("web")` 로 웹 데이터 폴더가
  `app_webview_web` 이 된다. 메인 프로세스는 그 폴더를 수업마다 바꿔 끼운다(WebView 가 떠 있는 프로세스에서는 폴더를 못 바꾼다).
- 수업 시작(`Session.prepare` → `AppHost.prepareWeb`): `:web` 을 닫고 폴더를 비운 뒤, 승인 때 서버가 준 열쇠(`handoff.profile {ref,key}`)로
  `files/vault/<ref>.bin` 을 풀어 넣는다. 수업 끝(`finishWeb`): `:web` 에 닫기 방송(`CLOSE_WEB` — 쿠키 flush·창 닫기·프로세스 끝) → 폴더를
  묶어(캐시 빼고, 150MB 상한) AES-256-GCM 으로 잠가 두고 폴더는 지운다. 열쇠가 없으면(보관 끔) 지우기만.
- **열쇠는 칠판에 없다** — 같은 선생님이 이 칠판에서 QR 로 승인할 때만 온다(서버 `classroom_profile_key`, 승인 화면 «이 기기에 로그인 보관»).
  학생이 칠판을 만져도 남은 것은 암호문뿐. 열쇠가 안 맞으면 보관 파일을 지우고 빈 브라우저. 60일 안 쓴 보관 파일은 켤 때 지운다.
- 구글 창 아래 «이 칠판 로그인 지우기» → 보관 파일·지금 브라우저 데이터를 지운다. 서버 열쇠·보관 모드는 그대로 — 지운 뒤 다시
  로그인하면 끝날 때 새로 보관한다(1.3.1~, Windows 1.5.5 와 같다. 1.3.0 은 서버 열쇠까지 지워 다시 한 로그인이 사라졌다).
- 구글 창 안내: 풀어 넣은 보관본에 구글 로그인 쿠키(SID 등, 만료 전)가 있나(`WebVault.googleLoginIn` — 이름·만료만)
  → «불러왔습니다» / «구글 로그인은 없었습니다». 앱 안 브라우저는 다른 프로세스라 수업 중 실시간 확인은 없다.
- **안드로이드 9+ 만**(폴더 접미사 API). 8 이하는 예전처럼 수업 끝에 지우기만.
- 스페이스기전 세션은 프로세스가 달라 Intent 대신 앱 전용 파일(`files/handoff/<uuid>.json`)로 넘기고 브라우저가 읽자마자 지운다.

## 휴대폰으로 입력 — 칸 찾기 고침 (2026-10-14, 1.3.0)

구글 로그인 화면의 이메일 칸은 `type=email` 이 아니라 `type=text`(`id=identifierId`, `name=identifier`)이고, 비밀번호 칸 앞에 숨은
`hiddenPassword` 가 있다(실제 화면 확인). 1.2.0 `fillScript` 는 `type=email` 만 찾아 이메일 단계를 못 넘겼다 → 보이는 칸만, 여러 이름으로.

## 1.1.0 (2026-10-14) — 구글 수업 도구

클래스룸·슬라이드 발표·설문지를 구글 로그인 없이 — Windows 판과 같은 화면(`app/web/gtools.*`, 빌드 때 복사)·같은 규칙(`GoogleApi.kt` = `core/google_tools.py`).
상세 `app/CLASSROOM.md` «구글 수업 도구». 🚨 Google Cloud 에서 Classroom · Slides · Forms API 를 켜야 한다.

## 1.0.3 (2026-10-14)

- **QR 화면 개편** — 쉬는 동안 늘 떠 있는 화면: 큰 시계·날짜, 이 칠판 이름, 세 단계 카드, QR 카드(다음 QR 까지 막대), 아래에 기기 설정·세팅 만들기 QR.
- **수업 화면 개편** — 타일을 가운데 크게(종류 글씨 뺌), 아래 줄에 세팅·선생님 · [열어 둔 파일 n개](누르면 드라이브) · 남은 시간 · +10분 · 수업 끝.
- **«null» 글자** — 반이 없는 세팅에서 `1-3 · null · 이름`으로 보이던 것. org.json `optString` 은 JSON null 을 "null" 로 준다 → `str()` 로 읽는다(Session.kt).
- **앱 안 브라우저는 PC 화면이 기본** — 앱 안 브라우저는 «휴대폰»으로 알려 큰 칠판에 휴대폰용 화면이 늘어나 보였다. PC Chrome 처럼 알리고
  아래 줄 [PC 화면/모바일 화면]으로 바꾼다(기억한다). 글자 크기 100% 고정, https 안의 http 그림 허용.
- **기기 설정에 웹 엔진 판** — 칠판의 Android System WebView 가 Chrome 100 미만이면 요즘 사이트가 깨질 수 있다고 알린다.

## Windows 판과 다른 점

- **사이트·구글 앱·스페이스기전은 앱 안 브라우저.** 수업이 끝나면 쿠키·저장소·캐시째 지운다 — 승인 때 «로그인 보관»을 켰으면
  잠가 두고(1.3.0, 위). 앱이 갑자기 끝났다 다시 켜져도 켤 때 지운다(그때는 보관하지 않는다).
- 🚨 **구글은 앱 안 브라우저(WebView)의 로그인을 막을 수 있다.** 사용자 에이전트를 일반 Chrome 처럼 바꿔 두었지만 막히면
  칠판에서는 구글 웹 로그인이 안 된다. 드라이브는 로그인 없이(QR 승인 때 받은 토큰) 앱 안 탐색기로 쓴다. **실기기 확인 필요.**
- **로그인 보관은 이 칠판 안에만**(1.3.0) — Windows 판은 PC 마다, 칠판은 칠판마다. 다른 기기로 옮겨 가지 않는다.
- **프로그램은 안드로이드 앱으로**: PowerPoint·Word·Excel(Microsoft 365 앱도), 한글, Whiteboard, 계산기. 메모장·그림판·캡처 도구·
  화상 키보드는 Windows 전용 — 타일이 흐리게 «이 칠판에 없음». 패키지를 늘리면 `AndroidManifest.xml` `<queries>` 에도.
- **드라이브 파일**은 받아서 칠판의 앱으로 연다(FileProvider). 앱이 고친 내용을 그 파일에 다시 쓰면 되올린다 — 앱에 따라
  «사본으로 저장»만 되는 것도 있다(그때는 되올릴 것이 없다). «기기에 저장»은 안드로이드 폴더 고르기(SAF)로.
- **다른 앱에서 돌아오기**: «다른 앱 위에 표시»를 허용하면 오른쪽에 «◀ 수업 화면» 단추가 뜬다(기기 설정 → 허용하기).
  이 허용이 있어야 **수업이 끝나면 QR 화면을 앞으로**도 된다(Android 10+ 의 뒤에서 화면 띄우기 제한).
- **«홈 화면으로 쓰기»·«칠판을 켜면 바로 실행»은 없다**(2026-10-14 요청으로 1.0.2 에서 뺐다). 칠판의 홈·시작 동작을 건드리지 않는다 —
  칠판을 켠 뒤 앱 목록에서 «스페이스기전 교실»을 연다. 1.0.0·1.0.1 에서 켜 두었던 것도 새 판으로 바꾸면 사라진다.

## 빌드 · 배포

```
python deploy/classroom-android/build.py              # 시험 → 서명된 APK → dist/SpacekijunClassroom.apk
python deploy/classroom-android/build.py --publish    # 자동 업데이트로 올리기(관리자 계정 로그인)
```

- 빌드 도구: `%LOCALAPPDATA%\SpacekijunAndroidBuild` (JDK 17 · Android SDK 35 · Gradle 8.10). 처음 한 번 그 폴더의 `setup.sh`.
- **판 번호**: `app/build.gradle.kts` 의 `versionCode`(정수, 자동 업데이트가 견준다)와 `versionName` — 둘 다 올린다.
- **서명 키**: `.secrets/classroom-android.jks` + 암호 `.secrets/classroom-android.pass`(DPAPI). 🚨 잃으면 칠판에 깐 앱을
  새 판으로 덮어쓸 수 없다(지우고 새로 깔아야 한다). 따로 보관할 것.
- **올리는 곳**: Storage `desk-releases/classroom-android/` — `latest.json`(versionCode·sha256·인증서) · `SpacekijunClassroom-<판>.apk` ·
  처음 깔 때 쓰는 고정 주소 `SpacekijunClassroom.apk`.
- **자동 업데이트**: 켜고 90초 뒤·30분마다 받아 두고(SHA-256 확인), QR 화면에 [새 판 설치]. 설치 창은 사람이 눌러야 한다
  (기기 관리자 앱이 아니면 안드로이드가 묻지 않고 설치하지 못한다). 처음 한 번 «이 출처 허용». 위조 APK 는 서명 키가 달라 설치가 거부된다.

## 처음 깔기(칠판마다 한 번)

1. 칠판 브라우저로 `https://your-project-ref.supabase.co/storage/v1/object/public/desk-releases/classroom-android/SpacekijunClassroom.apk`
   를 받아 연다(«알 수 없는 앱 설치» 허용).
2. 앱을 열고 [기기 설정] → 기기 이름(예: 2-3 교실) · **다른 앱 위에 표시 허용하기**.

## 검증

- `./gradlew testDebugUnitTest` — 흐름(QR·승인·거절·끊김·시간 끝·휴대폰에서 끝·드라이브 다시 연결·연장)·드라이브(되올리기·
  구글 문서 사본·못 올린 파일 상자·권한 오류)·QR.
- 화면: `assets/web/board.html` 을 브라우저로 열고 `window.AndroidBridge.invoke` 를 가짜로 넣어 본다(가짜 상태·파일 목록).
