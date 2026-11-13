// 열린 Nexacro 화면(xfdl form)을 이름으로 찾는 식 — page.evaluate 에 넘겨 eval(FF(name)) 으로 쓴다
exports.FF = name => `(() => {
  const app = nexacro.getApplication(); let hit = null; const seen = new Set();
  function v(f, d) {
    if (!f || d > 9 || hit || seen.has(f)) return; seen.add(f);
    if (f.name === '${name}') { hit = f; return; }
    for (const k of Object.keys(f)) { let o; try { o = f[k]; } catch (e) { continue; }
      if (!o || typeof o !== 'object') continue;
      if (o.form && o.form !== f) v(o.form, d + 1);
      else if (/Frame/.test(o._type_name || '') ) v(o, d + 1); }
  }
  v(app.gv_workFrame, 0);
  for (const k of Object.keys(app)) if (!hit && /Frame/.test(k)) { try { v(app[k].form || app[k], 0); } catch (e) { } }
  return hit; })()`;

// 데이터셋 → 객체 배열 (nexacro 64비트 정수 {hi,lo} 는 hi 로)
exports.DS = `function __ds(ds, lim) { const cols = []; for (let c = 0; c < ds.getColCount(); c++) cols.push(ds.getColID(c));
  const out = []; const n = Math.min(ds.getRowCount(), lim || 1e9);
  for (let i = 0; i < n; i++) { const o = {}; cols.forEach(c => { let v = ds.getColumn(i, c); if (v && typeof v === 'object' && 'hi' in v) v = v.hi; if (v !== undefined && v !== null && v !== '') o[c] = v; }); out.push(o); }
  return out; }`;
