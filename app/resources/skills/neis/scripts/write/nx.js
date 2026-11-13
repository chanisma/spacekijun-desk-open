// 쓰기 스크립트 실행기: node scripts/write/nx.js scripts/write/<스크립트>.js  (env 로 인자). 세션은 neis.js session start 로 먼저 연다.
const L = require("path").join(__dirname, "../lib") + "/";
const S = require(L + 'session.js'), nav = require(L + 'nav.js'), cleo = require(L + 'cleo.js');
(async () => {
  const { page } = await S.attach();
  page.on('dialog', d => { console.log('[dialog]', d.message()); d.dismiss().catch(() => {}); });
  const fn = require(require('path').resolve(process.argv[2]));
  const r = await fn(page, nav, cleo);
  console.log(typeof r === 'string' ? r : JSON.stringify(r, null, 1));
  process.exit(0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
