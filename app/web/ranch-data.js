// 별사이 목장 — 생물·품질·시설·상점·방문자·대사 (2026-11-06, 뼈대 개편: 참고 게임 Tiny Pasture 의 구조).
// 규칙은 ranch.js, 설계는 docs/plans/2026-11-06-byeolsai-ranch.md §6
// 그림: ranch/sprites/<sheet>.png — 자세 다섯 칸(가만히·기쁨·먹기·잠·시무룩), 소품은 items.png 한 장 (scripts/ranch-art/build.py)
'use strict';

window.RANCH_DATA = (() => {
  // 동물 — income = 어른이 «흐린» 품질일 때 1분에 쌓는 조각, price = 뽑기 한 번 값, grow = 어른까지 건강하게 지낼 분
  // unlock: 처음부터 / adult(어른을 키운 마리 수) / earned(모은 조각 누계) / species(그 종을 어른으로)
  // 동물 — income = 어른이 «흐린» 품질일 때 1분에 쌓는 조각, price = 뽑기 한 번 값, grow = 어른까지 건강하게 지낼 분
  // size = [아기, 어른] 화면 키(목장 그림 칸) — 참고 게임처럼 종마다 다르다(2026-11-06). 그림 = <id>_adult · <id>_baby (옆모습, 오른쪽을 봄)
  // unlock: 처음부터 / adult(어른을 키운 마리 수) / earned(모은 조각 누계) / species(그 종을 어른으로) / tier(그 품질 이상을 얻기)
  const SPECIES = [
    {id: 'rabbit', name: '토끼', baby: '아기 토끼', price: 20, income: 1, grow: 15, size: [14, 21], origin: '풀밭 세계', speed: 18},
    {id: 'chick', name: '닭', baby: '병아리', price: 45, income: 1.6, grow: 15, size: [11, 19], origin: '풀밭 세계', speed: 14, unlock: {adult: 1}},
    {id: 'duckling', name: '오리', baby: '아기 오리', price: 100, income: 2.5, grow: 20, size: [12, 18], origin: '물에 잠긴 세계', speed: 13, unlock: {earned: 300}},
    {id: 'lamb', name: '양', baby: '아기 양', price: 220, income: 4, grow: 25, size: [15, 22], origin: '풀밭 세계', speed: 13, unlock: {adult: 3}},
    {id: 'kitten', name: '고양이', baby: '아기 고양이', price: 450, income: 6.5, grow: 30, size: [15, 22], origin: '주식회사 이세계 옥상', speed: 17, unlock: {earned: 2000}},
    {id: 'puppy', name: '강아지', baby: '아기 강아지', price: 900, income: 10, grow: 30, size: [16, 23], origin: '주식회사 이세계 경비실', speed: 19, unlock: {species: 'kitten'}},
    {id: 'fox', name: '여우', baby: '아기 여우', price: 1800, income: 16, grow: 40, size: [18, 26], origin: '별빛 숲', speed: 20, unlock: {earned: 12000}},
    {id: 'alpaca', name: '알파카', baby: '아기 알파카', price: 3500, income: 25, grow: 45, size: [22, 34], origin: '구름 고원', speed: 12, unlock: {adult: 10}},
    // 특수 캐릭터 — 다마고찌에서 학생 의뢰로 태어난 아이들(spacekijun 다마고찌 가챠 그림 그대로). 참고 게임의 협업 캐릭터처럼
    // 한 가지 모습으로 온다: 아기 단계·품질 뽑기·번식이 없다
    {id: 'scarfpigeon', name: '겨울을 기다리는 둘기', sheet: 'char_scarfpigeon', price: 7000, income: 40, size: [22, 22], origin: '별빛 아카데미 우편국 지붕', speed: 15, special: true, unlock: {earned: 60000}},
    {id: 'blackcat', name: '검은 고양이', sheet: 'char_blackcat', price: 11000, income: 58, size: [24, 24], origin: '다마고찌 펫 집 뒷골목', speed: 17, special: true, unlock: {species: 'scarfpigeon'}},
    {id: 'moonmoth', name: '은빛 달의 정령', sheet: 'char_moonmoth', price: 16000, income: 80, size: [28, 28], origin: '창가의 하늘', speed: 12, special: true, fly: true, unlock: {tier: 4}},
  ].map((s) => ({...s, sheet: s.sheet || `${s.id}_adult`, babySheet: s.special ? (s.sheet || `${s.id}_adult`) : `${s.id}_baby`}));


  // 품질 — 틈을 건너올 때 묻혀 온 빛. 높을수록 빨리 쌓는다. 무지개만 번식 상한이 없다(참고 게임과 같음)
  const TIERS = [
    {id: 0, name: '흐린', color: '#a7a19a', mult: 1, chance: 0.6, note: '틈의 그늘에서 왔어요.'},
    {id: 1, name: '물빛', color: '#7fc4e6', mult: 1.6, chance: 0.25, note: '물에 잠긴 세계의 물결이 털끝에 남아 있어요.'},
    {id: 2, name: '별빛', color: '#ffd24a', mult: 2.6, chance: 0.1, note: '별이 된 펫들의 빛을 조금 묻혀 왔어요.'},
    {id: 3, name: '노을', color: '#f06a5b', mult: 4.2, chance: 0.04, note: '주식회사 이세계의 퇴근길 노을빛이에요.'},
    {id: 4, name: '무지개', color: 'rainbow', mult: 7, chance: 0.01, note: '세계와 세계 사이, 틈 그 자체의 빛이에요. 번식 상한이 없어요.'},
  ];
  const BREED_CAP_TIER = 3;           // 무지개가 아닌 부모의 새끼는 노을 품질의 수익까지만

  const STAGES = [
    {id: 'baby', name: '아기', scale: 0.62},
    {id: 'adult', name: '어른', scale: 1},
  ];

  // 시설 — 레벨을 올리면 더 잘 일한다. cost[i] = i+1 레벨로 올리는 값
  const FACILITIES = {
    broom: {name: '마법 빗자루', icon: 'broom', from: '별빛 아카데미 청소 도구함',
      note: '목장의 똥을 저절로 치워요.', cost: [300, 1500, 6000, 20000, 60000],
      every: [90, 60, 40, 25, 15]},                       // 초마다 똥 하나
    feeder: {name: '전서구 급식함', icon: 'pigeonbox', from: '전서구 우편국',
      note: '배고픈 동물 곁에 먹이 창고의 먹이를 떨어뜨려요.', cost: [500, 2500, 9000, 30000, 90000],
      every: [120, 80, 50, 30, 20]},
    jar: {name: '반딧불 채집통', icon: 'jar', from: '별빛 숲',
      note: '쌓아 둔 조각이 가득 찬 동물에게서 조각을 대신 받아 와요.', cost: [800, 4000, 15000, 50000, 150000],
      every: [180, 120, 80, 50, 30]},
    curtain: {name: '별빛 장막', icon: 'curtain', from: '창가의 하늘',
      note: '같은 종 어른 둘이 들어가면 새끼가 나와요. 새끼의 수익 = 부모 수익의 합.', cost: [1500, 6000, 20000, 60000, 180000],
      minutes: [30, 22, 15, 10, 6]},
  };

  const SLOTS = {start: 3, max: 20, cost: (n) => Math.round(60 * Math.pow(2.4, n - 3))};   // n 번째 칸(4번째부터)
  const LENGTH = {start: 560, step: 160, cost: (k) => 200 * Math.pow(3, k)};               // k 번째 넓히기

  // 상점 물건 — food(창고에 더하기) · cure(치료제) · deco(놓는 것)
  const GOODS = [
    {id: 'food10', kind: 'food', name: '먹이 10개', icon: 'food', price: 10, amount: 10, note: '빈 땅을 누르면 하나씩 떨어뜨려요.'},
    {id: 'food50', kind: 'food', name: '먹이 50개', icon: 'food', price: 40, amount: 50, note: '조금 싸요.'},
    {id: 'cure', kind: 'cure', name: '치료제', icon: 'medicine', price: 30, amount: 1, note: '동물의 건강을 50 올려요.'},
    {id: 'fence', kind: 'deco', name: '나무 울타리', icon: 'fence', price: 20, note: '목장 가장자리에 세워요.'},
    {id: 'flowers', kind: 'deco', name: '꽃밭', icon: 'flowers', price: 40, note: '근처 동물의 건강이 조금 더 빨리 차요.'},
    {id: 'house', kind: 'deco', name: '동물 집', icon: 'house', price: 120, note: '근처에서 자는 동물의 건강이 더 빨리 차요.'},
    {id: 'water', kind: 'deco', name: '물그릇', icon: 'water', price: 80, note: '근처 동물의 똥이 조금 덜 나와요.'},
  ];

  // 배경 — 참고 게임처럼 낮은 띠 그림(먼·중간·가까운 층)을 겹친다. 그림 = ranch/sprites/bg_<id>.png (scripts/ranch-art/build.py)
  const BACKDROPS = [
    {id: 'none', name: '배경 없음', price: 0, note: '바탕화면이 그대로 보여요. 풀밭 띠만 깔아요.'},
    {id: 'meadow', name: '틈의 풀밭', price: 0, note: '세계 사이 틈에 처음 생긴 작은 풀밭이에요.'},
    {id: 'academy', name: '별빛 아카데미 언덕', price: 3000, note: '멀리 아카데미 첨탑과 별의 연구시설 망원경이 보여요.'},
    {id: 'drowned', name: '물에 잠긴 세계의 물가', price: 6000, note: '수평선 끝에 누군가 쌓은 탑과 비공정이 떠 있어요.'},
    {id: 'isekai', name: '주식회사 이세계 퇴근길', price: 9000, note: '불 켜진 사무실 창문들 아래로 버스 정류장이 있어요.'},
  ];

  // 공부 선물 — 서버가 오늘 한 번씩 (ranch_study_gifts)
  const GIFTS = {
    lunch: {name: '자습 도시락', icon: 'lunch', from: '자습실 출석', note: '목장의 모든 동물이 배부르고 건강해져요.'},
    seed: {name: '별 씨앗', icon: 'seed', from: '플래너 완료', note: '심으면 하루 동안 근처 동물이 1.5배 빨리 쌓아요.'},
    egg: {name: '물빛 알', icon: 'egg', from: '별까지 쌓기 집중', note: '품으면 물빛 품질 이상인 아기가 나와요.'},
  };

  // 방문자 — 틈이 열리면 찾아온다. 말투는 해요체, 담백하게
  const VISITORS = {
    noel: {name: '전서구 배달부', sheet: 'visitor_pigeon', from: '별빛 아카데미 전서구 우편국',
      lines: ['편지 왔어요. 받는 사람은… 이 목장이네요.', '틈새로 오는 길이 오늘은 짧았어요.', '아카데미 우편국에서 안부 전해 달래요.'],
      gift: [['food', 10], ['shardMinutes', 20], ['seed', 1], ['cure', 1]]},
    clerk: {name: '인사팀 직원', sheet: 'visitor_clerk', from: '주식회사 이세계 인사팀',
      lines: ['복지 목장 실사 나왔습니다. 잠깐 보고 갈게요.', '서류상으로는 이 목장이 우리 회사 복지 시설이에요. 저도 처음 알았어요.'],
      order: true},
    airship: {name: '비공정 상인', sheet: 'visitor_airship', from: '물에 잠긴 세계의 하늘',
      lines: ['물 위로만 다니다 보니 풀 냄새가 반갑네요.', '오늘은 물건이 조금 남았어요. 보고 가세요.'],
      shop: [{id: 'egg', minutes: 90}, {id: 'seed', minutes: 40}, {id: 'lunch', minutes: 30}]},   // 값 = 목장 수익 N분어치
    bottle: {name: '병 편지', sheet: null, icon: 'bottle', from: '물에 잠긴 세계',
      letters: [
        '여기는 물이 많이 차올랐어요. 탑을 한 층 더 쌓았어요. 위에서 보면 별이 가까워요.',
        '오늘 물고기 세 마리를 놓아줬어요. 그 애들도 어딘가로 흘러갔겠죠.',
        '병을 던지면 어디로 가는지 몰라요. 그래도 누군가 읽으면 좋겠어요.',
        '관측 돔에서 이상한 틈을 봤어요. 그 너머에 풀밭이 있었어요.',
        '비공정 상인이 그러는데, 틈 너머엔 동물을 키우는 학생이 있대요.',
        '쌓은 탑이 무너지지 않게 매일 조금씩 고쳐요. 공부도 그런 거래요.',
      ]},
  };

  // 실사 주문 — 갖춰 두면 보상(목장 수익 N분어치 + 사원증)
  const ORDERS = [
    {need: {adult: 1}, text: '어른이 된 동물 한 마리를 보여 주세요.', minutes: 30},
    {need: {count: 3}, text: '동물이 셋 이상 지내는지 볼게요.', minutes: 30},
    {need: {clean: true}, text: '목장에 똥이 하나도 없어야 해요.', minutes: 40},
    {need: {food: 10}, text: '먹이 창고에 열 개 이상 있어야 해요.', minutes: 25},
    {need: {healthy: 2}, text: '건강한(80 이상) 동물 둘을 보고 싶어요.', minutes: 40},
    {need: {tier: 1}, text: '물빛 품질 이상인 동물이 있나요?', minutes: 60},
  ];

  const TEXT = {
    class: '수업 중 · 보기만',
    classLong: (until) => `수업 중이에요. ${until || '쉬는 시간'}에 돌봐 줄 수 있어요.`,
    offline: '이 PC 에만 저장 중',
    hungry: '배고파요', sick: '아파요', dirty: '근처가 더러워요',
    welcome: '세계와 세계 사이, 아무도 살지 않는 틈에 작은 목장이 생겼어요. 아기 토끼 한 마리가 먼저 굴러 들어왔어요.',
    tips: [
      '빈 땅을 누르면 먹이를 떨어뜨려요. 배고픈 동물이 걸어와 먹어요.',
      '어른이 된 동물을 누르면 몸에 쌓아 둔 틈새 조각을 한꺼번에 받아요.',
      '동물을 끌고 다니면 쌓아 둔 조각을 조금씩 흘려요. 떨어진 조각은 마우스를 올리면 주워요.',
      '똥을 누르면 치워요. 더러우면 동물의 건강이 떨어지고, 아프거나 배고프면 자라지도 쌓지도 않아요.',
    ],
  };

  return {SPECIES, TIERS, BREED_CAP_TIER, STAGES, FACILITIES, SLOTS, LENGTH, GOODS, BACKDROPS, GIFTS, VISITORS, ORDERS, TEXT};
})();
