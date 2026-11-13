/**
 * 나이스 지식(오프라인) — 화면 카탈로그·용어·사용법 안내·화면 사이 규칙·업무 달력.
 *   catalog.json  1,384 화면: key(단위업무›세부업무›메뉴그룹›화면), roles(교과/학급/동아리담임 — 비면 업무분장으로 받는 화면), inner(화면 안 탭), purpose
 *   glossary.json 교사들이 부르는 말(aliases) → 화면
 *   guides/       215 화면 사용법(purpose·context·who·before·after·flows·cautions·faq)
 *   RULES.md      «A 를 안 하면 B 가 비어 보인다» 같은 화면 사이 규칙
 *   WORKFLOW.md   시기별 업무 달력(누가·언제·무엇 먼저)
 * 출처: 2026 상반기 나이스 교무업무 사용자 설명서(고등학교) 를 바탕으로 정리, 2026-10 기준. 개편되면 화면 이름이 달라질 수 있다.
 */
const fs = require('fs');
const path = require('path');
const { paths } = require('./config.js');
const K = paths.knowledge;
let _cat, _glo, _guides;

const catalog = () => _cat || (_cat = JSON.parse(fs.readFileSync(path.join(K, 'catalog.json'), 'utf8')));
const glossary = () => _glo || (_glo = JSON.parse(fs.readFileSync(path.join(K, 'glossary.json'), 'utf8')));
function guides() {
  if (_guides) return _guides;
  _guides = new Map();
  const walk = d => { for (const f of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, f.name);
    if (f.isDirectory()) walk(p); else if (f.name.endsWith('.json')) { try { const g = JSON.parse(fs.readFileSync(p, 'utf8')); _guides.set(g.key, g); } catch (e) { } }
  } };
  walk(path.join(K, 'guides'));
  return _guides;
}
const norm = s => String(s || '').replace(/\s+/g, '').toLowerCase();

/** 하고 싶은 말로 화면 찾기 — 화면 이름·용도·용어(aliases)·안내 목적에서 점수 */
function findScreens(query, { limit = 10, role = '' } = {}) {
  const words = String(query).split(/\s+/).filter(Boolean).map(norm);
  const glo = glossary();
  const gloEntries = Array.isArray(glo) ? glo : Object.entries(glo.screens || glo).map(([name, v]) => ({ name, ...v }));
  const aliasOf = new Map(gloEntries.map(e => [e.name || e.screen, (e.aliases || []).join(' ')]));
  const g = guides();
  const scored = [];
  for (const s of catalog().screens) {
    if (role && !(s.roles || []).some(r => r.includes(role))) continue;
    const guide = g.get(s.key);
    const hay = { name: norm(s.name), path: norm(s.key), purpose: norm((s.purpose || '') + (guide ? guide.purpose : '')), alias: norm(aliasOf.get(s.name) || '') };
    let score = 0, matched = 0;
    for (const w of words) {
      let hit = 0;
      if (hay.name === w) hit += 10; else if (hay.name.includes(w)) hit += 6;
      if (hay.alias.includes(w)) hit += 5;
      if (hay.path.includes(w)) hit += 2;
      if (hay.purpose.includes(w)) hit += 2;
      if (hit) { matched++; score += hit; }
    }
    if (score && words.length > 1 && matched === words.length) score += 10;   // 낱말을 다 담은 화면을 위로
    if (score) scored.push({ score, 화면: s.name, 경로: s.key.replace(/›/g, ' › '), 역할: (s.roles || []).join('·') || '업무분장', 용도: (guide && guide.purpose) || s.purpose || '', 안내: !!guide });
  }
  return scored.sort((a, b) => b.score - a.score).slice(0, limit);
}

/** 화면 사용법 안내 (이름 또는 key 일부) */
function getGuide(name) {
  const g = guides();
  const hits = [...g.values()].filter(x => x.key.endsWith('›' + name) || x.key === name);
  const list = hits.length ? hits : [...g.values()].filter(x => x.key.includes(name));
  return list;
}

/** 규칙·업무달력에서 낱말이 든 문단 */
function grepDoc(file, query, { context = 0 } = {}) {
  const text = fs.readFileSync(path.join(K, file), 'utf8');
  const blocks = text.split(/\n(?=\d+\.\s|\#|\- |\|)/);
  const ws = String(query || '').split(/\s+/).filter(Boolean);
  return blocks.filter(b => ws.every(w => b.includes(w))).map(b => b.trim()).slice(0, 40);
}

module.exports = { catalog, glossary, guides, findScreens, getGuide, grepDoc };
