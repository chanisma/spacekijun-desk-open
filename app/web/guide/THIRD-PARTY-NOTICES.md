# 출처와 라이선스 (Third-Party Notices)

이 저장소(샘플고등학교 수업 자료 허브)는 세 개의 외부 프로젝트에 기대고 있다.
하나는 코드를 그대로 가져다 쓰고, 하나는 설계 원칙과 문서를 옮겨 왔고, 하나는 저장소
밖에서 영상을 구워 그 결과물만 받아 온다. 이 문서는 **무엇을 어디에서 가져왔고, 그에
따라 무엇을 지켜야 하는지**를 기록한다.

마지막 대조: 2026-08-22 (상류 저장소 main 기준)

이 저장소 자체의 라이선스는 둘로 나뉜다 — 코드는 MIT(`LICENSE`), 수업 자료는
CC BY-NC-SA 4.0(`LICENSE-CONTENT.md`). 아래는 **외부에서 들어온 것**에 대한 기록이다.

## 요약

| 프로젝트 | 라이선스 | 이 저장소와의 관계 | 지켜야 할 것 |
|---|---|---|---|
| [stackblitz/bolt-slides](https://github.com/stackblitz/bolt-slides) | MIT | **코드를 직접 반입** — 덱 엔진·크롬·슬라이드 컴포넌트·스타일 | 저작권 고지와 라이선스 전문을 함께 배포 (아래 §1에 전문 수록) |
| newVideoGen (로컬 프로젝트, `E:\newVideoGen`) | 표기 없음 | **설계 원칙·스킬 문법을 이식** + 일부 에셋 반입 | 각 문서에 원본 표기 유지, 공개 전 권리 관계 확인 (§2) |
| [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0 | **저장소 밖 도구** — 영상 렌더만 맡기고 산출물(mp4)만 반입 | 코드·스킬 문서를 이 저장소로 복사하지 않기 (§3) |

---

## 1. bolt-slides — 덱 엔진의 원본

> Use any agent to create stunning, interactive presentations
> — https://github.com/stackblitz/bolt-slides

이 저장소의 프레젠테이션 엔진은 bolt-slides를 **복사해 와서 그 위에 얹은 것**이다.
슬라이드를 넘기는 방식, 떠 있는 독과 썸네일 레일, 클릭 빌드, 프레젠터 화면, 슬라이드
컴포넌트 26종, 전체 CSS가 모두 상류에서 왔다. 새로 만든 것이 아니라 **가져온 것**이다.

### 반입 범위

상류 `src/` 39개 파일이 이 저장소에 그대로 들어와 있고, 그중 **33개는 바이트 단위로
동일**하며 6개만 이 저장소 사정에 맞게 고쳤다.

| 경로 | 상태 | 비고 |
|---|---|---|
| `src/deck/{Slide,Build,Reveal,DeckContext,useInView}.*` | 원본 그대로 | 엔진 핵심 |
| `src/deck/{Deck,Annotator,icons}.tsx` | 수정 | 라이브 세그먼트·레거시 뷰어 연동으로 `Deck.tsx`는 546줄 → 1037줄 |
| `src/components/*.tsx` (26종) | `Charts.tsx`만 수정, 나머지 원본 그대로 | Cover·Split·Steps·Timeline 등 |
| `src/styles/base.css` | 원본 그대로 (2832줄) | CLAUDE.md의 "수정 금지" 영역 |
| `src/styles/tokens.css` | 수정 | 이 저장소 테마 토큰 |
| `src/App.tsx` · `src/main.tsx` | 수정 | 라우팅을 이 저장소 SPA 구조로 교체 |
| `index.html` · `vite.config.ts` · `tsconfig*.json` | 대부분 수정 | `tsconfig.node.json`은 원본 그대로 |
| `.claude/skills/react-deck-builder/references/bolt-authoring.md` | **원본 그대로** | 상류 `.bolt/skills/slides/SKILL.md`의 복사본 |

이 저장소가 **추가한** 부분(상류에 없는 것): `src/deck/{Capture,Notes}.tsx`,
`src/components/{HtmlSlide,KenBurns,SceneVideo,Terminal}.tsx`, 그리고
`src/{scene,composite,hub,legacy,live,decks,vox,diorama,whiteboard,watercolor,walkthrough}/`
전부. 라이브 레이어·허브·레거시 뷰어·씬 런타임은 이 저장소에서 만든 것이다.

### MIT 라이선스 전문

MIT 라이선스는 "저작권 고지와 이 허가 문구를 소프트웨어의 복사본 전체 또는 상당 부분에
포함할 것"을 요구한다. 아래가 상류 `LICENSE` 전문이며, 이 문서에 수록함으로써 그 조건을
충족한다.

```
MIT License

Copyright (c) 2026 StackBlitz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 이 저장소가 지키는 방법

- 위 전문을 이 문서에 보관하고, README에서 여기로 연결한다.
- CLAUDE.md의 **"수정 금지 영역"**(`src/deck/`, `src/styles/base.css`)은 원래 엔진을
  깨뜨리지 않으려는 규약이지만, 결과적으로 상류 코드를 원형 그대로 유지하는 역할도 한다.
- 상류에서 갱신을 가져올 때는 위 표의 "수정" 파일만 손으로 병합하면 된다.

---

## 2. newVideoGen — 씬 문법과 스킬 설계의 원본

`E:\newVideoGen`에 있는 Remotion 기반 영상 생성 프로젝트. 공개 저장소가 아니고, 폴더
안에 LICENSE 파일이나 저작권 표기가 없다(2026-08-22 확인). 따라서 **권리 관계를 이
문서에서 단정하지 않는다** — 아래 "확인이 필요한 부분"을 참고할 것.

### 반입 범위 — 코드가 아니라 규칙과 문법

가져온 것은 소스 코드가 아니라 **씬을 어떻게 설계할 것인가에 대한 규칙 문서**다.
영상(Remotion)이라는 매체에서 만들어진 원칙을 슬라이드덱이라는 다른 매체로 다시 쓴 것이며,
각 문서는 이미 첫머리나 끝에 원본 표기를 달고 있다.

| 이 저장소 | 원본 |
|---|---|
| `.claude/rules/scene-grammar.md` | newVideoGen `.claude/rules/scene-grammar.md` v2.x |
| `.claude/skills/dynamic-scene-builder/references/scene-philosophy.md` | 같은 프로젝트의 씬 설계 원칙 |
| `.claude/skills/diorama-deck-builder/references/diorama-grammar.md` | `/vg-diorama` v2.2 |
| `.claude/skills/vox-collage-deck-builder/references/collage-grammar.md` | `/vg-vox` v1.3 |
| `.claude/skills/whiteboard-deck-builder/references/whiteboard-grammar.md` | `/vg-whiteboard` v2.8 (rough-kit) |
| `.claude/skills/watercolor-deck-builder/SKILL.md` | `/vg-watercolor-motion` |
| `.claude/skills/svg-asset-builder/SKILL.md` | `vg-sketch` |
| `.claude/skills/image-asset-builder/SKILL.md` | `vg-story` Phase 3 + scene-grammar §17 |
| `.claude/skills/asset-library/SKILL.md` | `vg-assets` |
| `.claude/skills/lesson-deck-planner/SKILL.md`의 디자인 철학 절 | newVideoGen `CLAUDE.md` |
| `.claude/skills/lesson-script-planner/SKILL.md` | `/vg-script` + `/vg-chunk` + `/vg-scene`의 순서와 게이트 |
| `.claude/skills/pd-script/SKILL.md` | `/vg-script` — 대본 작성 7원칙·구조·스키마 그대로, 길이 단위만 분→장 |
| `.claude/skills/pd-chunk/SKILL.md` + `references/beats-schema.md` | `/vg-chunk` Step 3 (3a~3f 연출 메타·트리거 표·SPLIT-FIRST) 그대로, SRT 타임코드→문장 번호 |
| `.claude/skills/pd-scene/SKILL.md` + `references/pattern-catalog.md` | `/vg-scene` (visual_plan·semantic cluster·dedup·sketch 4조건) + `src/services/pattern-catalog.ts` 39종을 어휘표로 |

### 반입 범위 — 원문 그대로 (각색 아님)

위 표는 매체를 옮기며 **다시 쓴** 문서들이다. 아래 셋은 다르다 — 원본 파일을
**한 바이트도 고치지 않고** 그대로 두었다. 각색본과 원문을 나란히 놓아야
무엇을 바꾸고 무엇을 버렸는지 대조할 수 있기 때문이다.

| 이 저장소 | 원본 | 크기 |
|---|---|---|
| `.claude/skills/lesson-script-planner/references/vg-script.md` | `/vg-script` | 4,488바이트 |
| `.claude/skills/lesson-script-planner/references/vg-chunk.md` | `/vg-chunk` | 23,009바이트 |
| `.claude/skills/lesson-script-planner/references/vg-scene.md` | `/vg-scene` | 28,173바이트 |

폴더의 성격과 대조표는 `.claude/skills/lesson-script-planner/references/README.md`.
(같은 관례로 `react-deck-builder/references/bolt-authoring.md`도 상류 원문 그대로다.)

**공개 전 확인 항목이 하나 늘었다** — 각색본은 "원본 표기를 유지"하는 것으로 족하지만,
원문 반입은 newVideoGen의 권리 관계가 확정돼야 한다. 아래 체크리스트 첫 항목이
정리되면 이 셋도 같이 정리된다.

### 반입 범위 — 에셋

`assets/manifest.json`에서 `origin: "newvideogen"`으로 기록된 항목이 **61개**이며,
실제 파일은 `assets/external/` 아래에 있다. 이 항목들은 newVideoGen이 만든 창작물이
아니라 **그 프로젝트가 모아 두었던 제3자 자료**(서비스 로고·아이콘·배경 사진 등)가
대부분이다 — `anthropic.svg`, `openai.png`, `fastapi.png`, `nextjs.svg`,
`assets/external/BG/*.jpg`, `assets/svg/템플릿*.svg` 등.

즉 여기서 물어야 할 것은 "newVideoGen에서 가져와도 되는가"가 아니라 **"그 파일들이
원래 누구 것인가"**다.

### 확인이 필요한 부분 (저장소 공개 전)

- [ ] newVideoGen 자체의 권리 관계 한 줄 확정 — 같은 사람이 만든 프로젝트라면 그렇게
      적으면 끝난다.
- [ ] `assets/external/`의 서비스 로고·아이콘: 수업에서 그 서비스를 가리키는 용도라면
      통상 문제되지 않지만, 상표는 상표대로 각 사의 브랜드 가이드가 있다.
- [ ] `assets/external/BG/*.jpg`, `assets/svg/템플릿*.svg`: 출처가 기록돼
      있지 않다. 출처를 찾아 `manifest.json`의 `license` 필드에 적거나, 대체하거나,
      빼는 편이 안전하다.
- [ ] `manifest.json`에 있으나 **파일이 없는 항목 9개** (`assets/external/characters/smurf/*.png`).
      실제 파일은 저장소에 없으므로 매니페스트 항목만 지우면 된다.

---

## 3. OpenMontage — 필름 덱의 렌더 도구 (저장소 밖)

> World's first open-source, agentic video production system
> — https://github.com/calesthio/OpenMontage · https://www.openmontage.video/
> 라이선스: **GNU Affero General Public License v3.0 (AGPL-3.0)**

`film-deck-builder` 스킬이 만드는 "필름 덱"은 페이지 전체가 미리 구운 mp4 1편이다.
그 mp4를 렌더하는 것이 OpenMontage(`remotion-composer`)이고, 이 프로젝트는 **이
저장소의 일부가 아니다.** 별도로 설치돼 있어야 하며, 없는 PC에서는 필름 덱을 만들 수
없다(스킬이 시작 전에 존재를 확인하고, 없으면 React 렌더러로 대체한다).

### 반입된 것은 산출물뿐

이 저장소에 들어와 있는 OpenMontage 관련 파일은 **렌더 결과 mp4 6편과 그 포스터**가
전부다(`assets/manifest.json`의 `origin: "openmontage"`).

```
data/dev/테스트 수업 자료/영상-에셋-데모/media/{loop-script,scrub-notice,step-decree}.mp4
data/dev/테스트 수업 자료/전주-영상-콜라주/media/{city,culture,tenmillion}.mp4
```

AGPL-3.0은 프로그램의 **출력물**을, 그 출력물이 프로그램 자체를 담고 있지 않은 한
라이선스 대상으로 삼지 않는다(AGPL-3.0 §0). 렌더된 mp4는 영상 프레임일 뿐 OpenMontage
코드를 포함하지 않으므로, 이 저장소가 AGPL을 이어받지 않는다. 영상에 실린 시각 문법과
컴포지션 설계는 이 저장소·newVideoGen 쪽 문법이다.

### AGPL 경계선 — 넘지 말아야 할 선

AGPL은 강한 카피레프트다. **OpenMontage의 코드가 이 저장소로 들어오는 순간** 그 파생물
전체를 AGPL로 공개해야 하는 문제가 생긴다. 그래서 다음을 규칙으로 둔다.

- ❌ OpenMontage의 소스·스킬 문서·설정 파일을 이 저장소로 복사하지 않는다.
- ❌ `remotion-composer`의 컴포지션(`JeonjuVox.tsx`, `PacketVox.tsx` 등)을 이 저장소로
  옮기지 않는다 — 저작은 OpenMontage 쪽 작업 폴더에서 하고, 이쪽으로는 mp4만 가져온다.
- ✅ 이 저장소가 가지는 것: 렌더된 mp4·poster, 그리고 그것을 재생하는
  `src/components/SceneVideo.tsx`(이 저장소에서 작성).
- ✅ `film-deck-builder` 스킬 문서는 "OpenMontage를 어떻게 호출할 것인가"를 적은 이
  저장소의 절차서이며, OpenMontage 문서의 복사본이 아니다.

### 곁들여 — Remotion

OpenMontage는 [Remotion](https://www.remotion.dev)으로 렌더한다. Remotion은 자체
라이선스를 쓰며 개인·소규모 회사·**비영리 단체**에는 무료다(공립학교의 수업 자료
제작은 여기에 해당한다). 회사 규모가 커지면 별도 라이선스가 필요하다 —
https://github.com/remotion-dev/remotion/blob/main/LICENSE.md

---

## 4. 코드 의존성

| 이름 | 라이선스 | 위치 |
|---|---|---|
| React · React DOM | MIT | npm |
| framer-motion | MIT | npm (덱 모션) |
| Vite · @vitejs/plugin-react | MIT | npm |
| modern-screenshot | MIT | npm (썸네일 캡처) |
| TypeScript · Playwright | Apache-2.0 | npm (개발·테스트) |
| supabase-js (`live/vendor/supabase.umd.js`) | MIT | 저장소에 직접 담아 서빙 |
| QR Code Generator for JavaScript (`live/vendor/qrcode.js`) | MIT · Copyright (c) 2009 Kazuhiko Arase | 저장소에 직접 담아 서빙 |
| three.js r169 (`assets/vendor/three/three.module.min.js`) | MIT · Copyright 2010-2024 Three.js Authors | 저장소에 직접 담아 서빙 (3D 모형 수업 자료) |

`live/vendor/`의 두 파일은 CDN이 막힌 학교망에서도 라이브 수업이 돌아가게 하려고 직접
담아 둔 것이다. 두 파일 모두 MIT이며, `qrcode.js`는 파일 첫머리에 저작권 고지가 그대로
살아 있다.

`assets/vendor/three/`는 3D 모형형 수업 자료(확산 모델 3D 모형 등)가 `<script type="module">`로
불러 쓰는 three.js 공식 빌드다. npm `three@0.169.0` 패키지의 `build/three.module.min.js`와
`LICENSE`를 그대로 담았고, 파일 첫머리의 저작권 고지도 살아 있다. 자료 안에 라이브러리를
인라인하지 않고 한 곳에서 공유하는 것은 학교망(CDN 차단)에서도 돌아가게 하려는 같은 이유다.

웹폰트(Noto Sans KR·Nanum·Gowun Batang·Pretendard)는 저장소에 담지 않고 Google Fonts
등에서 불러 쓴다. 모두 오픈 폰트 라이선스(OFL) 계열이다.

---

## 5. 수업 자료 안의 이미지와 영상

`assets/manifest.json`이 재활용 에셋의 출처를 `origin` 필드로 기록한다(2026-08-22 기준
172항목).

| `origin` | 개수 | 성격 |
|---|---|---|
| `generated` | 69 | 이 저장소에서 생성한 이미지·SVG (image-asset-builder / svg-asset-builder) |
| `newvideogen` | 61 | §2 참조 — 출처 점검 대상 |
| `notebooklm` | 23 | NotebookLM으로 만든 수업 슬라이드 이미지 |
| `external` | 13 | 외부에서 가져온 사진 — **전부 `license` 필드에 출처가 적혀 있다** |
| `openmontage` | 6 | §3 참조 — 렌더 산출물 mp4 |

`origin: "external"` 13개는 대부분 위키미디어 공용의 CC 라이선스 사진이며, 매니페스트에
라이선스·저작자·원본 파일명이 함께 기록돼 있다. 예:

```
CC BY-SA 4.0 · Wesalius · Wikimedia Commons (File:Lee Sedol (B) vs AlphaGo (W) - Game 4.jpg)
Public domain · NASA · Wikimedia Commons (File:Photo of typhoon nanmadol from international space station.jpg)
```

**새 사진을 수업 자료에 넣을 때는 이 형식으로 `license` 필드를 반드시 채운다.** CC BY·
CC BY-SA는 저작자 표시가 의무이므로, 슬라이드에도 출처를 함께 싣는다.

---

## 6. 저장소를 공개하기 전 점검 목록

- [x] **이 저장소 자체의 라이선스 결정** (2026-08-22 완료) — 코드는 MIT(`LICENSE`,
      Copyright (c) 2026 chanisma), 수업 자료는 CC BY-NC-SA 4.0(`LICENSE-CONTENT.md`).
      상류 bolt-slides가 MIT이므로 코드 쪽은 그대로 호환된다.
- [ ] §2의 newVideoGen 권리 관계 확정, `assets/external/` 출처 점검, 유령 항목 9개 정리
- [ ] `data/` 안에 학생 이름·제출물·개인정보가 남아 있지 않은지 확인
- [ ] Apps Script 웹앱 URL·공유 토큰·시트 ID가 커밋에 들어가 있지 않은지 확인
      (`.classroom.json`, `.env`는 이미 gitignore 대상)
- [ ] `supabase/migrations/`의 키·URL 노출 여부 확인
