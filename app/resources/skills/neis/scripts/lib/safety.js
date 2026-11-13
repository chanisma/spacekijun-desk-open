/**
 * 버튼이 무엇을 하는가 — 이름으로 추정한다. 자동화의 안전선이 여기 걸린다.
 *   read(조회) · export(출력·내려받기) · navigate(이동) 만 스스로 누르고,
 *   write(자료를 바꿈)는 누르지 않는다. **모르면 write 로 본다**(안전한 쪽으로 틀린다).
 * 쓰기 규칙을 먼저 본다 — `조회취소`·`출력설정저장` 같은 합성어가 뒤 규칙에 먹히지 않게.
 */
const RULES = [
  [/저장|삭제|마감|확정|반영|등록|생성|이관|전송|상신|승인|반려|추가|일괄|부여|배정|편성|적용|해제|복사|가져오기|올리기|초기화|채점|산출|정정|변경|수정|입력|처리|요청|접수|취소|발급|연계|재연계|잠금/, 'write'],
  [/출력|엑셀|다운로드|내려받기|인쇄|미리보기|PDF|한글/i, 'export'],
  [/조회|검색|찾기|보기|확인$|현황|통계/, 'read'],
  [/닫기|이전|다음|펼치기|접기|전체화면|축소|확대|도움말|질의응답|FAQ|연락처|온라인컨텐츠|즐겨찾기/i, 'navigate'],
];
const LABEL = { read: '조회', export: '출력·내려받기', navigate: '이동', write: '자료를 바꿈' };

function buttonEffect(label) {
  const text = String(label || '').replace(/\s+/g, '');
  for (const [re, effect] of RULES) if (re.test(text)) return effect;
  return 'write';
}

/** 누르면 안 되는 버튼이면 오류 */
function assertSafe(label) {
  const e = buttonEffect(label);
  if (e === 'write') throw new Error(`[${label}] 은(는) 자료를 바꿀 수 있는 버튼이라 누르지 않습니다(조회 전용). 사람이 직접 누르세요.`);
  return e;
}

module.exports = { buttonEffect, assertSafe, EFFECT_LABEL: LABEL };
