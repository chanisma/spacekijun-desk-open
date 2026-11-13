// 별사이 목장 (학생판, 2026-11-06) — 독 위 띠에서 아기 동물을 키운다.
// 뼈대(2026-11-06 개편)는 참고 게임 Tiny Pasture 의 구조를 따른다:
//   어른은 수익(틈새 조각)을 몸에 쌓아 두고 → 누르면 한꺼번에 받는다. 가득 차면 넘친 만큼 땅에 떨어지고, 떨어진 조각은 10분 뒤 사라진다.
//   빈 땅을 누르면 먹이를 떨어뜨리고 배고픈 동물이 걸어와 먹는다. 똥이 생기고, 더럽거나 배고프면 건강이 떨어진다 —
//   아프거나 배고프면 자라지도 쌓지도 않는다(죽지는 않는다). 동물은 뽑기로 얻고 품질(흐린~무지개)이 높을수록 빨리 쌓는다.
//   번식한 새끼의 수익 = 부모의 합(무지개만 상한 없음). 시설(빗자루·급식함·채집통·장막)은 레벨을 올린다. 칸·넓히기는 값이 점점 커진다.
// 창 = 유리. 아래 STRIP(104px)이 목장 띠, 위 PANEL 자리는 패널을 열 때만. 누를 자리만 창 모양으로 알린다(ranch_region).
// 수업 중(ranch_state.lesson)에는 보기만 — 동물 상태·도감은 보이고, 돌보기·줍기·상점·번식·꾸미기는 쉬는 시간에. 시설은 수업 중에도 일한다.
// 저장 = 스페이스기전 ranch_read·ranch_save(판 번호 맞추기). 닿지 않으면 이 PC(localStorage)에만 두었다가 다음에 올린다.
'use strict';

const D = window.RANCH_DATA;
// 크기(참고 게임의 확대) — 그림 1화소 = 실제 zoom 픽셀(데스크가 화면 해상도로 정하고 «화면»에서 바꾼다). 띠·땅·그림이 함께 커진다
let PIXEL = 2, STRIP = 104, GROUND = 12;         // CSS px — setZoom 이 다시 셈한다
const STRIP_ART = 52, GROUND_ART = 6;            // core/ranch.py STRIP_ART 와 같다
const HOUR = 3600e3, MIN = 60e3, SEC = 1e3;
const FULL_DECAY = 100 / (4 * HOUR);           // 배부름 — 4시간이면 바닥
const HEALTH_OK = 30;                          // 이 밑이면 아프다
const CAP_MINUTES = 60;                        // 몸에 쌓아 둘 수 있는 조각 = 수익 60분어치
const GROUND_LIFE = 10 * MIN, FOOD_LIFE = 3 * MIN;
const GROUND_CAP = 40, POOP_CAP = 30;
const OFFLINE_CAP = 12 * HOUR;
const FPS = 12;
const SAVE_EVERY = 120e3;

const $ = (id) => document.getElementById(id);
const canvas = $('field'), ctx = canvas.getContext('2d');
let W = 0, H = 0, ratio = 1;
let state = null, version = 0, dirty = false, online = false, lastSave = 0;
let lesson = {in_class: false, until: null}, mode = 'dock';
let atlas = null, sheets = {}, items = null;
let panel = null;             // {kind, ...}
let drag = null;              // {thing, moved, sx, dropAt}
let decorating = false;
let hover = null;
let today = {coins_left: null, rate: 1, unit: 30};
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = (list) => list[Math.floor(Math.random() * list.length)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const uid = () => Math.random().toString(36).slice(2, 10);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = (n) => Math.floor(n).toLocaleString('ko-KR');
const species = (id) => D.SPECIES.find((s) => s.id === id);
const tier = (t) => D.TIERS[t] || D.TIERS[0];

async function api(action, payload) {
  const result = await window.pywebview.api.call(action, payload || {});
  if (!result.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.');
  return result.data;
}

// ── 상태 ───────────────────────────────────────────────────
function fresh() {
  return {v: 2, shards: 0, earned: 0, food: 15, cures: 1, slots: D.SLOTS.start, lengthLevel: 0, length: D.LENGTH.start,
    animals: [], ground: [], deco: [], facilities: {}, inventory: {lunch: 0, seed: 0, egg: 0}, seeds: [], dex: {},
    unlocked: {rabbit: true}, adultsRaised: 0, raisedSpecies: {}, letters: 0, visitor: null, nextVisit: Date.now() + 8 * MIN,
    breeding: null, tick: Date.now(), created: Date.now(), welcomed: false, tip: 0, bg: 'meadow', bgOwned: {none: true, meadow: true}};
}

function newAnimal(sp, t = 0, income = null) {
  const s = species(sp);
  if (s.special) t = 0;                             // 특수 캐릭터 — 품질이 없다
  const a = {id: uid(), sp, tier: t, income: income ?? s.income * tier(t).mult, stage: s.special ? 1 : 0, grow: 0, full: 70, health: 100,
    stored: 0, name: s.special ? s.name : s.baby, x: rnd(0.2, 0.8), born: Date.now(), poopIn: rnd(8, 14) * MIN, fav: false, face: 1};
  state.dex[`${sp}:${t}`] = true;
  return a;
}

function rollTier(min = 0) {
  const pool = D.TIERS.filter((t) => t.id >= min);
  let r = Math.random() * pool.reduce((s, t) => s + t.chance, 0);
  for (const t of pool) { r -= t.chance; if (r <= 0) return t.id; }
  return pool[0].id;
}

// 예전 판(v1, 2026-11-06 첫 판)의 목장을 새 뼈대로 옮긴다 — 조각·먹이·동물·소품은 그대로
function upgrade(s) {
  if (s.v === 2) return s;
  const n = fresh();
  n.shards = s.shards || 0; n.earned = n.shards; n.food = s.food ?? n.food; n.letters = s.letters || 0;
  n.inventory = {...n.inventory, ...(s.inventory || {})};
  n.length = s.length || n.length;
  n.deco = (s.deco || []).map((d) => ({...d}));
  for (const k of ['house', 'water']) if (s.facilities?.[k]) n.deco.push({id: uid(), kind: k, x: s.facilities[k].x ?? 0.5});
  if (s.facilities?.curtain) n.facilities.curtain = {lv: 1, x: s.facilities.curtain.x ?? 0.8};
  if (s.facilities?.feeder) n.facilities.feeder = {lv: 1, x: s.facilities.feeder.x ?? 0.2, t: 0};
  n.welcomed = !!s.welcomed;
  for (const a of s.animals || []) {
    if (!species(a.sp)) continue;
    const t = a.variant === 'star' ? 2 : a.variant === 'water' ? 1 : 0;
    const b = newAnimal(a.sp, t);
    b.name = a.name || b.name; b.x = a.x ?? b.x; b.stage = species(a.sp).special || a.stage === 2 ? 1 : 0; b.badge = a.variant === 'badge';
    if (b.stage) { n.adultsRaised += 1; n.raisedSpecies[a.sp] = true; }
    n.animals.push(b); n.unlocked[a.sp] = true;
  }
  n.slots = Math.max(n.slots, n.animals.length);
  for (const [k, v] of Object.entries(state?.dex || {})) n.dex[k] = v;
  return n;
}

const adults = () => state.animals.filter((a) => a.stage === 1 && !a.away);
const STORAGE_MAX = 30;
const storage = () => (state.storage ||= []);
const roomLeft = () => state.animals.length < state.slots;
function stash(sp, t, income = null) {                 // 창고에 넣고 그 자리를 돌려준다
  const s = species(sp);
  const entry = {id: uid(), sp, tier: s.special ? 0 : t, income: income ?? s.income * tier(s.special ? 0 : t).mult, at: Date.now()};
  storage().push(entry); state.dex[`${sp}:${entry.tier}`] = true; dirty = true;
  return entry;
}
function unstash(entry) { state.storage = storage().filter((x) => x.id !== entry.id); dirty = true; }
function bringIn(entry) {                              // 창고 → 목장
  if (!storage().some((x) => x.id === entry.id)) return null;
  if (!roomLeft()) { toast('칸이 가득 찼어요. 창고에 그대로 있어요 — 칸을 늘리면 데려올 수 있어요.'); return null; }
  unstash(entry);
  const a = newAnimal(entry.sp, entry.tier, entry.income); a.pop = Date.now(); say(a, 'love', 2500);
  state.animals.push(a);
  return a;
}
const healthy = (a) => a.health >= HEALTH_OK && a.full > 0;
const capOf = (a) => Math.max(20, a.income * CAP_MINUTES);
const totalIncome = () => adults().reduce((s, a) => s + a.income, 0) || 5;     // 1분 수익 — 방문자 보상의 기준
const lv = (k) => state.facilities[k]?.lv || 0;
const worldW = () => Math.max(100, (W || 900) - 8);       // 목장 가로 길이(CSS px) — 창 너비
const nearX = (a, x, r) => Math.abs(a.x - x) * worldW() < r;

function unlockCheck() {
  for (const s of D.SPECIES) {
    if (state.unlocked[s.id]) continue;
    const u = s.unlock || {};
    const ok = (u.adult == null || state.adultsRaised >= u.adult) && (u.earned == null || state.earned >= u.earned)
      && (u.species == null || state.raisedSpecies[u.species]) && (u.tier == null || state.animals.some((a) => a.tier >= u.tier));
    if (ok) { state.unlocked[s.id] = true; toast(`틈 너머에 ${s.name}이(가) 보여요. 상점에서 데려올 수 있어요.`); dirty = true; }
  }
}
function unlockText(s) {
  const u = s.unlock || {};
  if (u.adult) return `어른으로 키운 동물 ${u.adult}마리 (${state.adultsRaised})`;
  if (u.earned) return `모은 조각 ${fmt(u.earned)} (${fmt(state.earned)})`;
  if (u.species) return `${species(u.species).name}을(를) 어른으로`;
  if (u.tier) return `${tier(u.tier).name} 품질 동물 얻기`;
  return '';
}

// 조각 떨어뜨리기 — 참고 게임처럼 동물에게서 한쪽으로 포물선을 그리며 튀어 나가 통통 떨어진다(20~30화소). 품질마다 빛깔이 다르다
function dropShard(x, n, t = 0) {
  n = Math.floor(n);                              // 조각은 늘 정수 — 서버가 정수로 검사한다
  if (n < 1) return;
  const side = Math.random() < 0.5 ? -1 : 1;
  const to = clamp(x + side * rnd(20, 30) * PIXEL / worldW(), 0.02, 0.98);
  const near = state.ground.find((g) => g.kind === 'shard' && (g.tier || 0) === t && Math.abs(g.x - to) < 0.02 && !g.fly);
  if (near) { near.n += n; near.at = Date.now(); return; }
  if (state.ground.filter((g) => g.kind === 'shard').length >= GROUND_CAP) return;
  state.ground.push({id: uid(), kind: 'shard', x: to, n, tier: t, at: Date.now(), fly: {from: x, t0: Date.now()}});
}
const FLY_MS = 650;
function flyOffset(g) {                           // {dx(목장 비율), dy(CSS px)} — 날아가는 중이면
  if (!g.fly) return null;
  const k = (Date.now() - g.fly.t0) / FLY_MS;
  if (k >= 1) { delete g.fly; return null; }
  const e = 1 - Math.pow(1 - k, 2);
  const hop = Math.sin(Math.PI * Math.min(1, k * 1.25)) * 22 * PIXEL * (1 - k * 0.6)
    + (k > 0.8 ? Math.abs(Math.sin((k - 0.8) / 0.2 * Math.PI)) * 3 * PIXEL : 0);     // 마지막에 한 번 통통
  return {dx: (g.fly.from - g.x) * (1 - e), dy: -hop - 10 * PIXEL * (1 - e)};
}

// 받은 조각 «+n» — 동물 위로 떠오르며 사라진다
const floats = [];
function floatText(x, y, text) { floats.push({x, y, text, t0: Date.now()}); }
function earn(n) { n = Math.floor(n); state.shards += n; state.earned += n; }

// 이미 지급된 재화의 연출만 담는다. 저장/ground/클릭 대상에 넣지 않아 이중 지급하지 않는다.
const effects = [];
let effectRects = [];
function emitEffect(kind, x, quality = 0, amount = 1) {
  if (document.hidden) return;
  effects.push({kind, x, quality, t0: Date.now(), count: kind === 'coins'
    ? Math.min(12, 4 + Math.ceil(Math.log2(Math.max(1, amount)))) : 1});
  if (effects.length > 16) effects.splice(0, effects.length - 16);
}
function cleanPoop(p, animate = true) {
  if (!state.ground.includes(p)) return;
  state.ground = state.ground.filter((g) => g !== p);
  if (animate) emitEffect('clean', p.x);
  dirty = true;
}

// 시간이 흐른다 — 화면이 도는 동안은 박자마다, 꺼져 있던 시간은 켤 때 1분 단위로 나눠(OFFLINE_CAP 까지)
function advance(now) {
  let dt = now - state.tick;
  if (dt <= 0) return;
  state.tick = now;
  dt = Math.min(dt, OFFLINE_CAP);
  const step = dt > 2 * MIN ? MIN : dt;
  for (let left = dt; left > 0; left -= step) tickBy(Math.min(step, left), dt > 2 * MIN, now);
  dirty = true;
}

function tickBy(dt, offline, now) {
  const poops = state.ground.filter((g) => g.kind === 'poop');
  for (const a of state.animals) {
    if (a.away) continue;
    const ax = a.x;
    a.full = clamp(a.full - FULL_DECAY * dt, 0, 100);
    // 똥 — 물그릇 근처는 덜 나온다
    const water = state.deco.some((d) => d.kind === 'water' && nearX(a, d.x, 140));
    a.poopIn -= dt / (water ? 1.4 : 1);
    if (a.poopIn <= 0) {
      a.poopIn = rnd(8, 14) * MIN;
      if (poops.length < POOP_CAP) { const p = {id: uid(), kind: 'poop', x: clamp(ax + rnd(-0.02, 0.02), 0.02, 0.98), at: now}; state.ground.push(p); poops.push(p); }
    }
    // 건강 — 배고프면·근처가 더러우면 떨어지고, 깨끗하고 배부르면 천천히 찬다
    const dirty_ = Math.min(4, poops.filter((p) => Math.abs(p.x - ax) * worldW() < 140).length);
    const m = dt / MIN;
    let dh = 0;
    if (a.full < 20) dh -= 2 * m;
    dh -= 1.5 * dirty_ * m;
    if (a.full >= 50 && !dirty_) {
      const rest = state.deco.some((d) => (d.kind === 'flowers' || (d.kind === 'house' && a.sleeping)) && nearX(a, d.x, 140));
      dh += (rest ? 1.2 : 0.5) * m;
    }
    a.health = clamp(a.health + dh, 0, 100);
    if (!healthy(a)) continue;
    if (a.stage === 0) {
      a.grow += dt;
      if (a.grow >= species(a.sp).grow * MIN) {
        a.stage = 1; state.adultsRaised += 1; state.raisedSpecies[a.sp] = true;
        if (a.name === species(a.sp).baby) a.name = species(a.sp).name;
        a.pop = Date.now(); say(a, 'happy', 2500);
        if (!offline) toast(`${a.name}이(가) 어른이 됐어요. 이제 조각을 쌓아요 — 누르면 받아요.`);
      }
      continue;
    }
    const boost = state.seeds.some((s) => s.until > now && nearX(a, s.x, 160)) ? 1.5 : 1;
    a.stored += a.income * boost * m;
    const cap = capOf(a);
    if (a.stored > cap) {                         // 넘친 만큼 땅에 — 화면이 꺼져 있었으면 사라진다(참고 게임과 같음)
      if (!offline) dropShard(ax, a.stored - cap, a.tier);
      a.stored = cap;
    }
  }
  // 땅의 것들 — 조각은 10분, 먹이는 3분 뒤 사라진다
  state.ground = state.ground.filter((g) => g.kind === 'poop' || now - g.at < (g.kind === 'food' ? FOOD_LIFE : GROUND_LIFE));
  facilities(dt, offline, now);
  state.seeds = state.seeds.filter((s) => s.until > now);
  if (state.breeding && now >= state.breeding.until) hatch(offline);
  unlockCheck();
}

// 시설 — 수업 중에도 일한다(사람이 누르는 것이 아니다)
function facilities(dt, offline, now) {
  for (const [k, info] of Object.entries(D.FACILITIES)) {
    const f = state.facilities[k];
    if (!f || !info.every) continue;
    f.t = (f.t || 0) + dt;
    const every = info.every[f.lv - 1] * SEC;
    while (f.t >= every) {
      f.t -= every;
      if (k === 'broom') {
        const p = state.ground.find((g) => g.kind === 'poop');
        if (p) { if (!offline) animateFacility(k, f, p.x); cleanPoop(p, !offline); }
      } else if (k === 'feeder') {
        const a = state.animals.filter((x) => !x.away && x.full < 40).sort((x, y) => x.full - y.full)[0];
        if (a && state.food > 0) {
          if (!offline) animateFacility(k, f, a.x);
          state.food -= 1;
          if (offline) a.full = Math.min(100, a.full + 40);
          else state.ground.push({id: uid(), kind: 'food', x: clamp(a.x + rnd(-0.03, 0.03), 0.02, 0.98), at: now});
        }
      } else if (k === 'jar') {
        const a = adults().filter((x) => x.stored >= capOf(x) * 0.95)[0];
        if (a) {
          if (!offline) animateFacility(k, f, a.x);
          const n = Math.floor(a.stored); earn(n); a.stored -= n;
          if (!offline && n > 0) emitEffect('coins', a.x, a.tier, n);
        }
      }
    }
  }
}

function hatch(offline = false) {
  const b = state.breeding;
  state.breeding = null;
  if (!offline && state.facilities.curtain) animateFacility('curtain', state.facilities.curtain, state.facilities.curtain.x, 'finish');
  for (const a of state.animals) if (b.parents.includes(a.id)) a.away = false;
  if (!roomLeft()) { stash(b.sp, b.tier, b.income); toast(`칸이 가득 차서 ${tier(b.tier).name} ${species(b.sp).name} 새끼를 창고에 두었어요. 상점 «창고»에서 데려와요.`); return; }
  const baby = newAnimal(b.sp, b.tier, b.income);
  baby.x = state.facilities.curtain?.x ?? 0.5; baby.pop = Date.now(); say(baby, 'love', 3000);
  state.animals.push(baby);
  toast(`별빛 장막에서 ${tier(b.tier).name} ${species(b.sp).name} 새끼가 나왔어요 (1분 ${fmt(b.income)}조각).`);
}

// ── 저장 ───────────────────────────────────────────────────
function saveLocal() { try { localStorage.setItem('ranch.state', JSON.stringify({state, version, at: Date.now()})); } catch {} }

async function load() {
  let local = null;
  try { local = JSON.parse(localStorage.getItem('ranch.state') || 'null'); } catch {}
  try {
    const got = await api('ranch_call', {work: 'read', body: {}});
    online = true;
    if (got?.today) today = got.today;
    const server = got?.ranch;
    if (server && server.state) {
      if (local && local.version === server.version && local.at > Date.parse(server.saved_at || 0)) {
        state = local.state; version = server.version; dirty = true;        // 올리지 못한 변경이 있다
      } else { state = server.state; version = server.version; }
    } else if (local) { state = local.state; version = 0; dirty = true; }
  } catch (error) {
    online = false;
    if (local) { state = local.state; version = local.version || 0; }
  }
  state = state ? upgrade(state) : fresh();
  for (const [k, v] of Object.entries(fresh())) if (state[k] === undefined) state[k] = v;
  advance(Date.now());
}

let saving = false;
async function save(force = false) {
  saveLocal();
  if (saving || (!dirty && !force)) return;
  saving = true;
  try {
    const got = await api('ranch_call', {work: 'save', body: {p_version: version, p_state: state}});
    online = true;
    if (got?.conflict) {
      if (got.ranch?.state) { state = upgrade(got.ranch.state); version = got.ranch.version; dirty = false; if (!got.rejected) toast('다른 PC 에서 돌본 목장을 불러왔어요.'); }
      else if (got.rejected) { state = fresh(); version = 0; dirty = true; }     // 처음 올린 것이 거절됐다
      else { version = 0; dirty = true; }                                       // 서버에 아직 없다 — 다음에 처음부터 올린다
    } else if (got?.version) { version = got.version; dirty = false; }
    if (got?.rejected) toast(got.rejected);
    lastSave = Date.now();
  } catch (error) {
    online = false;
  } finally { saving = false; saveLocal(); paintHud(); }
}

// ── 그림 ───────────────────────────────────────────────────
async function loadArt() {
  atlas = window.RANCH_ATLAS || {sheets: {}, items: {}};
  const img = (src) => new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => ok(null); i.src = src; });
  for (const [name, meta] of Object.entries(atlas.sheets || {})) sheets[name] = {meta, img: await img(meta.src || `ranch/sprites/${name}.png`)};
  if (atlas.items && Object.keys(atlas.items).length) items = {meta: atlas.items, img: await img(atlas.itemsSrc || 'ranch/sprites/items.png')};
  for (const el of document.querySelectorAll('.ico.shard')) el.outerHTML = icon('shard', 16);
  for (const el of document.querySelectorAll('.ico.food')) el.outerHTML = icon('food', 16);
  dress($('hud'));
}

// 패널·HUD 의 작은 그림 — 시트를 CSS 배경으로 잘라 보인다.
// 🚨 캔버스에서 그림을 꺼내면(toDataURL) 안 된다: 데스크 창은 file:// 라 그린 캔버스가 «오염»돼 SecurityError 가 난다.
// 🚨 HTML 에 style="…" 를 쓰면 안 된다: 화면의 CSP(style-src 'self')가 막는다. data-* 로 두고 dress() 가 element.style 로 입힌다.
const icon = (name, size = 24) => `<i class="ico" data-icon="${name}" data-size="${size}"></i>`;
const portrait = (sheet, size = 28) => `<i class="ico" data-portrait="${sheet}" data-size="${size}"></i>`;
function qualitySheet(sheet, quality) {
  const variant = `${sheet}_t${quality}`;
  return quality > 0 && sheets[variant]?.img ? variant : sheet;
}
function dress(root = document) {
  for (const el of root.querySelectorAll('[data-icon],[data-portrait]')) {
    const size = Number(el.dataset.size) || 24;
    el.style.width = el.style.height = `${size}px`;
    let url, w, h, sx, sy, iw, ih;
    if (el.dataset.icon) {
      const facility = sheets[`facility_${atlas.facilityIcons?.[el.dataset.icon]}`];
      if (facility?.img) {
        const b = facility.meta.bounds[0];
        [sx, sy] = b; w = b[2] - b[0]; h = b[3] - b[1];
        [iw, ih] = [facility.img.width, facility.img.height]; url = facility.meta.src;
      } else {
      const box = items?.meta?.[el.dataset.icon];
      if (!box || !items.img) continue;
      [sx, sy, w, h] = box; [iw, ih] = [items.img.width, items.img.height]; url = atlas.itemsSrc || 'ranch/sprites/items.png';
      }
    } else {
      const s = sheets[el.dataset.portrait];
      if (!s) continue;
      [w, h] = s.meta.cell; sx = 0; sy = 0; iw = w * s.meta.frames; ih = h; url = `ranch/sprites/${el.dataset.portrait}.png`;
      if (s.meta.native && s.img) {
        const b = s.meta.bounds[0];
        [sx, sy] = b; w = b[2] - b[0]; h = b[3] - b[1];
        iw = s.img.width; ih = s.img.height; url = s.meta.src;
      }
    }
    const k = size / Math.max(w, h);
    el.style.backgroundImage = `url(${url})`;
    el.style.backgroundRepeat = 'no-repeat';
    el.style.backgroundSize = `${iw * k}px ${ih * k}px`;
    el.style.backgroundPosition = `${-sx * k + (size - w * k) / 2}px ${-sy * k + (size - h * k)}px`;
  }
  for (const el of root.querySelectorAll('[data-w]')) el.style.width = `${el.dataset.w}%`;
  for (const el of root.querySelectorAll('[data-tier]')) {
    const t = tier(Number(el.dataset.tier));
    el.style.background = t.color === 'rainbow' ? 'linear-gradient(90deg,#f06a5b,#ffd24a,#6fd08c,#7fc4e6,#b48cf0)' : t.color;
  }
}

const nativeMasks = new Map(), nativeClocks = new WeakMap();
function nativeFrame(a, meta, now, held = false) {
  const clips = meta.clips;
  const action = held ? 'move' : a.until > now && a.special === 1 ? 'interact_0' : a.eating ? 'eat' : a.moving ? 'move' : a.pose === 3 ? 'sleep_loop'
    : a.pose === 1 ? 'interact_0' : a.sit || a.pose === 4 ? (clips.idle_1_loop ? 'idle_1_loop' : 'idle_1') : 'idle_0';
  const clip = clips[action] || clips.idle_0;
  let clock = nativeClocks.get(a);
  if (!clock || clock.action !== action) {
    clock = {action, start: now}; nativeClocks.set(a, clock);
  }
  const t = ((now - clock.start) / 1000) % clip.duration;
  let i = 0;
  while (i + 1 < clip.times.length && clip.times[i + 1] <= t) i += 1;
  return clip.frames[i];
}

function drawNativeSheet(s, frame, x, baseY, scale, alpha, flip, warp) {
  const m = s.meta, [cw, ch] = m.cell, [ax, ay] = m.anchor, outline = warp?.outline;
  const sx = frame % m.columns * cw, sy = Math.floor(frame / m.columns) * ch;
  const flipped = flip !== (m.frameFlip?.includes(frame) ? !m.flip : m.flip);
  // 바닥 앵커와 모든 좌표를 원본 픽셀 격자에 맞춘다.
  const px = Math.round(x / scale) * scale, py = Math.round(baseY / scale) * scale;
  ctx.save(); ctx.imageSmoothingEnabled = false; ctx.globalAlpha = alpha;
  ctx.translate(px, py);
  if (warp && (warp.sx !== 1 || warp.sy !== 1 || warp.skew)) ctx.transform(warp.sx ?? 1, 0, warp.skew || 0, warp.sy ?? 1, 0, 0);
  if (flipped) ctx.scale(-1, 1);
  if (outline) {
    const key = `${s.img.src}|${outline}`;
    if (!nativeMasks.has(key)) {
      const c = document.createElement('canvas'); c.width = s.img.width; c.height = s.img.height;
      const g = c.getContext('2d'); g.drawImage(s.img, 0, 0);
      g.globalCompositeOperation = 'source-in'; g.fillStyle = outline; g.fillRect(0, 0, c.width, c.height);
      nativeMasks.set(key, c);
    }
    ctx.globalAlpha = alpha * 0.7;
    for (const [dx, dy] of [[-1,0],[1,0],[0,-1],[0,1]])
      ctx.drawImage(nativeMasks.get(key), sx, sy, cw, ch, (-ax+dx*(m.pixelRatio || 1))*scale, (-ay+dy*(m.pixelRatio || 1))*scale, cw*scale, ch*scale);
    ctx.globalAlpha = alpha;
  }
  ctx.drawImage(s.img, sx, sy, cw, ch, -ax*scale, -ay*scale, cw*scale, ch*scale);
  ctx.restore();
  const b = m.bounds[frame] || m.bounds[0];
  // 모든 프레임을 합친 상자 — 말풍선 자리·창 모양이 프레임마다 출렁이지 않게(2026-11-07, 잘려 보이던 것)
  const u = m.union ||= m.bounds.filter(Boolean).reduce((a, c) => [Math.min(a[0], c[0]), Math.min(a[1], c[1]), Math.max(a[2], c[2]), Math.max(a[3], c[3])]);
  const sk = Math.abs(warp?.skew || 0) * (ay - u[1]) * scale;
  return {x: px + (flipped ? ax-b[2] : b[0]-ax)*scale, y: py+(b[1]-ay)*scale,
    w: (b[2]-b[0])*scale, h: (b[3]-b[1])*scale,
    full: {x: px + (flipped ? ax-u[2] : u[0]-ax)*scale - sk, y: py+(u[1]-ay)*scale, w: (u[2]-u[0])*scale + sk*2, h: (u[3]-u[1])*scale}};
}

function drawSheet(sheet, frame, x, baseY, scale, alpha = 1, flip = false, warp = null) {
  const s = sheets[sheet];
  if (s?.meta.native && s.img) return drawNativeSheet(s, frame, x, baseY, scale, alpha, flip, warp);
  if (!s?.img) {                                         // 그림이 아직 없으면 둥근 덩어리
    ctx.fillStyle = '#e8d8ff'; ctx.strokeStyle = '#3b2a55';
    ctx.beginPath(); ctx.ellipse(x, baseY - 14 * scale, 14 * scale, 13 * scale, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    return {x: x - 15 * scale, y: baseY - 28 * scale, w: 30 * scale, h: 28 * scale};
  }
  const [cw, ch] = s.meta.cell;
  const w = Math.round(cw * scale), h = Math.round(ch * scale);
  const left = Math.round(x - w / 2), top = Math.round(baseY - h);
  ctx.globalAlpha = alpha;
  // 동물 2판은 고해상도 — 부드럽게 줄인다(픽셀을 찍으면 뭉개진다). 다마고찌 시트·소품은 그대로 화소를 살린다
  ctx.imageSmoothingEnabled = !!s.meta.hires;
  if (s.meta.hires) ctx.imageSmoothingQuality = 'high';
  if (flip || warp) {
    // 발바닥(가운데 아래)을 기준으로 뒤집고·늘이고·기울인다
    ctx.save(); ctx.translate(left + w / 2, top + h);
    if (warp) ctx.transform(warp.sx, 0, warp.skew, warp.sy, 0, 0);
    if (flip) ctx.scale(-1, 1);
    ctx.drawImage(s.img, frame * cw, 0, cw, ch, -w / 2, -h, w, h);
    ctx.restore();
  } else ctx.drawImage(s.img, frame * cw, 0, cw, ch, left, top, w, h);
  ctx.imageSmoothingEnabled = false;
  ctx.globalAlpha = 1;
  return {x: left, y: top, w, h};
}

const ITEM_H = {shard: 7, poop: 7, pile: 7, food: 9, seed: 8, sprout: 9, fence: 16, flowers: 12, house: 26, water: 10,
  broom: 20, pigeonbox: 22, jar: 13, feeder: 18, curtain: 24, bottle: 9, egg: 9, lunch: 9, medicine: 9};
function itemScale(name, k = 1) {                 // 그 소품이 ITEM_H 칸 × k 가 되게
  const box = items?.meta?.[name];
  return box ? PIXEL * (ITEM_H[name] || 10) * k / box[3] : PIXEL;
}

function drawItem(name, x, baseY, scale = 1) {
  const box = items?.meta?.[name];
  if (!box || !items.img) {
    ctx.fillStyle = name === 'shard' ? '#b9a2ff' : name === 'poop' ? '#8a5a3a' : '#c9a36b';
    ctx.fillRect(Math.round(x - 6 * scale), Math.round(baseY - 12 * scale), 12 * scale, 12 * scale);
    return {x: x - 6 * scale, y: baseY - 12 * scale, w: 12 * scale, h: 12 * scale};
  }
  const w = Math.round(box[2] * scale), h = Math.round(box[3] * scale);
  ctx.drawImage(items.img, box[0], box[1], box[2], box[3], Math.round(x - w / 2), Math.round(baseY - h), w, h);
  return {x: Math.round(x - w / 2), y: Math.round(baseY - h), w, h};
}

function backdrop() {
  const id = state.bg || 'meadow';
  return id === 'none' ? null : (sheets[`bg_${id}`]?.img && atlas.bgs?.[id] ? {img: sheets[`bg_${id}`].img, meta: atlas.bgs[id]} : null);
}
// 층 하나를 목장 너비만큼 잇는다 — 이음매가 보이지 않게 한 칸씩 좌우를 뒤집어 잇는다(ABBA). 높이가 띠보다 크면 줄인다
function eachTile(layer, fn) {
  const k = Math.min(PIXEL, STRIP / layer.h);
  const w = layer.w * k, h = layer.h * k;
  const stride = w - (layer.overlap || 0) * k;
  let i = 0;
  for (let dx = -stride * (layer.phase || 0); dx < W; dx += stride, i += 1) fn(0, i % 2 === 1, dx, w, h);
  return {w, h, k, stride};
}
const shardCache = {};
const COIN_ART = ['coin_copper_ani', 'diamond_blue_ani', 'diamond_yellow_ani', 'coin_gold_ani', 'diamond_rainbow_ani'];
function drawEffectSprite(name, frame, x, baseY, scale = PIXEL, alpha = 1) {
  const s = sheets[`fx_${name}`];
  if (!s?.img) return null;
  const m = s.meta, [cw, ch] = m.cell;
  frame = Math.max(0, Math.min(m.frames - 1, frame));
  const left = Math.round((x / scale) - cw / 2) * scale;
  const top = Math.round(baseY / scale - m.anchorY) * scale;
  ctx.save(); ctx.imageSmoothingEnabled = false; ctx.globalAlpha *= alpha;
  ctx.drawImage(s.img, frame*cw, 0, cw, ch, left, top, cw*scale, ch*scale);
  ctx.restore();
  const b = m.bounds[frame] || [0,0,cw,ch];
  return {x:left+b[0]*scale, y:top+b[1]*scale, w:(b[2]-b[0])*scale, h:(b[3]-b[1])*scale};
}
function drawEffects(now) {
  const {left, len} = rangeX(), base = H - GROUND;
  for (let i = effects.length - 1; i >= 0; i -= 1) {
    const e = effects[i], age = now-e.t0, lifetime = e.kind === 'coins' ? 1400 : 620;
    if (age >= lifetime) { effects.splice(i, 1); continue; }
    let bounds = null;
    const include = (r) => {
      if (!r) return;
      if (!bounds) bounds = {...r};
      else { const x=Math.min(bounds.x,r.x), y=Math.min(bounds.y,r.y);
        bounds={x,y,w:Math.max(bounds.x+bounds.w,r.x+r.w)-x,h:Math.max(bounds.y+bounds.h,r.y+r.h)-y}; }
    };
    const x = left+e.x*len;
    if (e.kind === 'coins') {
      for (let n = 0; n < e.count; n += 1) {
        const t = (age-n*24)/1050;
        if (t < 0 || t >= 1) continue;
        const spread = (n/(e.count-1)-0.5)*66;
        const arc = t < 0.72 ? 12*(1-t/0.72) + Math.sin(t/0.72*Math.PI)*(15+n%3*3)
          : Math.abs(Math.sin((t-0.72)/0.28*Math.PI))*5;
        const cx = clamp(x+spread*t*PIXEL, 8*PIXEL, W-8*PIXEL);
        include(drawEffectSprite(COIN_ART[e.quality] || COIN_ART[0], Math.floor(age/85+n)%5,
          cx, base-arc*PIXEL, PIXEL, Math.min(1,(1-t)/0.23)));
      }
    } else {
      // 원본 소멸 시트의 후반 7장. 12fps 목장에서도 각 칸이 읽히도록 약 0.6초.
      include(drawEffectSprite('fx_poop', 5+Math.min(6,Math.floor(age/85)), x, base, PIXEL));
    }
    if (bounds) effectRects.push(bounds);
  }
}
function drawShard(t, x, baseY, scale) {         // 품질 빛깔을 입힌 조각 — 화면 밖 캔버스에 칠해 둔다(읽지 않으므로 file:// 에서도 된다)
  const native = drawEffectSprite(COIN_ART[t] || COIN_ART[0], Math.floor(Date.now()/110)%5, x, baseY, PIXEL * scale / itemScale('shard'));
  if (native) return native;
  const box = items?.meta?.shard;
  if (!box || !items.img) return drawItem('shard', x, baseY, scale);
  const color = tier(t).color === 'rainbow' ? ['#f06a5b', '#ffd24a', '#6fd08c', '#7fc4e6', '#b48cf0'][Math.floor(frameNo / 3) % 5] : t ? tier(t).color : null;
  let src = items.img, sx = box[0], sy = box[1];
  if (color) {
    if (!shardCache[color]) {
      const c = document.createElement('canvas'); c.width = box[2]; c.height = box[3];
      const g = c.getContext('2d'); g.imageSmoothingEnabled = false;
      g.drawImage(items.img, box[0], box[1], box[2], box[3], 0, 0, box[2], box[3]);
      g.globalCompositeOperation = 'source-atop'; g.globalAlpha = 0.55; g.fillStyle = color; g.fillRect(0, 0, box[2], box[3]);
      shardCache[color] = c;
    }
    src = shardCache[color]; sx = 0; sy = 0;
  }
  const w = Math.round(box[2] * scale), h = Math.round(box[3] * scale);
  ctx.drawImage(src, sx, sy, box[2], box[3], Math.round(x - w / 2), Math.round(baseY - h), w, h);
  return {x: Math.round(x - w / 2), y: Math.round(baseY - h), w, h};
}

// 종마다 정한 키(목장 그림 칸)가 되게 — 시트의 첫 자세(서 있기) 키 기준
function sizeScale(a) {
  const sp = species(a.sp), meta = sheets[a.stage ? sp.sheet : sp.babySheet]?.meta;
  if (meta?.native) return PIXEL / (meta.pixelRatio || 1); // 저장 밀도와 화면 몸 크기를 분리한다.
  const body = meta?.body || meta?.cell?.[1] || 32;
  return PIXEL * sp.size[a.stage ? 1 : 0] / body;
}

function rangeX() {                      // 목장이 차지하는 가로 범위 (창 안 CSS px) — 창 너비가 곧 목장(«화면»에서 정한다)
  return {left: 4, len: Math.max(100, W - 8)};
}

let view = {width: 1, x: 0.5, lift: 0, zoom: null, top: false, outline: true}, zoom = 2;
function setZoom(z) {
  zoom = z || 2;
  PIXEL = zoom / (window.devicePixelRatio || 1);
  STRIP = STRIP_ART * PIXEL; GROUND = Math.round(GROUND_ART * PIXEL);
  const root = document.documentElement.style;
  root.setProperty('--strip', `${STRIP}px`);
  const nativeArt = window.RANCH_ATLAS?.sheets?.rabbit_adult?.native;
  root.setProperty('--hud-bottom', `${Math.round(nativeArt ? STRIP + 2 * PIXEL : STRIP - 26 * Math.max(1, PIXEL / 2))}px`);
  root.setProperty('--panel-bottom', `${Math.round(nativeArt ? STRIP + 2 * PIXEL + 36 : STRIP + 8)}px`);
  lastRegion = '';
}

function night() { const h = new Date().getHours(); return h >= 19 || h < 6; }

// 원경은 옅게, 앞쪽 풀은 선명하게. 투명 윤곽을 보존하고 층별 색 보정은 한 번만 한다.
const sceneryCache = new Map();
function sceneryLayer(bg, layer, index, dark) {
  const key = `${bg.img.src}|${index}|${dark}`;
  if (!sceneryCache.has(key)) {
    const c = document.createElement('canvas'); c.width = layer.w; c.height = layer.h;
    const g = c.getContext('2d');
    g.drawImage(bg.img, 0, layer.y, layer.w, layer.h, 0, 0, layer.w, layer.h);
    g.globalCompositeOperation = 'source-atop';
    g.fillStyle = dark ? `rgba(22,30,78,${[0.48, 0.34, 0.22][index] ?? 0.22})`
      : `rgba(239,239,217,${[0.22, 0.08, 0][index] ?? 0})`;
    g.fillRect(0, 0, c.width, c.height);
    sceneryCache.set(key, c);
  }
  return sceneryCache.get(key);
}

// 발밑의 낮은 픽셀 그림자. 공중에 뜬 캐릭터도 그림자는 땅에 남는다.
function drawContactShadow(x, base, width, flying = false) {
  const p = PIXEL, w = Math.max(4, Math.round(width * (flying ? 0.22 : 0.3) / p));
  ctx.save();
  ctx.fillStyle = night() ? 'rgba(15,23,39,.30)' : 'rgba(34,55,42,.23)';
  const left = Math.round(x / p - w / 2) * p, y = Math.round(base / p) * p;
  ctx.fillRect(left, y, w * p, p);
  ctx.fillRect(left + p, y - p, Math.max(2, w - 2) * p, p);
  ctx.restore();
}

// 옮기기 연출(2026-11-07) — 들면 떠오르고 끄는 방향 반대로 흔들리고, 놓으면 떨어져 통 튄다. 저장하지 않는다
const motions = new WeakMap();
function motionOf(a) { let m = motions.get(a); if (!m) motions.set(a, m = {lift: 0, dropT: 0, dropFrom: 0}); return m; }
const LIFT = 9;          // 들어 올리는 높이(그림 칸)

// 시설의 실제 작업은 facilities/hatch가 한 번만 처리한다. 연출은 저장하지 않고,
// 프레임을 재생하거나 창을 다시 그린다고 먹이·재화·새끼가 추가되지 않는다.
const facilityJobs = new WeakMap();
let facilityFrames = [];
function animateFacility(kind, f, target, action = 'work') {
  if (!f) return;
  facilityJobs.set(f, {kind, from: f.x, target, action, start: Date.now(), duration: kind === 'curtain' ? 1200 : 2400});
}
function drawFacility(kind, f, at, base, now) {
  const s = sheets[`facility_${kind}`];
  if (!s?.img) return drawItem(D.FACILITIES[kind].icon, at(f.x), base, itemScale(D.FACILITIES[kind].icon));
  let job = facilityJobs.get(f);
  if (job && now - job.start >= job.duration) { facilityJobs.delete(f); job = null; }
  const elapsed = job ? Math.max(0, now - job.start) : 0;
  let frame = 0, x = f.x, lift = 0, phase = 'idle', workerX = null;
  const ease = t => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
  if (kind === 'broom') {
    if (job) {
      const out = ease(elapsed / 650), back = ease((elapsed - 1450) / 750);
      x = elapsed < 1450 ? job.from + (job.target - job.from) * out : job.target + (f.x - job.target) * back;
      phase = elapsed < 650 ? 'travel' : elapsed < 1450 ? 'sweep' : 'return';
      frame = phase === 'sweep' ? 4 + Math.floor(elapsed / 100) % 3 : elapsed > 2200 ? 7 : 2 + Math.floor(elapsed / 160) % 2;
      lift = phase === 'sweep' ? 0 : Math.sin(Math.PI * (elapsed < 650 ? out : 1 - back)) * 6 * PIXEL;
    } else { frame = Math.floor(now / 900) % 2; lift = (Math.sin(now / 650) + 1) * PIXEL; }
  } else if (kind === 'feeder' && job) {
    frame = Math.min(7, Math.floor(elapsed / 300));
    phase = elapsed < 900 ? 'open' : elapsed < 1800 ? 'dispense' : 'close';
  } else if (kind === 'jar') {
    frame = job ? Math.min(7, Math.floor(elapsed / 300)) : Math.floor(now / 800) % 2;
    phase = job ? 'collect' : 'idle';
  } else if (kind === 'curtain') {
    if (job) {
      phase = job.action;
      frame = job.action === 'finish' ? elapsed < 600 ? 6 : 7 : Math.min(3, Math.floor(elapsed / 300));
    } else if (state.breeding) { phase = 'breeding'; frame = 4 + Math.floor(now / 300) % 2; }
  }
  const scale = PIXEL / s.meta.pixelRatio;
  const r = drawNativeSheet(s, frame, at(x), base - lift, scale, 1, false, null);
  if (job && kind === 'jar') {
    // 집에서 목표 동물까지 왕복하는 반딧불 일꾼. 작은 빛/날개는 독립된 효과다.
    const k = clamp((elapsed - 300) / 1800, 0, 1), leg = k < .5 ? ease(k * 2) : ease((1 - k) * 2);
    workerX = f.x + (job.target - f.x) * leg;
    const wx = at(workerX), wy = base - (20 + Math.sin(k * Math.PI) * 14) * PIXEL;
    const wing = Math.floor(now / 70) % 2 ? 3 : 1;
    ctx.fillStyle = '#f6f2cf'; ctx.fillRect(wx - 4*PIXEL, wy - wing*PIXEL, 3*PIXEL, PIXEL); ctx.fillRect(wx + PIXEL, wy - wing*PIXEL, 3*PIXEL, PIXEL);
    ctx.fillStyle = '#566c59'; ctx.fillRect(wx-2*PIXEL, wy-PIXEL, 4*PIXEL, 3*PIXEL);
    ctx.fillStyle = '#ffdf79'; ctx.fillRect(wx, wy, 2*PIXEL, 2*PIXEL);
    effectRects.push({x:wx-5*PIXEL,y:wy-4*PIXEL,w:10*PIXEL,h:8*PIXEL});
  }
  if (job && kind === 'feeder' && elapsed >= 900 && elapsed < 1800) {
    const k = (elapsed-900)/900, gx = at(f.x+(job.target-f.x)*k), gy = base-(26*(1-k)+16*Math.sin(k*Math.PI))*PIXEL;
    ctx.fillStyle = '#e9b956';
    for (let i=0;i<3;i++) ctx.fillRect(gx+(i-1)*2*PIXEL,gy+(i%2)*PIXEL,PIXEL,2*PIXEL);
    effectRects.push({x:gx-3*PIXEL,y:gy-PIXEL,w:7*PIXEL,h:5*PIXEL});
  }
  // 움직이는 빗자루와 일꾼도 창의 투명 영역에 포함한다.
  effectRects.push(r.full || r);
  facilityFrames.push({kind, frame, phase, x, home:f.x, workerX, active:!!job, rect:{...r.full}});
  return r;
}

let hits = [];          // 이번 장면에서 누를 수 있는 것 [{rect, thing}]
let frameNo = 0;
function draw() {
  frameNo += 1;
  effectRects = []; handRects = []; facilityFrames = []; // 이번 장면의 연출 자리 — 투명 창 모양에 포함한다.
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.imageSmoothingEnabled = false;
  const {left, len} = rangeX();
  const base = H - GROUND;
  hits = [];
  // 배경 — 참고 게임처럼 낮은 띠 그림(먼·중간·가까운 층)을 겹쳐 옆으로 잇는다. 밤이면 남색을 덧입힌다
  const bg = backdrop();
  if (bg) {
    const dark = night();
    bg.meta.layers.forEach((layer, index) => {
      const art = sceneryLayer(bg, layer, index, dark);
      eachTile(layer, (sx, flip, dx, w, h) => {
      ctx.save();
      if (flip) { ctx.translate(dx + w, 0); ctx.scale(-1, 1); ctx.drawImage(art, 0, H - h, w, h); }
      else ctx.drawImage(art, dx, H - h, w, h);
      ctx.restore();
      });
    });
  } else {                                                    // 배경 없음 — 풀밭 띠만
    ctx.fillStyle = night() ? 'rgba(52,74,70,.92)' : 'rgba(118,170,94,.92)';
    ctx.fillRect(left, base, len, GROUND - 2);
    ctx.fillStyle = night() ? 'rgba(80,110,96,.95)' : 'rgba(150,200,110,.95)';
    for (let x = left + 3; x < left + len - 3; x += 9) ctx.fillRect(x, base - ((x * 7) % 3), 2, 3);
  }
  hits.push({rect: {x: left, y: base - 4, w: len, h: GROUND + 4}, thing: {type: 'ground'}, low: true});
  const at = (fx) => left + fx * len;
  for (const d of state.deco) {
    const r = drawItem(d.kind, at(d.x), base, itemScale(d.kind));
    if (decorating) hits.push({rect: r, thing: {type: 'deco', item: d}});
  }
  for (const [kind, f] of Object.entries(state.facilities)) {
    if (!f) continue;
    const r = drawFacility(kind, f, at, base, Date.now());
    hits.push({rect: r, full: r.full, thing: {type: 'facility', kind, item: f}});
  }
  for (const s of state.seeds) drawItem(items?.meta.sprout ? 'sprout' : 'seed', at(s.x), base, itemScale(items?.meta.sprout ? 'sprout' : 'seed'));
  for (const g of state.ground) {
    const fly = g.kind === 'shard' ? flyOffset(g) : null;
    const bob = g.kind === 'shard' && !fly ? Math.sin((frameNo + g.id.charCodeAt(0)) / 4) * 1.5 : 0;
    const fade = g.kind === 'shard' && Date.now() - g.at > GROUND_LIFE - MIN ? (frameNo % 6 < 3 ? 0.4 : 1) : 1;
    ctx.globalAlpha = fade;
    const fall = g.drop && Date.now() - g.drop < 400 ? (1 - (Date.now() - g.drop) / 400) ** 2 * 24 * PIXEL : 0;   // 먹이는 위에서 툭 떨어진다
    const gx = at(g.x + (fly?.dx || 0)), gy = base - 1 + bob + (fly?.dy || 0) - fall;
    const art = g.kind === 'food' ? 'pile' : g.kind;
    const big = g.kind === 'shard' ? Math.min(1.6, 1 + Math.log10(Math.max(1, g.n || 1)) / 6) : 1;    // 많이 쌓인 조각은 조금 크게
    let r;
    if (g.kind === 'poop') {
      const age = Math.max(0, Date.now()-g.at);
      const pop = age < 400 ? Math.sin(age/400*Math.PI)*3*PIXEL : 0;
      const kind = age >= 5*MIN ? 'shit_big' : 'shit_small';
      r = drawEffectSprite(kind, 0, gx, gy-pop) || drawItem(art,gx,gy,itemScale(art));
      if (age >= MIN) {
        const flies = drawEffectSprite('shit_flies', Math.floor(Date.now()/125)%7, gx, gy-7*PIXEL);
        if (flies) r = {x:Math.min(r.x,flies.x),y:Math.min(r.y,flies.y),
          w:Math.max(r.x+r.w,flies.x+flies.w)-Math.min(r.x,flies.x),h:gy-Math.min(r.y,flies.y)+1};
      }
    } else r = g.kind === 'shard' ? drawShard(g.tier || 0, gx, gy, itemScale('shard', big)) : drawItem(art, gx, gy, itemScale(art));
    ctx.globalAlpha = 1;
    hits.push({rect: r, thing: {type: g.kind, item: g}});
  }
  const v = state.visitor;
  if (v) {
    const info = D.VISITORS[v.id];
    const x = at(v.x);
    const r = info.sheet ? drawSheet(info.sheet, 0, x, v.id === 'airship' ? H - STRIP + 46 : base, PIXEL * 0.9)
                         : drawItem(info.icon, x, base, itemScale(info.icon));
    hits.push({rect: r, thing: {type: 'visitor'}});
  }
  const order = state.animals.filter((a) => !a.away).sort((a, b) => b.stage - a.stage);
  const now = Date.now();
  const labels = [];
  for (const a of order) {
    const sp = species(a.sp);
    const canonical = a.stage ? sp.sheet : sp.babySheet;
    const still = qualitySheet(canonical, a.tier);
    const native = sheets[still]?.meta.native;
    const walkSheet = sheets[`${still}_walk`] ? `${still}_walk` : null;
    // 걷는 중이면 걷기 6프레임(초당 8장, 참고 게임과 같은 짜임) — 걷기 그림이 없는 특수 캐릭터는 통통 튄다
    const walking = a.moving && !a.eating;
    const sheet = walking && walkSheet ? walkSheet : still;
    const mo = motionOf(a), held = !!(drag?.moved && drag.thing.item === a);
    const frame = native ? nativeFrame(a, sheets[still].meta, now, held)
      : walking && walkSheet ? Math.floor(now / 125 + a.born % 6) % 6 : (a.pose ?? 0);
    const hop = walking && !walkSheet && !native && frameNo % 4 < 2 ? 0.6 * PIXEL : 0;
    const fly = sp.fly ? Math.sin((frameNo + a.born % 50) / 5) * 3 - 6 : 0;
    // 숨쉬기(가만히·잠) · 이벤트 때 늘었다 줄었다(0.9~1.1, 참고 게임의 skew·scale 트윈) · 먹을 때 흔들림
    let sx = 1, sy = 1, skew = 0;
    if (!walking) { const b = Math.sin(now / (a.pose === 3 ? 900 : 600) + a.born % 7) * 0.025; sy += b; sx -= b / 2; }
    if (a.pop && now - a.pop < 450) { const k = (now - a.pop) / 450; const w = Math.sin(k * Math.PI * 2) * (1 - k) * 0.12; sx += w; sy -= w; }
    if (a.eating) skew = Math.sin(now / 70) * 0.06;
    let lift = 0;
    if (held) {
      mo.lift = Math.min(1, mo.lift + 0.15); mo.dropT = 0;
      drag.vx = (drag.vx || 0) * 0.88;                              // 마우스를 멈추면 흔들림이 잦아든다
      skew = Math.max(-0.45, Math.min(0.45, -drag.vx * 0.03)) + Math.sin(now / 170) * 0.05;   // 발이 뒤로 끌린다
      sx = 0.96; sy = 1.05;                                          // 들리면 몸이 살짝 늘어진다
      lift = (1 - (1 - mo.lift) ** 2) * LIFT * PIXEL;
    } else if (mo.dropT) {
      const k = (now - mo.dropT) / 240;
      if (k >= 1) { mo.dropT = 0; mo.lift = 0; a.pop = now; }      // 땅에 닿으면 통(0.9~1.1)
      else lift = mo.dropFrom * (1 - k * k);
    }
    const scale = sizeScale(a), warp = {sx, sy, skew};
    if (native && (view.outline !== false || hover === a.id)) {
      const color = tier(a.tier).color;
      warp.outline = color === 'rainbow' ? ['#f06a5b','#ffd24a','#6fd08c','#7fc4e6','#b48cf0'][Math.floor(now/160)%5] : color;
    }
    drawContactShadow(at(a.x), base, (sheets[sheet]?.meta.cell[0] || 30) * scale * (1 - lift / (LIFT * PIXEL) * 0.35), !!sp.fly);
    const r = drawSheet(sheet, frame, at(a.x), base - hop + fly + 1 - lift, scale, 1, a.face < 0, warp);
    mo.top = (r.full || r).y;
    if (view.outline !== false || hover === a.id) drawOutline(sheet, frame, r, a, warp);
    labels.push({a, r});
    hits.push({rect: r, full: r.full, thing: {type: 'animal', item: a}});
  }
  // 모든 몸을 그린 뒤 상태를 올려, 뒤에 그린 동물이 앞 동물의 말풍선을 덮지 않게 한다.
  for (const {a, r} of labels) { drawMarks(a, r); drawBubble(a, r, now); }
  drawEffects(now);
  for (const {a, r} of labels) drawPetHand(a, r, now);
  drawHearts(now);
  for (let i = floats.length - 1; i >= 0; i -= 1) {          // «+n»
    const f = floats[i], k = (Date.now() - f.t0) / 900;
    if (k >= 1) { floats.splice(i, 1); continue; }
    ctx.globalAlpha = 1 - k; ctx.font = `bold ${Math.round(6 * PIXEL)}px Pretendard, sans-serif`; ctx.textAlign = 'center';
    ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(40,30,60,.85)'; ctx.fillStyle = '#fff3b0';
    ctx.strokeText(f.text, f.x, f.y - k * 14 * PIXEL); ctx.fillText(f.text, f.x, f.y - k * 14 * PIXEL);
    const textWidth = ctx.measureText(f.text).width + 6, textHeight = 9 * PIXEL + 6;
    effectRects.push({x:f.x-textWidth/2, y:f.y-k*14*PIXEL-textHeight, w:textWidth, h:textHeight+4});
    ctx.globalAlpha = 1;
  }
  if (state.breeding) {
    const c = state.facilities.curtain;
    if (c) { ctx.fillStyle = 'rgba(255,236,150,.9)'; for (let i = 0; i < 3; i += 1) if ((frameNo + i * 3) % 9 < 5) ctx.fillRect(at(c.x) - 8 + i * 8, base - 34 - i * 3, 2, 2); }
  }
}

// 손은 캐릭터 원화와 독립된 픽셀 아이콘이다. 원본 interact 프레임의 손 역할을 모든 종에 제공한다.
const PET_HAND = [
  '       ooooo    ',
  '   oooowwwwwo   ',
  ' ooowwwwwwwwwo  ',
  'owwwwwwwwwwwwwo ',
  ' ooswwwwwwwwwwwo',
  '   oswwwwwwwwwwo',
  ' ooowwwwwwwwwwwo',
  'owwwwwwwwwwwwso ',
  ' ooswwwwwwssso  ',
  '   oosssssooo   ',
  '     ooooo      ',
];
const HOLD_HAND = [
  '    ooooooo    ',
  '   owwwwwwwo   ',
  '  owwswswswwo  ',
  '  owwswswswwo  ',
  '  owwwwwwwwwo  ',
  '   oswwwwwwwo  ',
  '    osssssso   ',
  '     oooooo    ',
];
let handRects = [];
function drawPetHand(a, r, now) {
  if (lesson.in_class) return;
  const held = drag?.thing?.item === a;
  if (!held && !(a.special === 1 && a.until > now)) return;
  const map = held ? HOLD_HAND : PET_HAND, p = PIXEL;
  const elapsed = Math.max(0, 1600 - (a.until - now));
  const stroke = held ? 0 : Math.sin(elapsed / 1600 * Math.PI * 6) * 2;
  const direction = a.face < 0 ? -1 : 1;
  const x = Math.round((r.x + r.w * (direction > 0 ? .58 : .42)) / p) * p;
  const y = Math.round((r.y - (held ? 5 : 6) * p) / p) * p;
  ctx.save(); ctx.translate(x + stroke * p, y); ctx.scale(direction, 1);
  ctx.globalAlpha = held ? 1 : Math.min(1, (a.until - now) / 180);
  for (let row = 0; row < map.length; row += 1) for (let col = 0; col < map[row].length; col += 1) {
    const color = {o: '#574a60', w: '#fff7e4', s: '#cbbdd0'}[map[row][col]];
    if (color) { ctx.fillStyle = color; ctx.fillRect((col - 7) * p, row * p, p, p); }
  }
  ctx.restore();
  const rect = {x:x - 11*p, y:y - p, w:24*p, h:(map.length+2)*p};
  handRects.push(rect); effectRects.push(rect); // 투명 창 밖으로 손끝이 잘리지 않게
}

// 품질 표시 · 쌓인 조각 · 아픔 — 몸에 색을 덧칠하면 네모가 비친다(2026-11-06 확인) — 둘레의 작은 표시로만
function drawMarks(a, r) {
  const p = PIXEL, t = tier(a.tier);
  const cx = Math.round(r.x + r.w / 2);
  if (a.tier >= 2 && frameNo % 12 < 7) { ctx.fillStyle = '#ffe58a'; ctx.fillRect(r.x + r.w - p * 2, r.y + p * 2, p, p * 3); ctx.fillRect(r.x + r.w - p * 3, r.y + p * 3, p * 3, p); }
  if (a.badge) {                                          // 인사팀이 걸어 준 사원증
    const cy = Math.round(r.y + r.h * 0.62);
    ctx.fillStyle = '#26356b'; ctx.fillRect(cx - p * 2, cy - p * 2, p, p * 2); ctx.fillRect(cx + p, cy - p * 2, p, p * 2);
    ctx.fillStyle = '#ffffff'; ctx.fillRect(cx - p * 2, cy, p * 4, p * 3); ctx.fillStyle = '#c9952b'; ctx.fillRect(cx - p, cy + p, p * 2, p);
  }
}

// 품질 외곽선 — build.py 가 만든 «둘레만 남긴 흰 테두리»(<시트>_line.png)에 품질 색을 입힌다(화면 밖 캔버스, 읽지 않는다).
// 무지개는 색이 돈다. 특수 캐릭터·외곽선 그림이 없는 시트는 건너뛴다. «화면»에서 끌 수 있다(끄면 마우스를 올릴 때만, 참고 게임과 같음)
const lineImgs = {}, lineCache = {};
function drawOutline(sheet, frame, r, a, warp) {
  const meta = sheets[sheet]?.meta;
  if (!meta?.line || species(a.sp).special) return;
  if (!(sheet in lineImgs)) { lineImgs[sheet] = null; const i = new Image(); i.onload = () => { lineImgs[sheet] = i; }; i.src = `ranch/sprites/${sheet}_line.png`; }
  const img = lineImgs[sheet];
  if (!img) return;
  const t = tier(a.tier);
  const color = t.color === 'rainbow' ? ['#f06a5b', '#ffd24a', '#6fd08c', '#7fc4e6', '#b48cf0'][Math.floor(Date.now() / 160) % 5] : t.color;
  const key = `${sheet}|${color}`;
  if (!lineCache[key]) {
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0); g.globalCompositeOperation = 'source-in'; g.fillStyle = color; g.fillRect(0, 0, c.width, c.height);
    lineCache[key] = c;
  }
  const [cw, ch] = meta.cell;
  ctx.save(); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  ctx.globalAlpha = a.tier === 0 ? 0.55 : 0.95;
  // 몸과 같은 발바닥 중심·변형을 써야 숨쉬기/먹기/쓰다듬기 때 테두리가 떨어지지 않는다.
  ctx.translate(r.x + r.w / 2, r.y + r.h);
  if (warp) ctx.transform(warp.sx, 0, warp.skew, warp.sy, 0, 0);
  if (a.face < 0) ctx.scale(-1, 1);
  ctx.drawImage(lineCache[key], frame * cw, 0, cw, ch, -r.w / 2, -r.h, r.w, r.h);
  ctx.restore();
}

// 머리 위 말풍선 — 참고 게임의 아이콘 여덟(기쁨·더러움·먹이 찾기·가득·사랑·회복·배고픔·아픔). 상태는 가끔(8초마다 2.5초), 일은 그때
const BUBBLE = {happy: 0, dirty: 1, findFood: 2, full: 3, love: 4, healthy: 5, hungry: 6, sick: 7};
function bubbleOf(a, now) {
  if (a.say && now < a.say.until) return a.say.kind;
  if (Math.floor((now + a.born) / 1000) % 8 > 2) return null;
  if (a.health < HEALTH_OK) return 'sick';
  if (a.full < 25) return 'hungry';
  if (state.ground.some((g) => g.kind === 'poop' && Math.abs(g.x - a.x) * worldW() < 140)) return 'dirty';
  if (a.stage === 1 && a.stored >= capOf(a) * 0.95) return 'full';
  if (a.moving && a.full < 80 && state.ground.some((g) => g.kind === 'food')) return 'findFood';
  return null;
}
function say(a, kind, ms = 2200) { a.say = {kind, until: Date.now() + ms}; }
function drawBubble(a, r, now) {
  const kind = bubbleOf(a, now), s = sheets.bubbles;
  if (!kind || !s?.img) return;
  const [cw, ch] = s.meta.cell, h = 11 * PIXEL, w = cw * h / ch;
  const bob = Math.sin(now / 250) * PIXEL * 0.5;
  const x = Math.round(r.x + r.w / 2 + (a.face < 0 ? -w : 0) * 0.3 - w / 2), y = Math.round(r.y - h - 1 + bob);
  ctx.save(); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(s.img, BUBBLE[kind] * cw, 0, cw, ch, x, y, w, h);
  ctx.restore();
  effectRects.push({x: x - 2, y: y - PIXEL * 2, w: w + 4, h: h + PIXEL * 3});   // 창 모양은 그리기도 자른다 — 말풍선 자리를 넣는다
}

// 하트 — 끌고 다니거나 쓰다듬으면 위로 떠오른다
const hearts = [];
function heart(x, y) { hearts.push({x, y, t0: Date.now(), dx: rnd(-6, 6)}); }
function drawHearts(now) {
  for (let i = hearts.length - 1; i >= 0; i -= 1) {
    const h = hearts[i], k = (now - h.t0) / 900;
    if (k >= 1) { hearts.splice(i, 1); continue; }
    const x = h.x + h.dx * k, y = h.y - k * 16 * PIXEL, s = PIXEL * 1.2;
    ctx.globalAlpha = 1 - k; ctx.fillStyle = '#f37c9a';
    ctx.fillRect(x - s, y, s, s); ctx.fillRect(x + s * 0.2, y, s, s); ctx.fillRect(x - s * 1.4, y + s * 0.5, s * 2.8, s * 0.8); ctx.fillRect(x - s * 0.7, y + s * 1.2, s * 1.6, s * 0.7);
    effectRects.push({x:x-s*1.4,y,w:s*2.8,h:s*1.9});
    ctx.globalAlpha = 1;
  }
}

// ── 동물 행동 ───────────────────────────────────────────────
function think(dt) {
  const len = worldW();
  const foods = state.ground.filter((g) => g.kind === 'food');
  for (const a of state.animals) {
    if (a.away || drag?.thing?.item === a) continue;
    // 쓰다듬는 동안 먹이 추적/무작위 행동이 접촉 반응을 덮지 않는다.
    if (a.special === 1 && a.until > Date.now()) {
      a.pose = 1; a.moving = false; a.eating = false; a.sleeping = false; a.sit = false;
      continue;
    }
    a.timer = (a.timer ?? 0) - dt;
    // 먹이가 있으면 배고픈 동물이 걸어간다
    if (a.full < 80 && foods.length && !a.eating) {
      const f = foods.reduce((b, g) => (Math.abs(g.x - a.x) < Math.abs(b.x - a.x) ? g : b));
      if (Math.abs(f.x - a.x) * len < 10) {
        state.ground = state.ground.filter((g) => g !== f); foods.splice(foods.indexOf(f), 1);
        a.full = Math.min(100, a.full + 40); a.eating = true; a.pose = 2; a.moving = false; a.timer = 2.5; a.pop = Date.now(); dirty = true;
        continue;
      }
      a.target = f.x; a.moving = true; a.pose = 0; a.timer = 2; a.face = Math.sign(f.x - a.x) || a.face;
    }
    if (a.timer <= 0) {
      if (a.eating) say(a, 'happy', 1500);
      a.moving = false; a.eating = false; a.sit = false;
      const roll = Math.random();
      const sleepy = night() && Math.random() < 0.3;
      if (!healthy(a)) { a.pose = 4; a.timer = rnd(3, 7); if (roll < 0.3) { a.target = clamp(a.x + rnd(-0.08, 0.08), 0.03, 0.97); a.moving = true; } }
      else if (a.sleeping || sleepy) { a.sleeping = Math.random() < 0.6; a.pose = a.sleeping ? 3 : 0; a.timer = rnd(12, 30); }
      // 참고 게임의 행동 비율 — 걷기 80 : 앉아 쉬기 15 : 잠 5 (animal.gd 의 상수표). 걷기 사이에는 잠깐씩 멈춰 선다
      else if (roll < 0.8) {
        if (Math.random() < 0.35) { a.pose = 0; a.timer = rnd(1.5, 4); }
        else { a.target = clamp(a.x + rnd(-0.22, 0.22), 0.03, 0.97); a.moving = true; a.pose = 0; a.timer = rnd(4, 9); }
      }
      else if (roll < 0.95) { a.pose = 0; a.sit = true; a.timer = rnd(6, 12); }   // 앉아 쉬기 — 숨쉬기만
      else { a.sleeping = true; a.pose = 3; a.timer = rnd(15, 30); }
      if (a.until && Date.now() < a.until) { a.pose = a.special; a.moving = false; a.timer = (a.until - Date.now()) / 1000; }
    }
    if (a.moving && a.target != null) {
      // 빠르기 = 그림 칸/초 — 참고 게임의 걷기(초당 12~20칸)에 맞췄다(2026-11-07). 아기는 조금 느리게, 아프면 느릿느릿
      const speed = species(a.sp).speed * (a.stage ? 1 : 0.85) * (healthy(a) ? 1 : 0.4) * PIXEL / len;
      const step = Math.sign(a.target - a.x) * speed * dt;
      if (step) a.face = Math.sign(step);
      if (Math.abs(a.target - a.x) <= Math.abs(step)) { a.x = a.target; a.moving = false; } else a.x += step;
    }
  }
  const v = state.visitor;
  if (v) {
    if (Date.now() > v.until) { state.visitor = null; dirty = true; }
    else if (v.id !== 'bottle') v.x = clamp(v.x + (v.dir || 0.01) * dt, 0.05, 0.95);
  }
}

function maybeVisit(now) {
  if (state.visitor || now < state.nextVisit || !state.animals.length) return;
  const ids = ['noel', 'clerk', 'airship', 'bottle'];
  const id = pick(state.letters >= D.VISITORS.bottle.letters.length ? ids.slice(0, 3) : ids);
  const v = {id, until: now + 10 * MIN, x: id === 'bottle' ? rnd(0.15, 0.85) : 0.02, dir: id === 'bottle' ? 0 : 0.012};
  if (id === 'clerk') v.order = Math.floor(Math.random() * D.ORDERS.length);
  state.visitor = v;
  state.nextVisit = now + rnd(25, 60) * MIN;
  dirty = true;
  toast(id === 'bottle' ? '물결에 병 편지 하나가 밀려왔어요.' : `틈이 열리고 ${D.VISITORS[id].name}이(가) 찾아왔어요.`);
}

// ── 누르기 ─────────────────────────────────────────────────
function thingAt(x, y) {
  let low = null, top = null;
  for (let i = hits.length - 1; i >= 0; i -= 1) {
    const r = hits[i].rect;
    if (x >= r.x - 2 && x <= r.x + r.w + 2 && y >= r.y - 2 && y <= r.y + r.h + 2) {
      const t = hits[i].thing;
      if (t.type === 'poop' || t.type === 'shard') return {...t, px: x};     // 발치의 작은 것이 동물보다 먼저 — 똥·조각을 치우기 쉽게
      if (hits[i].low) low = {...t, px: x}; else top = top || {...t, px: x};
    }
  }
  return top || low;
}

function blocked() {
  if (!lesson.in_class) return false;
  toast(D.TEXT.classLong(lesson.until));
  return true;
}

canvas.addEventListener('contextmenu', (e) => {                // 오른쪽 단추 = 자세히 (참고 게임과 같음)
  e.preventDefault();
  const t = thingAt(e.clientX, e.clientY);
  if (t?.type === 'animal') openAnimal(t.item);
});
canvas.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  const t = thingAt(e.clientX, e.clientY);
  if (!t) { closePanel(); return; }
  const {left, len} = rangeX();
  if (decorating && (t.type === 'deco' || t.type === 'facility')) {
    if (blocked()) return;
    if (t.type === 'facility') facilityJobs.delete(t.item);
    drag = {thing: t, moved: false, left, len};
    region(true);
    return;
  }
  if (t.type === 'animal' && !lesson.in_class) {
    drag = {thing: t, moved: false, left, len, sx: e.clientX, sy: e.clientY, dropAt: Date.now() + 1500};
    canvas.style.cursor = 'grabbing';
    region(true);
    return;
  }
  click(t);
});
window.addEventListener('mousemove', (e) => {
  if (drag) {
    if (drag.sx != null && Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) < 4 && !drag.moved) return;
    drag.moved = true;
    const item = drag.thing.item;
    item.x = clamp((e.clientX - drag.left) / drag.len, 0.02, 0.98);
    if (drag.thing.type === 'animal') {
      item.pose = 1; item.moving = false; item.eating = false; item.sleeping = false; item.sit = false;
      const t = performance.now();
      if (drag.lx != null) { const v = (e.clientX - drag.lx) / Math.max(8, t - drag.lt) * 16; drag.vx = (drag.vx || 0) * 0.5 + v * 0.5; }
      drag.lx = e.clientX; drag.lt = t;
      if (Math.abs(drag.vx || 0) > 0.8) item.face = Math.sign(drag.vx);
      item.say = {kind: 'love', until: Date.now() + 700};
      if (!drag.heartAt || Date.now() > drag.heartAt) { drag.heartAt = Date.now() + 450; heart(e.clientX, (motionOf(item).top ?? H - GROUND - 30 * PIXEL) - PIXEL * 2); }
      if (item.stage === 1 && Date.now() >= drag.dropAt && item.stored >= 1) {   // 끌고 다니면 쌓아 둔 조각을 흘린다
        const n = Math.min(Math.floor(item.stored), Math.max(1, Math.round(item.income)));
        item.stored -= n; dropShard(item.x, n, item.tier); drag.dropAt = Date.now() + 1500; dirty = true;
      }
    }
    return;
  }
  const t = thingAt(e.clientX, e.clientY);
  hover = t?.type === 'animal' ? t.item.id : null;
  canvas.style.cursor = hover && !lesson.in_class ? 'grab' : t ? 'pointer' : 'default';
  if (t?.type === 'shard' && !lesson.in_class) pickShard(t.item);      // 떨어진 조각은 마우스를 올리면 줍는다
});
window.addEventListener('mouseup', () => {
  if (!drag) return;
  const t = drag.thing, moved = drag.moved;
  drag = null;
  canvas.style.cursor = 'grab';
  dirty = true;
  if (!moved) click(t);
  else if (t.type === 'animal') {
    const mo = motionOf(t.item);
    mo.dropFrom = (1 - (1 - mo.lift) ** 2) * LIFT * PIXEL; mo.dropT = Date.now();
    t.item.timer = 1.5; t.item.pose = 0; say(t.item, 'happy', 1500);
  }
});
window.addEventListener('blur', () => {
  if (drag?.thing.type === 'animal') {
    const a = drag.thing.item, mo = motionOf(a);
    mo.dropFrom = (1 - (1 - mo.lift) ** 2) * LIFT * PIXEL; mo.dropT = Date.now();
    a.timer = 1; a.pose = 0;
  }
  drag = null; hover = null; canvas.style.cursor = 'default';
});

function pickShard(g) {
  if (!state.ground.includes(g) || g.fly) return;              // 날아가는 중에는 줍지 않는다
  const {left, len} = rangeX();
  floatText(left + g.x * len, H - GROUND - 12 * PIXEL, `+${fmt(g.n || 1)}`);
  state.ground = state.ground.filter((x) => x !== g);
  earn(g.n || 1); dirty = true; paintHud();
}

function click(t) {
  if (t.type === 'animal') {
    const a = t.item;
    if (lesson.in_class) return openAnimal(a);
    // 손과 표정의 시간축을 함께 다시 시작한다. 연타해도 재화는 아래에서 한 번만 수령한다.
    a.special = 1; a.until = Date.now() + 1600; a.timer = 1.6; a.pop = Date.now();
    a.pose = 1; a.moving = false; a.eating = false; a.sleeping = false; a.sit = false;
    nativeClocks.delete(a);
    say(a, 'love', 1600);
    const petRange = rangeX();
    heart(petRange.left + a.x * petRange.len, H - GROUND - species(a.sp).size[a.stage] * PIXEL);
    if (a.stage === 1 && a.stored >= 1 && !lesson.in_class) {           // 어른을 누르면 쌓아 둔 조각을 받는다
      const n = Math.floor(a.stored);
      a.stored -= n; earn(n);
      emitEffect('coins', a.x, a.tier, n);
      const {left, len} = rangeX();
      floatText(left + a.x * len, H - GROUND - (species(a.sp).size[1] + 4) * PIXEL, `+${fmt(n)}`);
      dirty = true; paintHud();
      return;
    }
    return; // 왼쪽 = 쓰다듬기/수령, 오른쪽 = 자세히. 패널이 손을 가리지 않는다.
  }
  if (t.type === 'shard') { if (!blocked()) pickShard(t.item); return; }
  if (t.type === 'poop') {
    if (blocked()) return;
    cleanPoop(t.item);
    return;
  }
  if (t.type === 'food') return;
  if (t.type === 'ground') {                                           // 빈 땅 = 먹이 떨어뜨리기
    if (blocked()) return;
    if (state.food <= 0) { toast('먹이 창고가 비었어요. 상점에서 먹이를 사요.'); return; }
    const {left, len} = rangeX();
    state.food -= 1;
    state.ground.push({id: uid(), kind: 'food', x: clamp((t.px - left) / len, 0.02, 0.98), at: Date.now(), drop: Date.now()});
    dirty = true; paintHud();
    return;
  }
  if (t.type === 'visitor') return openVisitor();
  if (t.type === 'facility' && !decorating) return t.kind === 'curtain' ? openCurtain() : openFacility(t.kind);
  if (decorating) return openDecoItem(t);
}

// ── 패널 ───────────────────────────────────────────────────
function openPanel(kind, title, html, anchorX) {
  panel = {kind};
  $('p-title').textContent = title;
  $('p-body').innerHTML = html;
  dress($('p-body'));
  panel.anchorX = anchorX;
  $('panel').hidden = false;
  placePanel();
  region();
}
function placePanel() {
  const w = 330, x = clamp((panel.anchorX ?? W - 180) - w / 2, 4, Math.max(4, W - w - 4));
  $('panel').style.left = `${x}px`;
}
function closePanel() { if (!panel) return; panel = null; $('panel').hidden = true; region(); }
$('p-close').addEventListener('click', closePanel);

function bar(label, value) {
  return `<div class="bar"><span>${label}</span><i><b class="${value < HEALTH_OK ? 'low' : ''}" data-w="${Math.round(value)}"></b></i></div>`;
}
const tierChip = (t) => `<span class="tier" data-tier="${t}">${esc(tier(t).name)}</span>`;
const sellPrice = (a) => Math.round(species(a.sp).price * 0.4 * tier(a.tier).mult * (a.stage ? 1.5 : 1));

function openAnimal(a) {
  const sp = species(a.sp), st = sp.special ? {name: '특수 캐릭터'} : D.STAGES[a.stage];
  const care = !lesson.in_class;
  const left = a.stage === 0 ? Math.max(0, Math.ceil(sp.grow - a.grow / MIN)) : 0;
  const why = !healthy(a) ? (a.full <= 0 ? D.TEXT.hungry : D.TEXT.sick) : a.full < 30 ? D.TEXT.hungry : '';
  openPanel('animal', a.name, `
    <div class="row">${portrait(qualitySheet(a.stage ? sp.sheet : sp.babySheet, a.tier))}<div class="name">${sp.special ? '<span class="tier special">특수</span>' : tierChip(a.tier)} ${esc(a.stage ? sp.name : sp.baby || sp.name)} · ${st.name}${a.badge ? ' · 사원증' : ''}
      <small>${esc(sp.origin)}에서 흘러왔어요${sp.special ? ' · 다마고찌에서 온 특별한 친구예요' : ` · ${esc(tier(a.tier).note)}`}</small></div></div>
    ${bar('배', a.full)}${bar('건강', a.health)}
    <p class="note">${a.stage === 0 ? `건강하게 ${left}분 더 지내면 어른이 돼요` : `1분에 ${fmt(a.income)}조각 · 쌓아 둔 것 ${fmt(a.stored)}/${fmt(capOf(a))}`}${why ? ` · ${esc(why)}` : ''}</p>
    ${care ? `<div class="acts">
      <button class="btn" data-do="feed" ${state.food ? '' : 'disabled'}>곁에 먹이 (${state.food})</button>
      <button class="btn soft" data-do="cure" ${state.cures ? '' : 'disabled'}>치료제 (${state.cures})</button>
      ${state.inventory.lunch ? `<button class="btn soft" data-do="lunch">자습 도시락 (${state.inventory.lunch})</button>` : ''}
      <button class="btn soft" data-do="rename">이름 짓기</button>
      <button class="btn soft" data-do="fav">${a.fav ? '즐겨찾기 풀기' : '즐겨찾기'}</button>
      <button class="btn soft" data-do="sell" ${a.fav ? 'disabled' : ''}>틈으로 보내기 (+${fmt(sellPrice(a))})</button></div>`
      : `<p class="note">${esc(D.TEXT.classLong(lesson.until))}</p>`}`, rangeX().left + a.x * rangeX().len);
  $('p-body').onclick = (e) => {
    const act = e.target.closest('[data-do]')?.dataset.do;
    if (!act || blocked()) return;
    const set = (pose, ms) => { a.special = pose; a.until = Date.now() + ms; a.timer = 0; };
    if (act === 'feed' && state.food > 0) { state.food -= 1; state.ground.push({id: uid(), kind: 'food', x: clamp(a.x + 0.01, 0.02, 0.98), at: Date.now()}); }
    if (act === 'cure' && state.cures > 0) { state.cures -= 1; a.health = Math.min(100, a.health + 50); set(1, 1500); }
    if (act === 'lunch') { state.inventory.lunch -= 1; for (const x of state.animals) { x.full = 100; x.health = 100; } toast('자습 도시락을 나눠 먹었어요. 모두 배부르고 건강해요.'); }
    if (act === 'fav') a.fav = !a.fav;
    if (act === 'sell') {
      if (!confirmOnce(e.target, a.tier >= 2 ? '품질이 높은 아이예요. 정말 보낼까요?' : '정말 보낼까요?')) return;
      const n = sellPrice(a);
      earn(n); state.animals = state.animals.filter((x) => x !== a); dirty = true; paintHud(); closePanel();
      toast(`${a.name}이(가) 틈 너머 원래 세계로 돌아갔어요. +${fmt(n)}`);
      return;
    }
    if (act === 'rename') {
      $('p-body').innerHTML = `<p>새 이름을 지어 주세요.</p><input class="name-edit" maxlength="12" value="${esc(a.name)}">
        <div class="acts"><button class="btn" data-ok>정하기</button></div>`;
      const input = $('p-body').querySelector('input'); input.focus(); input.select();
      $('p-body').onclick = (ev) => { if (!ev.target.closest('[data-ok]')) return; const n = input.value.trim().slice(0, 12); if (n) a.name = n; dirty = true; openAnimal(a); };
      return;
    }
    dirty = true; paintHud(); openAnimal(a);
  };
}

function confirmOnce(button, text) {          // 한 번 더 눌러야 하는 단추 (되돌릴 수 없는 것)
  if (button.dataset.sure) return true;
  button.dataset.sure = '1'; button.textContent = text;
  return false;
}

// 상점 — 뽑기 · 물건 · 시설 · 목장
let shopTab = 'animals';
function openShop(tab = shopTab) {
  shopTab = tab;
  const care = !lesson.in_class;
  const tabs = [['animals', '동물'], ['storage', `창고${storage().length ? ` ${storage().length}` : ''}`], ['goods', '물건'], ['facility', '시설'], ['bg', '배경'], ['farm', '목장']]
    .map(([k, n]) => `<button class="btn ${k === tab ? '' : 'soft'}" data-tab="${k}">${n}</button>`).join('');
  let body = '';
  if (tab === 'animals') {
    const full = storage().length >= STORAGE_MAX;
    body = `<p class="note">뽑으면 품질(흐린·물빛·별빛·노을·무지개)이 정해져요. 높을수록 빨리 쌓아요. 칸 ${state.animals.length}/${state.slots} · 뽑은 아이는 데려오기 전까지 창고에 있어요(${storage().length}/${STORAGE_MAX})</p>`
      + D.SPECIES.map((sp) => state.unlocked[sp.id]
        ? `<div class="row">${portrait(sp.sheet)}<div class="name">${esc(sp.name)}<small>${sp.special ? `특수 캐릭터 · 1분 ${sp.income}조각 · 품질·번식 없음` : `1분 ${sp.income}조각부터 · 어른까지 ${sp.grow}분`}</small></div>
           <button class="btn" data-draw="${sp.id}" ${care && !full && state.shards >= sp.price ? '' : 'disabled'}>${fmt(sp.price)}</button></div>`
        : `<div class="row locked">${portrait(sp.sheet)}<div class="name">???<small>${esc(unlockText(sp))}</small></div></div>`).join('');
  } else if (tab === 'storage') {
    const list = storage();
    body = `<p class="note">뽑았거나 칸이 없어 못 들어온 아이들이에요. 칸 ${state.animals.length}/${state.slots} · 창고 ${list.length}/${STORAGE_MAX}</p>`
      + (list.length ? list.map((x) => {
        const sp = species(x.sp), sheet = sp.special ? sp.sheet : qualitySheet(sp.babySheet, x.tier);
        return `<div class="row">${portrait(sheet)}<div class="name">${sp.special ? '<span class="tier special">특수</span>' : tierChip(x.tier)} ${esc(sp.special ? sp.name : sp.baby)}
          <small>어른이 되면 1분에 ${fmt(x.income)}조각</small></div>
          <button class="btn" data-bring="${x.id}" ${care && roomLeft() ? '' : 'disabled'}>데려오기</button>
          <button class="btn soft" data-free="${x.id}" ${care ? '' : 'disabled'}>놓아주기</button></div>`;
      }).join('') : '<p class="note">창고가 비었어요.</p>');
  } else if (tab === 'goods') {
    body = D.GOODS.map((g) => `<div class="row">${icon(g.icon)}<div class="name">${esc(g.name)}<small>${esc(g.note)}</small></div>
        <button class="btn" data-good="${g.id}" ${care && state.shards >= g.price ? '' : 'disabled'}>${fmt(g.price)}</button></div>`).join('')
      + Object.entries(D.GIFTS).filter(([k]) => state.inventory[k]).map(([k, g]) => `<div class="row">${icon(g.icon)}
        <div class="name">${esc(g.name)} ×${state.inventory[k]}<small>${esc(g.from)}에서 · ${esc(g.note)}</small></div>
        ${k === 'lunch' ? '' : `<button class="btn soft" data-use="${k}" ${care ? '' : 'disabled'}>쓰기</button>`}</div>`).join('');
  } else if (tab === 'facility') {
    body = Object.entries(D.FACILITIES).map(([k, f]) => {
      const level = lv(k), cost = f.cost[level];
      const now = f.every ? `${f.every[Math.max(0, level - 1)]}초마다` : `${f.minutes[Math.max(0, level - 1)]}분`;
      return `<div class="row">${icon(f.icon)}<div class="name">${esc(f.name)} ${level ? `Lv.${level}` : ''}<small>${esc(f.note)}${level ? ` · 지금 ${now}` : ''}</small></div>
        ${cost == null ? '<span class="note">최고 레벨</span>' : `<button class="btn" data-fac="${k}" ${care && state.shards >= cost ? '' : 'disabled'}>${level ? '올리기' : '들이기'} ${fmt(cost)}</button>`}</div>`;
    }).join('');
  } else if (tab === 'bg') {
    body = D.BACKDROPS.map((b) => {
      const owned = state.bgOwned?.[b.id], on = (state.bg || 'meadow') === b.id;
      return `<div class="row"><div class="name">${esc(b.name)}${on ? ' · 쓰는 중' : ''}<small>${esc(b.note)}</small></div>
        ${on ? '' : owned ? `<button class="btn soft" data-bg="${b.id}">쓰기</button>` : `<button class="btn" data-bg="${b.id}" ${care && state.shards >= b.price ? '' : 'disabled'}>${fmt(b.price)}</button>`}</div>`;
    }).join('');
  } else {
    const slotCost = D.SLOTS.cost(state.slots + 1);
    const left = today.coins_left;
    body = `<div class="row"><div class="name">동물 칸 늘리기<small>지금 ${state.slots}칸 (최대 ${D.SLOTS.max})</small></div>
        <button class="btn" data-slot ${care && state.slots < D.SLOTS.max && state.shards >= slotCost ? '' : 'disabled'}>${fmt(slotCost)}</button></div>
      <div class="row"><div class="name">목장 너비·자리·크기<small>단추 줄의 «화면»에서 바꿔요 (조각이 들지 않아요)</small></div>
        <button class="btn soft" data-view-open>화면</button></div>
      <div class="row"><div class="name">틈새 조각 → 스페이스기전 코인<small>조각 ${today.unit}개 → ${today.rate}코인 · ${online ? (left == null ? '' : `오늘 ${left}코인 더`) : '스페이스기전에 닿으면 바꿀 수 있어요'}</small></div>
        <button class="btn" data-sell ${care && online && state.shards >= today.unit && left !== 0 ? '' : 'disabled'}>바꾸기</button></div>
      <p class="note">모은 조각 누계 ${fmt(state.earned)} · 어른으로 키운 동물 ${state.adultsRaised}마리</p>`;
  }
  openPanel('shop', '상점', `<div class="acts tabs">${tabs}</div>${care ? '' : `<p class="note">${esc(D.TEXT.classLong(lesson.until))} 구경만 할 수 있어요.</p>`}${body}`);
  $('p-body').onclick = async (e) => {
    const tabBtn = e.target.closest('[data-tab]')?.dataset.tab;
    if (tabBtn) { openShop(tabBtn); return; }
    if (e.target.closest('[data-view-open]')) { openView(); return; }
    if (blocked()) return;
    const el = e.target.closest('button');
    if (!el || el.disabled) return;
    if (el.dataset.draw) return drawAnimal(el.dataset.draw);
    if (el.dataset.bring) { const x = storage().find((y) => y.id === el.dataset.bring); if (x && bringIn(x)) toast(`${species(x.sp).special ? species(x.sp).name : `${tier(x.tier).name} ${species(x.sp).baby}`}이(가) 목장에 왔어요.`); }
    if (el.dataset.free) {
      const x = storage().find((y) => y.id === el.dataset.free);
      if (x && x.tier >= 2 && !confirmOnce(el, '품질이 높은 아이예요. 정말 놓아줄까요?')) return;
      if (x) { unstash(x); toast(`${species(x.sp).name}이(가) 틈 너머로 돌아갔어요.`); }
    }
    if (el.dataset.good) buyGood(el.dataset.good);
    if (el.dataset.use) useItem(el.dataset.use);
    if (el.dataset.fac) buyFacility(el.dataset.fac);
    if (el.dataset.bg) {
      const b = D.BACKDROPS.find((x) => x.id === el.dataset.bg);
      state.bgOwned ||= {none: true, meadow: true};
      if (!state.bgOwned[b.id]) { if (state.shards < b.price) return; state.shards -= b.price; state.bgOwned[b.id] = true; toast(`${b.name}을(를) 들였어요.`); }
      state.bg = b.id; lastRegion = '';
    }
    if (el.hasAttribute('data-slot')) { const c = D.SLOTS.cost(state.slots + 1); if (state.shards >= c) { state.shards -= c; state.slots += 1; toast(`칸이 ${state.slots}칸이 됐어요.`); } }
    if (el.hasAttribute('data-view-open')) { openView(); return; }
    if (el.hasAttribute('data-sell')) { await sell(); return; }
    dirty = true; paintHud(); openShop();
  };
}

// 뽑기 — 참고 게임처럼 품질을 보고 «데려오기» 또는 «놓아주기»(값은 돌려받지 못한다)
function drawAnimal(id, minTier = 0, free = false) {
  const sp = species(id);
  if (storage().length >= STORAGE_MAX) { toast('창고가 가득 찼어요. 상점 «창고»에서 데려오거나 놓아주세요.'); return; }
  if (!free) { if (state.shards < sp.price) return; state.shards -= sp.price; }
  const t = sp.special ? 0 : rollTier(minTier);
  const entry = stash(id, t);
  if (sp.special) {
    const a = bringIn(entry); dirty = true; paintHud();
    if (!a) { openShop('storage'); return; }
    openPanel('draw', '틈에서 온 특별한 친구', `<div class="row">${portrait(sp.sheet, 40)}<div class="name"><span class="tier special">특수</span> ${esc(sp.name)}
        <small>${esc(sp.origin)}에서 왔어요 · 1분에 ${fmt(sp.income)}조각</small></div></div><div class="acts"><button class="btn" data-ok>반가워요</button></div>`);
    $('p-body').onclick = (e) => { if (e.target.closest('[data-ok]')) closePanel(); };
    return;
  }
  dirty = true; paintHud();
  openPanel('draw', '틈에서 굴러온 아기', `<div class="row">${portrait(qualitySheet(sp.babySheet, t), 40)}<div class="name">${tierChip(t)} ${esc(sp.baby)}
      <small>${esc(tier(t).note)} · 어른이 되면 1분에 ${fmt(sp.income * tier(t).mult)}조각</small></div></div>
    <div class="acts"><button class="btn" data-keep>데려오기</button>${free ? '' : `<button class="btn soft" data-again ${state.shards >= sp.price ? '' : 'disabled'}>놓아주고 한 번 더 (${fmt(sp.price)})</button>`}
      <button class="btn soft" data-let>놓아주기</button></div>
    <p class="note">창을 닫아도 창고에 남아요 — 상점 «창고»에서 데려올 수 있어요.${roomLeft() ? '' : ' 지금은 칸이 가득 찼어요.'}</p>`);
  $('p-body').onclick = (e) => {
    if (e.target.closest('[data-keep]')) {
      if (!bringIn(entry)) return;                     // 칸이 가득 — 창고에 남는다
      closePanel(); toast(`${tier(t).name} ${sp.name}이(가) 목장에 왔어요.`);
    } else if (e.target.closest('[data-again]')) {
      if (t >= 2 && !confirmOnce(e.target.closest('[data-again]'), '품질이 높은 아이예요. 그래도 놓아줄까요?')) return;
      unstash(entry); drawAnimal(id, minTier);
    } else if (e.target.closest('[data-let]')) {
      if (t >= 2 && !confirmOnce(e.target.closest('[data-let]'), '품질이 높은 아이예요. 정말 놓아줄까요?')) return;
      unstash(entry); closePanel(); toast(`${sp.name}이(가) 틈 너머로 돌아갔어요.`);
    }
  };
}

function buyGood(id) {
  const g = D.GOODS.find((x) => x.id === id);
  if (!g || state.shards < g.price) return;
  state.shards -= g.price;
  if (g.kind === 'food') state.food += g.amount;
  if (g.kind === 'cure') state.cures += g.amount;
  if (g.kind === 'deco') state.deco.push({id: uid(), kind: g.id, x: rnd(0.1, 0.9)});
  toast(`${g.name}을(를) 샀어요.`);
}

function buyFacility(k) {
  const f = D.FACILITIES[k], level = lv(k), cost = f.cost[level];
  if (cost == null || state.shards < cost) return;
  state.shards -= cost;
  if (!state.facilities[k]) state.facilities[k] = {lv: 0, x: {broom: 0.06, feeder: 0.2, jar: 0.94, curtain: 0.8}[k], t: 0};
  state.facilities[k].lv = level + 1;
  toast(level ? `${f.name}이(가) Lv.${level + 1}이 됐어요.` : `${f.name}을(를) 들였어요.`);
}

function openFacility(k) {
  const f = D.FACILITIES[k], level = lv(k);
  openPanel('facility', `${f.name} Lv.${level}`, `<p>${esc(f.note)}</p><p class="note">${esc(f.from)}에서 왔어요 · 지금 ${f.every[level - 1]}초마다 일해요.</p>
    <div class="acts"><button class="btn" data-up>상점에서 올리기</button></div>`);
  $('p-body').onclick = (e) => { if (e.target.closest('[data-up]')) openShop('facility'); };
}

function useItem(kind) {
  if (!state.inventory[kind]) return;
  if (kind === 'seed') { state.inventory.seed -= 1; state.seeds.push({x: rnd(0.15, 0.85), until: Date.now() + 24 * HOUR}); toast('별 씨앗을 심었어요. 근처 동물이 하루 동안 1.5배 빨리 쌓아요.'); }
  if (kind === 'egg') {
    if (storage().length >= STORAGE_MAX) { toast('창고가 가득 찼어요.'); return; }
    state.inventory.egg -= 1;
    const sp = pick(D.SPECIES.filter((s) => !s.special && state.unlocked[s.id]));
    drawAnimal(sp.id, 1, true);
    return;
  }
  dirty = true; openShop(); paintHud();
}

async function sell() {
  const times = Math.floor(state.shards / today.unit);
  if (times < 1) return;
  await save(true);                                  // 서버가 가진 조각으로 바꾸므로 먼저 올린다
  try {
    const got = await api('ranch_call', {work: 'sell', body: {p_times: Math.min(times, Math.max(1, today.coins_left ?? times))}});
    if (got?.ranch?.state) { state = upgrade(got.ranch.state); version = got.ranch.version; }
    if (got?.today) today = got.today;
    toast(`${got?.coins ?? 0}코인으로 바꿨어요. 스페이스기전 지갑에 들어갔어요.`);
  } catch (error) { toast(error.message); }
  paintHud(); if (panel?.kind === 'shop') openShop();
}

function openDex() {
  const total = D.SPECIES.reduce((n, sp) => n + (sp.special ? 1 : D.TIERS.length), 0);
  const seen = Object.keys(state.dex).filter((k) => species(k.split(':')[0])).length;
  const cells = D.SPECIES.map((sp) => (sp.special ? [D.TIERS[0]] : D.TIERS).map((t) => {
    const got = state.dex[`${sp.id}:${t.id}`];
    return `<div class="${got ? '' : 'miss'}" title="${got ? '' : '아직 못 만났어요'}">${portrait(qualitySheet(sp.sheet, t.id))}<br>${sp.special ? `${esc(sp.name)} · 특수` : t.id === 0 ? esc(sp.name) : esc(t.name)}</div>`;
  }).join('')).join('');
  openPanel('dex', `도감 ${seen}/${total}`, `<p class="note">틈으로 흘러온 아이들이에요. 줄마다 흐린·물빛·별빛·노을·무지개, 다마고찌 친구는 특수 캐릭터 한 칸.</p>
    <div class="dex">${cells}</div><h2>병 편지 ${state.letters}/${D.VISITORS.bottle.letters.length}</h2>
    ${D.VISITORS.bottle.letters.slice(0, state.letters).map((t) => `<p class="note">«${esc(t)}»</p>`).join('')}`);
}

function reward(minutes) { return Math.max(10, Math.round(totalIncome() * minutes)); }

function openVisitor() {
  const v = state.visitor;
  if (!v) return;
  const info = D.VISITORS[v.id];
  if (v.id === 'bottle') {
    if (blocked()) return;
    const text = info.letters[state.letters] || pick(info.letters);
    state.letters = Math.min(info.letters.length, state.letters + 1);
    state.visitor = null; dirty = true;
    openPanel('visitor', '병 편지', `<p>${esc(text)}</p><p class="note">${esc(info.from)}에서 흘러온 편지예요. 도감에 모아 둘게요.</p>`);
    return;
  }
  const say = v.say || (v.say = pick(info.lines));
  let body = `<p>${esc(say)}</p><p class="note">${esc(info.from)}</p>`;
  if (v.id === 'noel' && !v.done) body += `<div class="acts"><button class="btn" data-take ${lesson.in_class ? 'disabled' : ''}>편지 받기</button></div>`;
  if (v.id === 'clerk' && !v.done) {
    const o = D.ORDERS[v.order];
    body += `<h2>실사 항목</h2><p>${esc(o.text)}</p><div class="acts"><button class="btn" data-check ${lesson.in_class ? 'disabled' : ''}>보여 주기 (조각 ${fmt(reward(o.minutes))} · 사원증)</button></div>`;
  }
  if (v.id === 'airship') body += info.shop.map((s) => `<div class="row">${icon(D.GIFTS[s.id].icon)}
      <div class="name">${esc(D.GIFTS[s.id].name)}<small>${esc(D.GIFTS[s.id].note)}</small></div>
      <button class="btn" data-air="${s.id}" ${!lesson.in_class && state.shards >= reward(s.minutes) ? '' : 'disabled'}>${fmt(reward(s.minutes))}</button></div>`).join('');
  if (v.done) body += '<p class="note">고마워요. 잠시 뒤 틈으로 돌아갈게요.</p>';
  openPanel('visitor', info.name, body);
  $('p-body').onclick = (e) => {
    if (blocked()) return;
    if (e.target.closest('[data-take]')) {
      const [kind, n] = pick(info.gift);
      if (kind === 'food') state.food += n; else if (kind === 'cure') state.cures += n;
      else if (kind === 'shardMinutes') earn(reward(n)); else state.inventory[kind] += n;
      v.done = true;
      v.say = `편지와 함께 ${kind === 'food' ? `먹이 ${n}개` : kind === 'cure' ? '치료제' : kind === 'shardMinutes' ? `틈새 조각 ${fmt(reward(n))}개` : D.GIFTS[kind].name}를 두고 갈게요.`;
    }
    if (e.target.closest('[data-check]')) {
      const o = D.ORDERS[v.order], n = o.need;
      const ok = (n.adult ? adults().length >= n.adult : true) && (n.count ? state.animals.length >= n.count : true)
        && (n.clean ? !state.ground.some((g) => g.kind === 'poop') : true) && (n.food ? state.food >= n.food : true)
        && (n.healthy ? state.animals.filter((a) => a.health >= 80).length >= n.healthy : true)
        && (n.tier ? state.animals.some((a) => a.tier >= n.tier) : true);
      if (ok) {
        earn(reward(o.minutes));
        const plain = state.animals.find((a) => !a.badge);
        if (plain) plain.badge = true;
        v.done = true; v.say = `실사 통과예요. 서류에 도장 찍어 둘게요.${plain ? ` ${plain.name}에게 사원증을 걸어 줬어요. 직급은 «인턴».` : ''}`;
      } else v.say = '아직은 조금 부족해요. 다음에 다시 올게요.';
    }
    const air = e.target.closest('[data-air]')?.dataset.air;
    if (air) { const s = info.shop.find((x) => x.id === air); const c = reward(s.minutes); if (state.shards >= c) { state.shards -= c; state.inventory[air] += 1; toast(`${D.GIFTS[air].name}을(를) 샀어요.`); } }
    dirty = true; paintHud(); openVisitor();
  };
}

function openCurtain() {
  const c = state.facilities.curtain, busy = state.breeding;
  const groups = {};
  for (const a of adults()) if (healthy(a) && !species(a.sp).special) (groups[a.sp] ||= []).push(a);
  const pairs = Object.entries(groups).filter(([, list]) => list.length >= 2);
  const minutes = D.FACILITIES.curtain.minutes[c.lv - 1];
  const left = busy ? Math.max(1, Math.ceil((busy.until - Date.now()) / MIN)) : 0;
  const child = (sp) => {
    const two = groups[sp].sort((x, y) => y.income - x.income).slice(0, 2);
    const rainbow = two.some((a) => a.tier === 4);
    const capInc = species(sp).income * tier(D.BREED_CAP_TIER).mult;
    const income = rainbow ? two[0].income + two[1].income : Math.min(capInc, two[0].income + two[1].income);
    const ratio_ = income / species(sp).income;
    const t = [...D.TIERS].reverse().find((x) => ratio_ >= x.mult)?.id ?? 0;
    return {two, income, tier: rainbow ? Math.max(t, 4) : Math.min(t, D.BREED_CAP_TIER)};
  };
  openPanel('curtain', `별빛 장막 Lv.${c.lv}`, busy ? `<p>${esc(species(busy.sp).name)} 둘이 장막 안에 있어요. ${left}분쯤 뒤에 새끼가 나와요.</p>`
    : `<p class="note">같은 종 어른 둘이 들어가면 ${minutes}분 뒤 새끼가 나와요. 새끼의 수익 = 부모 수익의 합 (무지개 부모가 아니면 노을 품질까지).</p>
      ${pairs.length ? pairs.map(([sp]) => { const k = child(sp); return `<div class="row">${portrait(species(sp).sheet)}<div class="name">${esc(species(sp).name)}
          <small>${esc(k.two[0].name)} + ${esc(k.two[1].name)} → ${tier(k.tier).name} · 1분 ${fmt(k.income)}조각</small></div>
        <button class="btn" data-pair="${sp}" ${lesson.in_class || state.animals.length >= state.slots ? 'disabled' : ''}>들여보내기</button></div>`; }).join('')
        : '<p>건강한 같은 종 어른이 둘 있어야 해요.</p>'}
      ${state.animals.length >= state.slots ? '<p class="note">새끼가 들어갈 빈 칸이 있어야 해요.</p>' : ''}`, rangeX().left + c.x * rangeX().len);
  $('p-body').onclick = (e) => {
    const sp = e.target.closest('[data-pair]')?.dataset.pair;
    if (!sp || blocked()) return;
    const k = child(sp);
    for (const a of k.two) a.away = true;
    state.breeding = {sp, parents: k.two.map((a) => a.id), until: Date.now() + minutes * MIN, income: k.income, tier: k.tier};
    animateFacility('curtain', state.facilities.curtain, state.facilities.curtain.x, 'start');
    dirty = true; openCurtain();
  };
}

function openDecoItem(t) {
  const name = t.type === 'deco' ? D.GOODS.find((s) => s.id === t.item.kind)?.name : D.FACILITIES[t.kind]?.name;
  openPanel('deco', name || '소품', `<p class="note">끌어서 옮길 수 있어요.</p>
    ${t.type === 'deco' ? '<div class="acts"><button class="btn soft" data-remove>치우기 (조각 절반 돌려받기)</button></div>' : ''}`);
  $('p-body').onclick = (e) => {
    if (!e.target.closest('[data-remove]') || blocked()) return;
    state.deco = state.deco.filter((d) => d !== t.item);
    earn(Math.floor((D.GOODS.find((s) => s.id === t.item.kind)?.price || 0) / 2));
    dirty = true; closePanel(); paintHud();
  };
}

// «화면» — 참고 게임의 «게임 창 조정»: 너비·가로 위치·높이·크기·항상 위. 수업 중에도 바꿀 수 있다(돌보기가 아니다)
function openView() {
  const v = view;
  const row = (label, key, min, max, step, value, note) => `<div class="row"><div class="name">${label}<small>${note}</small></div>
    <input type="range" data-view="${key}" min="${min}" max="${max}" step="${step}" value="${value}"></div>`;
  openPanel('view', '화면', `<p class="note">목장을 화면 아래에 어떻게 둘지 정해요. 이 PC 에 기억해요.</p>
    ${row('너비', 'width', 0.2, 1, 0.05, v.width, `화면 너비의 ${Math.round(v.width * 100)}%`)}
    ${row('가로 위치', 'x', 0, 1, 0.01, v.x, v.width >= 1 ? '너비가 화면 전체면 움직이지 않아요' : '왼쪽 ↔ 오른쪽')}
    ${row('높이', 'lift', 0, 400, 10, v.lift, `${mode === 'dock' ? '독' : '작업 표시줄'} 위로 ${v.lift}px 올리기`)}
    ${row('크기', 'zoom', 1, 6, 1, zoom, `그림 1칸 = ${zoom}픽셀${v.zoom ? '' : ' (화면 해상도에 맞춘 기본값)'}`)}
    <div class="row"><div class="name">항상 위<small>켜면 다른 창 위에 늘 보여요. 끄면 독과 함께 가려져요.</small></div>
      <input type="checkbox" data-view="top" ${v.top ? 'checked' : ''}></div>
    <div class="row"><div class="name">품질 색 테두리<small>동물 둘레에 품질 색을 둘러요. 끄면 마우스를 올릴 때만 보여요.</small></div>
      <input type="checkbox" data-view="outline" ${v.outline !== false ? 'checked' : ''}></div>
    <div class="acts"><button class="btn soft" data-view-reset>기본값으로</button></div>`);
  const send = async (next) => {
    try { const got = await api('ranch_view', {view: next}); view = got.view; setTimeout(poll, 400); } catch (error) { toast(error.message); }
  };
  $('p-body').oninput = (e) => {
    const el = e.target.closest('[data-view]');
    if (!el || el.type === 'checkbox') return;
    const key = el.dataset.view, value = Number(el.value);
    const small = el.closest('.row').querySelector('small');
    if (key === 'width') small.textContent = `화면 너비의 ${Math.round(value * 100)}%`;
    if (key === 'lift') small.textContent = `위로 ${value}px 올리기`;
    if (key === 'zoom') small.textContent = `그림 1칸 = ${value}픽셀`;
  };
  $('p-body').onchange = (e) => {
    const el = e.target.closest('[data-view]');
    if (!el) return;
    const key = el.dataset.view;
    send({...view, [key]: key === 'top' || key === 'outline' ? el.checked : key === 'zoom' || key === 'lift' ? Math.round(Number(el.value)) : Number(el.value)});
  };
  $('p-body').onclick = (e) => {
    if (e.target.closest('[data-view-reset]')) send({width: 1, x: 0.5, lift: 0, zoom: null, top: false, outline: true}).then(() => setTimeout(openView, 600));
  };
}

function openWelcome() {
  const a = newAnimal('rabbit'); a.x = 0.5; a.full = 40;   // 이름은 «아기 토끼», 어른이 되면 «토끼»
  state.animals.push(a); state.welcomed = true; dirty = true;
  openPanel('welcome', '별사이 목장', `<p>${esc(D.TEXT.welcome)}</p>${D.TEXT.tips.map((t) => `<p class="note">· ${esc(t)}</p>`).join('')}
    <p class="note">수업 시간에는 동물이 지내는 모습만 볼 수 있고, 돌보기는 쉬는 시간에 해요.</p>
    <div class="acts"><button class="btn" data-ok>시작하기</button></div>`);
  $('p-body').onclick = (e) => { if (e.target.closest('[data-ok]')) { closePanel(); save(true); } };
}

$('b-shop').addEventListener('click', () => (panel?.kind === 'shop' ? closePanel() : openShop()));
$('b-dex').addEventListener('click', () => (panel?.kind === 'dex' ? closePanel() : openDex()));
$('b-view').addEventListener('click', () => (panel?.kind === 'view' ? closePanel() : openView()));
$('b-deco').addEventListener('click', () => {
  if (!decorating && blocked()) return;
  decorating = !decorating; $('b-deco').classList.toggle('on', decorating);
  toast(decorating ? '꾸미기 — 소품·시설을 끌어서 옮겨요. 다시 누르면 끝나요.' : '꾸미기를 마쳤어요.');
});

// ── 띠·창 모양 ─────────────────────────────────────────────
function paintHud() {
  $('shards').textContent = state ? fmt(state.shards) : 0;
  $('food').textContent = state ? state.food : 0;
  const badge = $('badge');
  badge.hidden = !(lesson.in_class || !online);
  badge.textContent = lesson.in_class ? D.TEXT.class : D.TEXT.offline;
  badge.className = `badge${lesson.in_class ? '' : ' off'}`;
  const {left, len} = rangeX();
  $('hud').style.right = `${Math.max(4, W - (left + len) + 4)}px`;
}

let lastRegion = '';
let sceneryRegionCache = null;
function sceneryRegions(bg) {
  const key = `${bg.img.src}|${W}|${H}|${PIXEL}`;
  if (sceneryRegionCache?.key === key) return sceneryRegionCache.rects;
  // 폭에 비례해 무한히 사각형을 늘리지 않는다. 각 구간의 최대 높이로 모든 픽셀을 보존한다.
  const count = Math.min(112, Math.max(1, Math.ceil(W / 8))), bin = W / count;
  const heights = new Array(count).fill(0);
  for (const layer of bg.meta.layers) {
    const prof = layer.profile || bg.meta.profile, step = layer.step || bg.meta.step;
    if (!prof || !step) continue;
    eachTile(layer, (_, flip, dx, w, h) => {
      const k = h / layer.h;
      for (let i = Math.max(0, Math.floor(dx / bin)); i < Math.min(count, Math.ceil((dx+w)/bin)); i++) {
        let lo = Math.max(0, (i*bin-dx)/k), hi = Math.min(layer.w, ((i+1)*bin-dx)/k);
        if (flip) [lo,hi] = [layer.w-hi,layer.w-lo];
        for (let c = Math.max(0, Math.floor(lo/step)); c < Math.min(prof.length, Math.ceil(hi/step)); c++)
          heights[i] = Math.max(heights[i], prof[c]*k);
      }
    });
  }
  const rects = heights.flatMap((height,i) => height > 0 ? [[Math.floor(i*bin), Math.floor(H-height)-1, Math.ceil((i+1)*bin)-Math.floor(i*bin), Math.ceil(height)+2]] : []);
  sceneryRegionCache = {key,rects};
  return rects;
}
function compactRegions(rects, limit) {
  if (rects.length <= limit) return rects;
  // 드롭/연출이 매우 많아도 뒤쪽 사각형을 버리지 않는다. 가까운 것끼리 보수적으로 합친다.
  const sorted = [...rects].sort((a,b)=>a[0]-b[0]), packed=[];
  for (let i=0;i<limit;i++) {
    const group=sorted.slice(Math.floor(i*sorted.length/limit),Math.floor((i+1)*sorted.length/limit));
    const x=Math.min(...group.map(r=>r[0])),y=Math.min(...group.map(r=>r[1]));
    packed.push([x,y,Math.max(...group.map(r=>r[0]+r[2]))-x,Math.max(...group.map(r=>r[1]+r[3]))-y]);
  }
  return packed;
}
function region(all = false) {
  if (!W) return;
  const rects = [], overlayRects = [];
  // SetWindowRgn은 그리기도 자른다. 연출 범위만 추가하고 클릭 대상에는 넣지 않는다.
  for (const r of effectRects) rects.push([Math.floor(r.x)-2,Math.floor(r.y)-2,Math.ceil(r.w)+4,Math.ceil(r.h)+4]);
  for (const h of hits) if (!h.low) { const b = h.full || h.rect; rects.push([Math.floor(b.x) - 6, Math.floor(b.y) - 9, Math.ceil(b.w) + 12, Math.ceil(b.h) + 12]); }
  if (all) rects.push([0, H - STRIP, W, STRIP]);
  else {
    // 창 모양은 그리기도 자른다(2026-11-06 실측) — 풀밭 띠는 늘 넣고, 동물은 둘레의 표시까지 넉넉히
    const {left, len} = rangeX();
    rects.push([left, H - GROUND - 4, len, GROUND + 4]);
    // 배경 윤곽 — build.py 가 셈한 «칸마다 바닥에서 몇 화소까지 칠했나»를 잇는 사각형들(창 모양은 그리기도 자르므로)
    const bg = backdrop();
    if (bg) rects.push(...sceneryRegions(bg));
    const hud = $('hud').getBoundingClientRect();
    overlayRects.push([Math.floor(hud.left), Math.floor(hud.top), Math.ceil(hud.width), Math.ceil(hud.height)]);
    const toastEl = $('toast');
    if (!toastEl.hidden) { const r = toastEl.getBoundingClientRect(); overlayRects.push([Math.floor(r.left), Math.floor(r.top), Math.ceil(r.width), Math.ceil(r.height)]); }
  }
  if (panel) { const r = $('panel').getBoundingClientRect(); overlayRects.push([Math.floor(r.left), Math.floor(r.top), Math.ceil(r.width), Math.ceil(r.height)]); }
  const clipped = [...overlayRects,...compactRegions(rects.filter(r=>r[2]>0&&r[3]>0),256-overlayRects.length)];
  const key = JSON.stringify(clipped);
  if (key === lastRegion) return;
  lastRegion = key;
  api('ranch_region', {rects: clipped, ratio, length: W}).catch(() => {});
}

let toastTimer = 0;
function toast(text) {
  const el = $('toast');
  el.textContent = text; el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

function resize() {
  ratio = window.devicePixelRatio || 1;
  PIXEL = zoom / ratio; STRIP = STRIP_ART * PIXEL; GROUND = Math.round(GROUND_ART * PIXEL);
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * ratio); canvas.height = Math.round(H * ratio);
  lastRegion = '';
  if (state) paintHud();
  if (panel) placePanel();
}
window.addEventListener('resize', resize);

async function poll() {
  try {
    const s = await api('ranch_state');
    const was = lesson.in_class;
    lesson = s.lesson || lesson; mode = s.mode || mode;
    if (s.view) view = s.view;
    if (s.zoom && s.zoom !== zoom) setZoom(s.zoom);
    if (was && !lesson.in_class) toast('쉬는 시간이에요. 동물들을 돌봐 줄 수 있어요.');
    if (!was && lesson.in_class && panel && panel.kind !== 'dex') closePanel();
  } catch {}
  paintHud();
}

let giftsAt = 0;
async function gifts() {
  if (!online || Date.now() - giftsAt < 30 * MIN) return;
  giftsAt = Date.now();
  try {
    const got = await api('ranch_call', {work: 'gifts', body: {}});
    for (const [kind, n] of Object.entries(got?.granted || {})) {
      if (!n || !(kind in state.inventory)) continue;
      state.inventory[kind] += n; dirty = true;
      toast(`${D.GIFTS[kind].from} 선물 — ${D.GIFTS[kind].name} ${n}개가 왔어요.`);
    }
  } catch {}
}

let last = performance.now();
function loop() {
  window.__ranchFrames = (window.__ranchFrames || 0) + 1;
  const now = performance.now();
  const dt = Math.min(1, (now - last) / 1000);
  last = now;
  if (!document.hidden && state) {
    try {
      advance(Date.now());
      think(dt);
      maybeVisit(Date.now());
      draw();
      region(!!drag);
    } catch (error) {                      // 한 박자의 오류로 목장이 멈춰 보이지 않게 — 기록만 하고 다음 박자에 다시
      window.__ranchError = String(error?.stack || error);
    }
  }
}

async function start() {
  setZoom(2);
  resize();
  await loadArt();
  await load();
  const originalBg = atlas.bgAliases?.[state.bg];
  if (originalBg) {
    state.bg = originalBg; state.bgOwned ||= {}; state.bgOwned[originalBg] = true; dirty = true;
  }
  paintHud();
  await poll();
  if (!state.welcomed && !state.animals.length) openWelcome();
  setInterval(loop, 1000 / FPS);
  setInterval(poll, 30e3);
  setInterval(() => { if (dirty && Date.now() - lastSave > SAVE_EVERY / 6) save(); }, 20e3);
  setInterval(() => save(true), SAVE_EVERY);
  setInterval(gifts, 5 * MIN);
  gifts();
  window.addEventListener('beforeunload', () => saveLocal());
}
window.addEventListener('pywebviewready', start);
window.deskRanch = {get state() { return state; }, set state(s) { state = s; }, openShop, openDex, openWelcome, advance, tickBy, hits: () => hits,
  effects: () => ({active: effects.map((e) => ({...e})), rects: effectRects.map((r) => ({...r})), hands: handRects.map(r => ({...r})), facilities: facilityFrames.map(f=>({...f,rect:{...f.rect}}))}), toast, drawAnimal, upgrade};
