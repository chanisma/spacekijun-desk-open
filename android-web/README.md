# 스페이스기전 웹앱 — 안드로이드 TWA

`https://spacekijun.lovable.app` 을 휴대폰 앱처럼. **TWA(Trusted Web Activity)** — 앱 안에 웹 화면을 넣는 것이 아니라
휴대폰의 Chrome 이 주소창 없이 사이트를 띄운다. 그래서 구글 로그인·Web Push 알림·파일 받기·`window.open` 이 웹과 똑같다.
Java/Kotlin 코드는 없다 — `androidbrowserhelper` 의 `LauncherActivity` 를 매니페스트 설정만으로 쓴다.

최종 확인: 2026-10-18 (1.0.0) — 빌드·서명·매니페스트(`aapt2 dump`)까지. **실기기 확인 전.**

## 왜 WebView 가 아니라 TWA 인가

- 🚨 사이트 로그인은 Supabase 구글 로그인(`signInWithOAuth`, `hd=myschool.hs.kr`)이다. **구글은 앱 안 WebView 의 로그인을 막는다**
  (`403 disallowed_useragent`). 교실판(`android/`)은 QR 승인으로 받은 세션을 심어 피하지만 범용 앱에는 그 길이 없다.
- 그래서 `FALLBACK_STRATEGY = customtabs` — Chrome(또는 TWA 를 하는 브라우저)이 없으면 Custom Tab(주소창 있는 Chrome 탭)으로.
  `webview` 로 바꾸면 로그인이 안 된다.

## 주소창이 사라지는 조건 — assetlinks

앱과 사이트가 서로를 가리켜야 한다. 하나라도 어긋나면 **동작은 하지만 위에 주소창이 남는다.**

| 쪽 | 자리 | 내용 |
|---|---|---|
| 앱 | `res/values/strings.xml` `asset_statements` | `https://spacekijun.lovable.app` |
| 사이트 | spacekijun `public/.well-known/assetlinks.json` | 패키지 `kr.hs.kijun.spacekijun` + 서명 인증서 SHA-256 |

- 확인: `https://spacekijun.lovable.app/.well-known/assetlinks.json` 이 JSON 으로 열려야 한다.
  2026-10-18 spacekijun `10024602` 로 올리고 Lovable Publish → 200 `application/json`, 구글 `assetlinks:check` 가 `linked: true`.
  **Lovable 은 `public/.well-known/` 도 배포한다**(점 폴더라도). Publish 뒤 반영까지 약 3분.
- 구글 확인 도구: `https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://spacekijun.lovable.app&relation=delegate_permission/common.handle_all_urls`
- 구글 로그인 화면(`accounts.google.com`)·Supabase 처럼 **다른 사이트로 나갈 때는 주소창이 잠깐 보이는 것이 정상**이다.
- 사이트 주소를 바꾸면 `app/build.gradle.kts` 의 `host` · `strings.xml` · 새 사이트의 assetlinks 셋 다.

## 빌드

```
python deploy/web-android/build.py                                                     # → dist/SpacekijunWeb.apk
python deploy/web-android/build.py --assetlinks D:/spacekijun/public/.well-known/assetlinks.json
```

- **배포 (2026-11-10)**: `python deploy/web-android/build.py --publish`(빌드하고 올림) · `--publish-only`(dist 의 APK 를 판 번호·서명 확인 뒤 올림)
  → Storage `desk-releases/web-android/`(SpacekijunWeb-<판>.apk · SpacekijunWeb.apk · latest.json, 교실판과 같은 모양).
  spacekijun «PC 앱» 페이지(`/desktop-app`, `src/lib/androidApps.ts`)가 이 목록으로 받기 단추를 그린다. 1.0.0 을 2026-11-10 올림.
  🚨 버킷이 `application/vnd.android.package-archive` 를 받지 않아 `application/octet-stream` 으로 올린다. 같은 판 번호로 다른 파일은 거절.
- 빌드 도구·방식은 교실판과 같다(`%LOCALAPPDATA%\SpacekijunAndroidBuild`).
- **판 번호**: `app/build.gradle.kts` 의 `versionCode`·`versionName` — 둘 다 올린다. 사이트를 고치는 것은 앱을 다시 낼 필요가 없다.
- **서명 키**: `.secrets/web-android.jks` + `.secrets/web-android.pass`(DPAPI). 🚨 잃으면 깐 앱을 덮어쓸 수 없고 assetlinks 지문도 바꿔야 한다.
- Play 스토어에 올리면 구글이 다시 서명한다 — 그때는 Play Console «앱 서명» 인증서 지문을 assetlinks 의 `sha256_cert_fingerprints` 에 **추가**한다.

## 아이콘

사이트 `public/logo_sm.png`(73×73, 흰 바탕 불투명)를 키워 만들었다 — 흐리다. 큰 원본이 생기면 바꿀 것.
적응형 아이콘(`mipmap-anydpi-v26`, 흰 바탕 + `drawable-nodpi/ic_launcher_foreground.png`), 옛 런처용 `mipmap-*/ic_launcher.png`,
시작 화면 `splash.png`, 알림 작은 아이콘 `ic_notification.png`(흰색이 아닌 곳의 흰 실루엣).
