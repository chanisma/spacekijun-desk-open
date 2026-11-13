/**
 * Cleopatra(나이스 화면 프레임워크) 데이터 읽기 — 그리드는 가상 스크롤이라 DOM 보다 DataSet 이 정확하다.
 *   앱 인스턴스: cpr.core.Platform.INSTANCE.getAllRunningAppInstances()  (id 예: edu/sw/his/srg/aa/his_srgaa04_m01…)
 *   DataSet/DataMap: app.lookup('이름') → getRowCount() · getRowDataRanged() · getValue(i, 열)
 *   한 앱의 모든 데이터: app.getAllDataControls()
 * ⚠ 이전 조회 결과가 DataSet 에 남아 있을 수 있다 — 조회 전에 clearData(), 읽은 뒤 검색조건(dm…)과 대조.
 * ⚠ 결과에는 학생·교직원 개인정보가 들어 있다. 필요한 열만 읽고, 파일은 쓰고 나면 지운다.
 */

/** 실행 중인 앱 목록 [{id, datasets}] */
const listApps = page => page.evaluate(() => {
  const P = window.cpr && cpr.core && cpr.core.Platform && cpr.core.Platform.INSTANCE;
  if (!P) return [];
  return P.getAllRunningAppInstances().map(a => {
    let ds = [];
    try { ds = (a.getAllDataControls ? a.getAllDataControls() : []).map(d => d.id); } catch (e) { }
    return { id: a.id, datasets: ds };
  });
});

/**
 * 앱 하나의 데이터 컨트롤 요약(이름·종류·행 수·열). app: id 일부(없으면 DataSet 이 가장 많은 마지막 앱)
 * rows: 행 몇 개까지 값도 볼지(기본 0 — 구조만). cols: 이 열만.
 */
const dumpData = (page, { app = '', rows = 0, only = '', cols = '' } = {}) => page.evaluate(({ app, rows, only, cols }) => {
  const P = cpr.core.Platform.INSTANCE;
  const apps = P.getAllRunningAppInstances().filter(a => !app || a.id.includes(app));
  if (!apps.length) return { 오류: `앱 없음: ${app}` };
  // 지정이 없으면 지금 열린 업무 화면(포털 껍데기 app/com/main 과 탭 껍데기 …m00 제외, 가장 최근 것)
  const work = apps.filter(a => /^edu\//.test(a.id));           // 업무 화면 앱(edu/…). app/com·udc/ 는 포털·공통 부품
  const pickNonShell = list => list.filter(a => !/_m00(\$\d+)?$/.test(a.id)).pop() || list.pop();
  const A = app ? apps[apps.length - 1] : (pickNonShell(work.slice()) || apps[apps.length - 1]);
  const want = cols ? cols.split(',') : null;
  const out = { app: A.id, data: [] };
  for (const d of (A.getAllDataControls ? A.getAllDataControls() : [])) {
    if (only && !only.split(',').includes(d.id)) continue;
    const item = { id: d.id, type: d.type || (d.getRowCount ? 'dataset' : 'datamap') };
    try {
      if (d.getRowCount) {
        item.rows = d.getRowCount();
        const data = d.getRowDataRanged ? d.getRowDataRanged() : [];
        item.columns = data.length ? Object.keys(data[0]) : (d.getColumnNames ? d.getColumnNames() : []);
        if (rows) item.sample = data.slice(0, rows).map(r => want ? Object.fromEntries(want.map(c => [c, r[c]])) : r);
      } else if (d.getDatas) { item.values = d.getDatas(); }
      else if (d.getValue && d.getColumnNames) { item.values = Object.fromEntries(d.getColumnNames().map(c => [c, d.getValue(c)])); }
    } catch (e) { item.err = e.message; }
    out.data.push(item);
  }
  return out;
}, { app, rows, only, cols });

/** DataSet 전체 행 */
const readDataset = (page, app, name, cols) => page.evaluate(({ app, name, cols }) => {
  const A = cpr.core.Platform.INSTANCE.getAllRunningAppInstances().filter(a => a.id.includes(app)).pop();
  if (!A) throw new Error('앱 없음: ' + app);
  const d = A.lookup(name); if (!d) throw new Error('데이터 없음: ' + name);
  const rows = d.getRowDataRanged();
  return cols ? rows.map(r => Object.fromEntries(cols.map(c => [c, r[c]]))) : rows;
}, { app, name, cols: cols || null });

module.exports = { listApps, dumpData, readDataset };
