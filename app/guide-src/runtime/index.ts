/**
 * Walkthrough 런타임 — 프로그램 절차를 "말"이 아니라 "화면 시연"으로 보여 주는 엔진.
 *
 * presentation 프로젝트의 `software-walkthrough-builder` 스킬이 쓰는 것과 **같은 역학**이라,
 * 저쪽에서 저작한 씬 코드를 거의 그대로 옮겨 올 수 있다. 이 저장소가 가져온 것은
 * **역학뿐**이고 덱 엔진(네비게이션·썸네일·발표자 모드·export)은 가져오지 않았다 —
 * 여기서 필요한 것은 "모달에 절차 한 편을 재생" 이지 발표 도구가 아니다.
 *
 * ── 저작 규칙 요약 (자세히는 presentation 의 스킬 문서) ─────────────────────
 *  · 모든 모션은 `useSceneTime()` t 의 **순수 함수**여야 한다(같은 t = 같은 화면)
 *  · 국면 시각은 **이름 있는 상수**로 컴포넌트 상단에 모은다 — 포인터·창·타이핑이 공유
 *  · 목업은 실물을 베끼지 않고 **랜드마크 3~5개**만(로고·핵심 버튼·주소·구조 하나)
 *  · 지나간 창은 `dimAfter` 로 물리고 현재 창만 밝게 — 시선 유도
 *  · 창이 2개 이상이면 배지 ①②③ 로 순번을 말한다
 *  · 마지막 국면은 **성공 판정 화면**(✓·완료 상태)으로 끝낸다
 */
export {
  Scene, useSceneTime, interpolate, easeOut, easeInOut, spring, riseIn,
} from './scene';

export {
  Pointer, clickFlash, typed, typedDoneAt, Caret, popIn, dimAfter, AppWindow,
  type CursorKey, type WindowKind,
} from './mechanics';
