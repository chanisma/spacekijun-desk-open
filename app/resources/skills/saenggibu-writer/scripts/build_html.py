#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
students.json  ->  검수용 HTML (카드형 ↔ 표형 토글 + 검색)

각 학생의 자료(활동별), 평가문, 바이트수/목표/판정을 한눈에 보고 검수한다.
데이터는 HTML 안에 JSON으로 임베드되어 단일 파일로 어디서나 열린다.

사용법: python build_html.py students.json 결과.html
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from byte_count import count_bytes, parse_target  # noqa: E402


def enrich(students):
    out = []
    for s in students:
        text = s.get("평가문", "") or ""
        n = s.get("바이트수") or count_bytes(text)
        lo, hi = parse_target(s.get("목표바이트", ""))
        if hi is not None and n > hi:
            status = "over"
        elif lo is not None and n and n < lo:
            status = "under"
        elif text:
            status = "ok"
        else:
            status = "empty"
        out.append({
            "번호": s.get("번호", ""),
            "이름": s.get("이름", ""),
            "성적": s.get("성적", ""),
            "제약사항": s.get("제약사항", ""),
            "활동": s.get("활동", {}) or {},
            "목표바이트": s.get("목표바이트", ""),
            "평가문": text,
            "바이트수": n if text else "",
            "status": status,
        })
    return out


TEMPLATE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · 생활기록부 검수</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--line:#e6e8eb;--ink:#1f2328;--sub:#6b7280;--accent:#2f5496;}
  *{box-sizing:border-box}
  body{margin:0;font-family:"Pretendard","맑은 고딕","Malgun Gothic",system-ui,sans-serif;background:var(--bg);color:var(--ink)}
  header{position:sticky;top:0;background:var(--accent);color:#fff;padding:14px 20px;z-index:10;box-shadow:0 1px 6px rgba(0,0,0,.15)}
  header h1{margin:0;font-size:18px;font-weight:700}
  header .meta{font-size:13px;opacity:.9;margin-top:2px}
  .toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px 20px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:54px;z-index:9}
  .toolbar input{flex:1;min-width:180px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:14px}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  .seg button{border:0;background:#fff;padding:8px 16px;font-size:14px;cursor:pointer}
  .seg button.active{background:var(--accent);color:#fff}
  .wrap{padding:18px 20px;max-width:1180px;margin:0 auto}
  /* 카드 */
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
  .card h3{margin:0 0 4px;font-size:16px}
  .card .grade{font-size:13px;color:var(--sub)}
  .pill{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:999px;margin-left:6px}
  .ok{background:#d9ead3;color:#274e13}.over{background:#f4cccc;color:#a61b1b}
  .under{background:#fff2cc;color:#7f6000}.empty{background:#eee;color:#888}
  .eval{margin:10px 0;padding:12px;background:#fbfcfd;border:1px solid var(--line);border-radius:8px;line-height:1.7;font-size:14.5px;white-space:pre-wrap}
  details{margin-top:8px;font-size:13px}details summary{cursor:pointer;color:var(--accent);font-weight:600}
  .act{margin:6px 0;padding:8px 10px;background:#f6f7f9;border-radius:6px}
  .act b{display:block;color:var(--accent);margin-bottom:2px;font-size:12.5px}
  .constraint{font-size:12.5px;color:#a61b1b;margin-top:6px}
  /* 표 */
  table{width:100%;border-collapse:collapse;background:#fff;font-size:13.5px}
  th,td{border:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}
  th{background:var(--accent);color:#fff;position:sticky;top:104px;cursor:pointer;white-space:nowrap}
  td.c{text-align:center;white-space:nowrap}
  tr:nth-child(even) td{background:#fafbfc}
  .hidden{display:none}
  .count{font-size:13px;color:var(--sub);margin:4px 0 12px}
</style></head>
<body>
<header><h1>__TITLE__ · 생활기록부 평가문</h1><div class="meta">학생 __N__명 · 카드/표 전환과 검색으로 검수하세요</div></header>
<div class="toolbar">
  <input id="q" placeholder="이름·번호·내용 검색…" oninput="render()">
  <div class="seg"><button id="bCard" class="active" onclick="setView('card')">카드형</button><button id="bTable" onclick="setView('table')">표형</button></div>
</div>
<div class="wrap">
  <div class="count" id="count"></div>
  <div id="cardView" class="grid"></div>
  <div id="tableView" class="hidden"></div>
</div>
<script>
const DATA = __DATA__;
let view = "card";
const esc = s => String(s==null?"":s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const STAT = {ok:"적정",over:"초과",under:"미달",empty:"미작성"};
function setView(v){view=v;document.getElementById('bCard').classList.toggle('active',v==='card');document.getElementById('bTable').classList.toggle('active',v==='table');render();}
function match(s,q){if(!q)return true;q=q.toLowerCase();const hay=[s.번호,s.이름,s.평가문,JSON.stringify(s.활동)].join(" ").toLowerCase();return hay.includes(q);}
function badge(s){const b=s.바이트수===""?"":s.바이트수+"B";const t=s.목표바이트?(" / "+s.목표바이트):"";return `<span class="pill ${s.status}">${STAT[s.status]||""} ${b}${t}</span>`;}
function cardHTML(s){
  let acts=Object.entries(s.활동||{}).map(([k,v])=>`<div class="act"><b>${esc(k)}</b>${esc(v)}</div>`).join("");
  let con=s.제약사항?`<div class="constraint">⚠ ${esc(s.제약사항)}</div>`:"";
  return `<div class="card"><h3>${esc(s.이름)} <span class="grade">${esc(s.번호)}${s.성적!==""?" · "+esc(s.성적)+"점":""}</span>${badge(s)}</h3>
    <div class="eval">${esc(s.평가문)||"<i style='color:#aaa'>미작성</i>"}</div>
    ${con}
    <details><summary>활동 자료 보기</summary>${acts||"<div class='act'>자료 없음</div>"}</details></div>`;
}
function tableHTML(list){
  let rows=list.map(s=>`<tr><td class="c">${esc(s.번호)}</td><td class="c">${esc(s.이름)}</td><td class="c">${esc(s.성적)}</td>
    <td>${esc(s.평가문)}</td><td class="c">${s.바이트수}</td><td class="c">${esc(s.목표바이트)}</td>
    <td class="c"><span class="pill ${s.status}">${STAT[s.status]||""}</span></td></tr>`).join("");
  return `<table><thead><tr><th onclick="sortBy('번호')">번호</th><th onclick="sortBy('이름')">이름</th>
    <th onclick="sortBy('성적')">성적</th><th>평가문</th><th onclick="sortBy('바이트수')">바이트</th><th>목표</th><th>판정</th></tr></thead><tbody>${rows}</tbody></table>`;
}
let sortKey=null,sortAsc=true;
function sortBy(k){if(sortKey===k)sortAsc=!sortAsc;else{sortKey=k;sortAsc=true;}render();}
function render(){
  const q=document.getElementById('q').value;
  let list=DATA.filter(s=>match(s,q));
  if(sortKey){list=[...list].sort((a,b)=>{let x=a[sortKey],y=b[sortKey];if(!isNaN(parseFloat(x))&&!isNaN(parseFloat(y))){x=+x;y=+y;}return (x>y?1:x<y?-1:0)*(sortAsc?1:-1);});}
  document.getElementById('count').textContent=`표시: ${list.length}명`;
  const cv=document.getElementById('cardView'),tv=document.getElementById('tableView');
  if(view==='card'){cv.classList.remove('hidden');tv.classList.add('hidden');cv.innerHTML=list.map(cardHTML).join("");}
  else{tv.classList.remove('hidden');cv.classList.add('hidden');tv.innerHTML=tableHTML(list);}
}
render();
</script>
</body></html>"""


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: python build_html.py students.json 결과.html")
    src, out = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    students = data.get("students", data if isinstance(data, list) else [])
    subject = data.get("subject", "생활기록부")
    rows = enrich(students)
    html = (TEMPLATE
            .replace("__TITLE__", subject)
            .replace("__N__", str(len(rows)))
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"저장 완료: {out}  (학생 {len(rows)}명)")


if __name__ == "__main__":
    main()
