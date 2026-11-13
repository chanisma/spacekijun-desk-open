import React, { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { Scene, useSceneTime, Pointer, AppWindow as NativeWindow, clickFlash, typed } from './runtime';
import './style.css';

// UI landmarks checked against the desktop source and the live SPACEKIJUN profile.
// Example names/messages below are fictional. Scenes never call a real login API.
function AppWindow(props:Parameters<typeof NativeWindow>[0]) { return <NativeWindow {...props} style={{...props.style,height:Number(props.bodyStyle?.height??300)+40}}/>; }
const ring = (t:number, at:number):CSSProperties => ({boxShadow:`0 0 0 ${clickFlash(t,at)*9}px var(--focus)`});
const place = (left:number,top:number,width:number,height?:number):CSSProperties => ({position:'absolute',left,top,width,height});
function Mark({children}: {children:ReactNode}) {return <span className="mark">{children}</span>;}
function Done({show,children}: {show:boolean;children:ReactNode}) {return <div className={`done ${show?'shown':''}`}>{children}</div>;}

const homeLinks = [
  {name:'업무포털',mark:<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M5 21V5l7-3 7 3v16M3 21h18M9 7h1M14 7h1M9 11h1M14 11h1M10 21v-6h4v6"/></svg>,note:'전자결재 · 학교 행정'},
  {name:'나이스',mark:'N',note:'교육행정 업무시스템'},
  {name:'K-에듀파인',mark:'K',note:'인증서 자동 로그인'},
  {name:'전북 AIEP',mark:'AI',note:'교육 플랫폼'},
  {name:'리로스쿨',mark:'R',note:'교육 플랫폼'},
  {name:'기전시트온',mark:'S',note:'자습 관리'},
  {name:'스페이스기전',mark:<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 8h6M9 12h6M9 16h3"/></svg>,note:'내 업무 공간 열기'},
];
function Home() {
  const t=useSceneTime(), OPEN=7.3, READY=8.3;
  return <>
    <AppWindow title="① 스페이스기전 데스크 · 업무 홈" style={place(35,25,890)} bodyStyle={{height:480}}>
      <div className="walk-home-nav"><b>SPACEKIJUN</b><span className="selected">업무 홈</span><span>쪽지함</span><span>교직원 명부</span><span>연결 및 설정</span></div>
      <div className="walk-home-content" style={place(170,18,695)}>
        <div className="walk-myday"><small>2026년 9월 10일 목요일</small><h2>좋은 아침입니다, 홍길동 선생님.</h2>
          <div className="walk-home-tiles">{homeLinks.map((item,i)=><div key={item.name} className={item.name==='스페이스기전'?'space':''} style={item.name==='스페이스기전'?ring(t,OPEN):{}} data-click={item.name==='스페이스기전'?'open-space':undefined}><span>{item.mark}</span><b>{item.name}</b><small>{item.note}</small></div>)}</div>
        </div>
        <div className="walk-home-section"><b>나의 학교 대시보드</b><small>1분마다 갱신</small></div>
        <div className="walk-home-cards">
          <div><b>오늘의 흐름</b><p>09:00　공통수학1 1-3</p><p>11:00　교과 협의회</p></div>
          <div><b>이번 주 일정</b><p>9.11　평가 계획 제출</p><small>일정과 업무 마감 확인</small></div>
          <div className="wide"><b>나의 업무</b><p>학교 행사 준비 <small>오늘 마감</small></p></div>
          <div><b>학교 공지</b></div><div><b>최근 알림</b></div>
        </div>
      </div>
    </AppWindow>
    {t>=READY&&<AppWindow title="② 프로그램 안의 스페이스기전" kind="browser" url="spacekijun.lovable.app" style={place(325,295,590)} bodyStyle={{height:190}}><div className="pad"><Mark>SPACEKIJUN</Mark><h2>내 업무 공간</h2><p>일정 · 학교 소식 · 알림</p><span className="success">✓ 프로그램 안에서 열렸어요</span></div></AppWindow>}
    <Pointer path={[{t:1,x:35,y:30},{t:3,x:54,y:66},{t:5,x:75,y:66},{t:OPEN,x:87.2,y:34.7,click:true}]} />
    <Done show={t>=9.5}>✓ 홈에서 일정을 확인하고, 스페이스기전으로 이어갑니다.</Done>
  </>;
}
function Connect() {
  const t=useSceneTime(), CM=1.5, LOGIN=3.5, ACCOUNT=6.5, RETURN=8;
  return <>
    <AppWindow title="① 데스크 · 연결 및 설정" style={place(35,45,530)} bodyStyle={{height:330}}><div className="pad"><Mark>SPACEKIJUN 계정</Mark><h2>알림과 답장을 연결하세요</h2><p>{t>=RETURN?'예시 계정 · 로그인됨':'알림과 답장을 사용하려면 계정을 연결해 주세요.'}</p><span className="mock-button subtle" style={{...ring(t,CM),marginRight:12}}>쿨메신저 연결</span><span className="mock-button" style={ring(t,LOGIN)}>{t>=RETURN?'로그아웃':'구글 로그인'}</span><div className="status-line">{t>=RETURN?'● 자동 감시 중':'○ 계정 연결 대기'}</div></div></AppWindow>
    {t>=4.5&&t<RETURN&&<AppWindow kind="browser" title="Google 계정" url="accounts.google.com" badge="②" style={place(430,175,480)} bodyStyle={{height:240}}><div className="pad"><h2>계정 선택</h2><p>SPACEKIJUN에서 사용하는 계정</p><div className="mock-field" style={ring(t,ACCOUNT)}>예시 교직원 계정</div></div></AppWindow>}
    <Pointer path={[{t:.5,x:20,y:55},{t:CM,x:15.5,y:44,click:true},{t:LOGIN,x:33,y:44,click:true},{t:ACCOUNT,x:69.8,y:61.1,click:true},{t:RETURN,x:21,y:60}]} />
    <div className="connection-result" style={{...place(605,200,270),opacity:t>=RETURN?1:0}}><Mark>연결 완료</Mark><h2>쿨메신저<br/>↓<br/>SPACEKIJUN</h2><p>새 쪽지를 알림으로 전달합니다.</p></div><Done show={t>=8}>✓ 계정 연결 후에는 별도 감시 시작 버튼이 필요 없습니다.</Done>
  </>;
}
function Certificate() {
  const t=useSceneTime(), NAME=3, SAVE=7, SELECT=9;
  return <>
    <AppWindow title="연결 및 설정 · 인증서 자동 로그인" style={place(45,35,870)} bodyStyle={{height:425}}><div className="pad"><h2>인증서 자동 로그인</h2><p>아이디와 인증서 암호는 이 PC에 암호화하여 보관합니다.</p><div className="fields"><label>업무포털 아이디<span className="mock-field">teacher01</span></label><label>인증서 사용자 이름<span className="mock-field" style={ring(t,NAME)}>{typed(t,'홍길동',NAME,12)||'이름 입력'}</span></label><label>인증서 암호<span className="mock-field">••••••••</span></label></div><span className="mock-button" style={ring(t,SAVE)}>저장하기</span>{t>=SELECT&&<div className="selection"><small>인증서 선택 예시</small><div>김교사 · 교육기관 인증서</div><div className="selected">✓ 홍길동 · 교육기관 인증서</div></div>}</div></AppWindow>
    <Pointer path={[{t:1,x:28,y:35},{t:NAME,x:50,y:42.6,click:true},{t:SAVE,x:13,y:56,click:true}]} />
    <Done show={t>=10}>✓ 이름이 포함된 인증서가 하나일 때 자동 선택합니다.</Done>
  </>;
}
function Shortcuts() {
  const t=useSceneTime(), LOGIN=3, OPEN=4.2, COMPLETE=8;
  return <>
    <AppWindow title="① 데스크 · 업무 홈의 바로가기" style={place(45,25,870)} bodyStyle={{height:470}}>
      <div className="walk-shortcuts-content">
        <div className="walk-myday"><small>2026년 9월 10일 목요일</small><h2>좋은 아침입니다, 홍길동 선생님.</h2>
          <div className="walk-home-tiles">{homeLinks.map((item,i)=><div key={item.name} className={item.name==='스페이스기전'?'space':''} style={i===2?ring(t,LOGIN):{}} data-click={i===2?'open-klef':undefined}><span>{item.mark}</span><b>{item.name}</b><small>{i===2&&t>=LOGIN?(t>=COMPLETE?'로그인 완료':'로그인 준비 중…'):item.note}</small></div>)}</div>
        </div>
        <div className="walk-shortcut-notes"><p><b>업무포털 · 나이스 · K-에듀파인</b><span>각각 별도의 Edge 창에서 인증서 자동 로그인</span></p><p><b>전북 AIEP · 리로스쿨</b><span>기본 브라우저로 연결</span></p><p><b>기전시트온 · 스페이스기전</b><span>프로그램 안에서 데스크 계정으로 연결</span></p></div>
      </div>
    </AppWindow>
    {t>=OPEN&&<AppWindow title="② Microsoft Edge · K-에듀파인" style={place(355,300,560)} bodyStyle={{height:185}}><div className="pad"><Mark>인증서 자동 로그인</Mark><h2>{t<COMPLETE?'인증서 목록을 확인합니다':'업무 화면이 열렸어요'}</h2><p>{t<COMPLETE?'목록 로딩 → 이름 선택 → 암호 입력':'에듀파인에서 필요한 업무를 계속하세요.'}</p><span className="success">{t<COMPLETE?'로그인 진행 중':'✓ 로그인 완료'}</span></div></AppWindow>}
    <Pointer path={[{t:1,x:28,y:30},{t:LOGIN,x:38.3,y:34,click:true}]} />
    <Done show={t>=9}>✓ 세 자동 로그인 창은 동시에 열어 사용할 수 있습니다.</Done>
  </>;
}
function Alerts() {
  const t=useSceneTime(), SUMMARY=2.5, BODY=4.5, ARRIVE=7;
  return <>
    <AppWindow title="① 데스크 · 쪽지 알림 · 답장 연동" style={place(40,35,600)} bodyStyle={{height:300}}><div className="pad"><h2>내게 필요한 정보만 알림으로</h2><div className="option"><span>긴 쪽지 요약하기<small>긴 본문을 Solar로 요약</small></span><span className="mock-check" style={ring(t,SUMMARY)}>{t<SUMMARY?'✓':''}</span></div><div className="option"><span>알림에 본문 포함<small>끄면 발신자 정보만 표시</small></span><span className="mock-check" style={ring(t,BODY)}>{t<BODY?'✓':''}</span></div><span className="success">● 자동 감시 중</span></div></AppWindow>
    <div className="flow-label" style={place(175,400,400)}>쿨메신저 새 쪽지　→</div>
    <AppWindow title="② SPACEKIJUN · 알림" style={place(510,290,405)} bodyStyle={{height:175}}><div className="pad"><b>{t>=ARRIVE?'[쿨메신저] 예시 교직원':'새 알림 대기'}</b><p>{t>=ARRIVE?'새 쪽지가 도착했습니다.':'새로 받은 쪽지를 확인합니다.'}</p>{t>=ARRIVE&&<span className="mock-button subtle">답장</span>}</div></AppWindow>
    <Pointer path={[{t:1,x:51,y:29},{t:SUMMARY,x:62.3,y:29,click:true},{t:BODY,x:62.3,y:42.8,click:true}]} />
    <Done show={t>=9}>✓ 서버의 쿨메신저 연동 알림은 생성 후 한 달이 지나면 정리됩니다.</Done>
  </>;
}
function Inbox() {
  const t=useSceneTime(), PICK=3, READ=4;
  return <>
    <AppWindow title="데스크 · 쪽지함" style={place(40,40,880)} bodyStyle={{height:425}}><div className="pad"><h2>쪽지함</h2><p>최근 받은 쪽지와 답장을 확인하세요.</p><div className="inbox-demo"><div><div className="message-card selected" style={ring(t,PICK)}><b>예시 교직원</b><small>오늘 회의 안내</small><p>오늘 회의는 오후…</p></div><div className="message-card"><b>예시 부서</b><p>업무 일정 안내</p></div></div><div className="message-detail"><small>{t>=READ?'받은 쪽지 · 예시 화면':'쪽지 상세'}</small><h2>{t>=READ?'오늘 회의 안내':'쪽지를 선택해 주세요'}</h2><p>{t>=READ?'오늘 회의는 오후 3시입니다. 회의실에서 진행합니다. 준비 자료를 확인해 주세요.':'위쪽 목록에서 내용을 선택하세요.'}</p></div></div></div></AppWindow>
    <Pointer path={[{t:1,x:43,y:35},{t:PICK,x:28.3,y:42.9,click:true}]} />
    <Done show={t>=7}>✓ 데스크에서는 전문 확인, 답장은 SPACEKIJUN 알림에서.</Done>
  </>;
}
function Roster() {
  const t=useSceneTime(), SYNC=2, SEARCH=4, SAVE=8;
  return <>
    <AppWindow title="데스크 · 교직원 명부" style={place(40,40,880)} bodyStyle={{height:430}}><div className="pad"><div className="mock-heading"><h2>교직원 명부</h2><span className="mock-button subtle" style={ring(t,SYNC)}>조직도 새로 읽기</span></div><div className="mock-field" style={ring(t,SEARCH)}>{typed(t,'보건실',SEARCH,12)||'이름 또는 부서 검색'}</div><div className="roster-row"><b>보건실</b><span>예시 교직원</span></div><h3>별칭 연결</h3><div className="fields"><label>대화명<span className="mock-field">보건실</span></label><label>실명<span className="mock-field">홍길동</span></label><span className="mock-button" style={ring(t,SAVE)}>별칭 저장</span></div></div></AppWindow>
    <Pointer path={[{t:1,x:74,y:30},{t:SYNC,x:85.6,y:21.1,click:true},{t:SEARCH,x:50,y:31.6,click:true},{t:SAVE,x:87.3,y:73.1,click:true}]} />
    <Done show={t>=9}>✓ 대화명과 실명을 연결해 상대를 구분합니다.</Done>
  </>;
}
function Personal() {
  const t=useSceneTime(), MENU=2, PROFILE=4, TOGGLE=7, DONE=8;
  return <>
    <AppWindow kind="browser" url="spacekijun.lovable.app" style={place(35,30,890)} bodyStyle={{height:450}}>
      <div className="site-header"><b>SPACEKIJUN</b><span>알림</span><span className="user-icon" style={ring(t,MENU)} aria-label="사용자 아이콘">○</span></div>
      {t>=MENU&&t<PROFILE&&<div className="profile-menu"><b>예시 사용자</b><div style={ring(t,PROFILE)}>프로필</div><div>설정</div><div>로그아웃</div></div>}
      {t<PROFILE?<div className="pad"><h2>내 업무 공간</h2><p>오른쪽 위 사용자 아이콘을 눌러 주세요.</p></div>:<div className="pad"><h2>프로필</h2><div className="personal-card"><h3>개인기기 및 자동 로그인</h3><p>본인만 사용하는 기기에서 로그인 상태를 유지하세요.</p><div className="option"><b>이 브라우저를 개인기기로 등록</b><span className={`switch ${t>=TOGGLE?'on':''}`} style={ring(t,TOGGLE)}><i/></span></div><p>이 계정과 현재 브라우저에만 적용됩니다.<br/>공용 PC에서는 등록하지 마세요.</p></div>{t>=DONE&&<div className="success">개인기기로 등록했습니다. 다음 방문에도 로그인이 유지됩니다.</div>}</div>}
    </AppWindow>
    <Pointer path={[{t:1,x:70,y:19},{t:MENU,x:91.7,y:17,click:true},{t:PROFILE,x:82.4,y:40.3,click:true},{t:TOGGLE,x:88.1,y:56.8,click:true}]} />
    <Done show={t>=10}>✓ 데스크 안에서 쓸 경우, 데스크의 스페이스기전 창에서 등록하세요.</Done>
  </>;
}
function Startup() {
  const t=useSceneTime(), ENABLE=3, LOGON=6;
  return <>
    <AppWindow title="연결 및 설정 · Windows 자동 실행" style={place(40,40,870)} bodyStyle={{height:380}}><div className="pad"><h2>Windows 자동 실행</h2><p>PC에 로그인하면 데스크를 준비합니다.</p><div className="option"><span>Windows 로그인 시 자동 실행<small>창을 띄우지 않고 트레이에서 시작합니다.</small></span><span className="mock-check" style={ring(t,ENABLE)}>{t>=ENABLE?'✓':''}</span></div><p>현재 Windows 계정에만 적용됩니다.<br/>‘쿨메신저 연결’로 실행하고 로그인해 두세요.</p>{t>=LOGON&&<div className="status-line">Windows 로그인 → 트레이에서 데스크 시작</div>}</div></AppWindow>
    <Pointer path={[{t:1,x:50,y:35},{t:ENABLE,x:90.5,y:37.5,click:true}]} />
    <Done show={t>=8}>✓ SPACEKIJUN 계정이 연결되어 있으면 자동 감시를 시작합니다.</Done>
  </>;
}
function Tray() {
  const t=useSceneTime(), CLOSE=2.5, TRAY=5, EXIT=8;
  return <>
    <div className="desktop-demo" style={place(35,30,890,465)}><div className="desktop-word">업무를 마쳐도, 새 쪽지는 계속</div><div className="taskbar"><span>Windows</span><span style={ring(t,TRAY)}>⌃　SPACEKIJUN</span></div></div>
    {t<CLOSE&&<AppWindow title="스페이스기전 데스크" style={place(100,85,600)} bodyStyle={{height:190}}><div className="pad"><h2>● 쪽지 감시 중</h2><p>창의 닫기 버튼은 트레이로 숨깁니다.</p></div><span className="window-close" style={ring(t,CLOSE)}>×</span></AppWindow>}
    {t>=CLOSE&&t<EXIT&&<div className="tray-note">● 창을 닫아도 감시 중</div>}
    {t>=TRAY&&t<EXIT&&<div className="tray-menu"><div>열기</div><div style={ring(t,EXIT)}>종료</div></div>}
    {t>=EXIT&&<div className="exit-note"><h2>프로그램 종료</h2><p>다음 실행 전까지 감시가 중지됩니다.</p></div>}
    <Pointer path={[{t:1,x:61,y:24},{t:CLOSE,x:70.3,y:17.5,click:true},{t:TRAY,x:86,y:79,click:true},{t:EXIT,x:83.9,y:71.3,click:true}]} />
    <Done show={t>=9}>✓ 새 실행 파일로 교체할 때도 트레이의 ‘종료’를 사용합니다.</Done>
  </>;
}
const steps = [
  {label:'업무 홈',title:'날짜와 인사 아래에서 하루를 시작하세요',body:'오늘 일정·이번 주 일정·나의 업무·학교 공지·최근 알림을 데스크 홈에서 확인합니다.',points:['날짜와 시간대별 인사 메시지가 버튼 위에 표시됩니다.','버튼 순서: 업무포털 → 나이스 → K-에듀파인 → 전북 AIEP → 리로스쿨 → 기전시트온 → 스페이스기전.','연결한 SPACEKIJUN 계정의 정보를 홈에서 1분마다 갱신합니다.','각 항목의 전체 보기로 프로그램 안의 상세 페이지를 엽니다.','스페이스기전과 기전시트온은 전용 창에서 데스크 계정으로 로그인합니다. 각 사이트의 직접 Google 로그인도 유지됩니다.','배포된 사이트 변경은 새로고침으로 반영됩니다.'],scene:Home},
  {label:'계정 연결',title:'SPACEKIJUN 계정을 먼저 연결하세요',body:'연결 및 설정에서 구글 로그인을 누르고, 평소 SPACEKIJUN에 사용하는 계정을 선택합니다.',points:['먼저 ‘쿨메신저 연결’을 누르세요. 로그인 창이 보이면 로그인합니다.','재실행 안내가 나오면 작성 중인 쪽지를 저장한 뒤 확인을 누르세요.','‘자동 감시 중’이 보이면 준비 완료입니다.','데스크 로그인 후 스페이스기전·기전시트온 바로가기를 누르면 같은 계정으로 연결됩니다. 사이트에 직접 접속하는 Google 로그인도 그대로 사용할 수 있습니다.'],scene:Connect},
  {label:'인증서 설정',title:'사용자 이름으로 인증서를 구분하세요',body:'업무포털 아이디, 인증서 사용자 이름, 인증서 암호를 입력한 뒤 저장합니다.',points:['나이스·업무포털·에듀파인에 공통 적용됩니다.','같은 이름이 여러 개면 인증서의 구분 문구까지 입력하세요.','암호 칸을 비우고 저장하면 기존 암호를 유지합니다.','목록을 못 찾거나 여러 개가 일치하면 열린 창과 활동 기록을 확인하세요.'],scene:Certificate},
  {label:'바로가기',title:'필요한 업무시스템을 바로 여세요',body:'날짜와 인사 아래의 정사각형 버튼을 누르세요. 시연에서는 세 번째 K-에듀파인을 선택합니다.',points:['나이스·전북 업무포털·K-에듀파인: 인증서 자동 로그인.','세 시스템은 별도의 Edge 창으로 동시에 사용할 수 있습니다. 에듀파인은 자동 로그인만 지원합니다.','전북 AIEP·리로스쿨: 기본 브라우저로 연결됩니다. 기전시트온·스페이스기전: 프로그램 안에서 데스크 계정으로 로그인합니다.','처음 실행 시 인증서 보안프로그램 권한을 허용해야 할 수 있습니다.'],scene:Shortcuts},
  {label:'알림·답장',title:'새 쪽지를 SPACEKIJUN 알림으로',body:'계정을 연결하고 데스크를 실행해 두면 새 쪽지를 확인합니다. 본문 포함과 긴 본문 Solar 요약은 각각 선택할 수 있습니다.',points:['요약은 Solar 연결이 준비된 PC에서 사용합니다.','SPACEKIJUN 알림의 답장은 쿨메신저로 연결됩니다.','생성 후 한 달이 지난 쿨메신저 연동 알림은 서버에서 정리됩니다.','쿨메신저의 원본 쪽지를 삭제하는 기능은 아닙니다.'],scene:Alerts},
  {label:'쪽지함',title:'목록에서 골라 전문을 확인하세요',body:'데스크의 쪽지함에서 최근 받은 쪽지와 답장을 확인합니다. 목록을 누르면 아래쪽에 전문이 표시됩니다.',points:['최근 60개 항목을 확인합니다.','새로고침으로 목록을 다시 불러올 수 있습니다.','답장을 보낼 때는 SPACEKIJUN 알림의 답장 기능을 사용하세요.'],scene:Inbox},
  {label:'교직원 명부',title:'대화명과 실명을 연결하세요',body:'조직도를 동기화한 뒤 교직원 명부를 검색합니다. ‘보건실’ 같은 대화명은 실명과 별칭으로 연결할 수 있습니다.',points:['명부가 비어 있으면 쿨메신저 연결을 먼저 확인하세요.','검색으로 이름이나 부서를 빠르게 찾습니다.','별칭은 상대를 구분하기 위한 설정입니다.'],scene:Roster},
  {label:'개인기기',title:'프로필에서 웹 자동 로그인을 설정하세요',body:'SPACEKIJUN 오른쪽 위 사용자 아이콘 → 프로필 → 개인기기 및 자동 로그인에서 스위치를 켭니다.',points:['정확한 스위치 이름: ‘이 브라우저를 개인기기로 등록’.','등록하면 매일 새벽 5시에도 로그아웃되지 않고, 다음 방문 시 로그인이 유지됩니다.','이 계정과 현재 브라우저에만 적용됩니다. 공용 PC에서는 등록하지 마세요.','직접 로그아웃하면 등록도 해제됩니다. 브라우저 데이터 삭제·인증 만료 시 다시 로그인하세요.','Google Drive·Calendar 연결은 별도 재인증이 필요할 수 있습니다.'],scene:Personal},
  {label:'자동 실행',title:'Windows 로그인과 함께 데스크를 시작하세요',body:'연결 및 설정에서 ‘Windows 로그인 시 자동 실행’을 켜세요. 다음 Windows 로그인부터 트레이에서 조용히 시작합니다.',points:['기본값은 꺼짐이며 현재 Windows 계정에만 적용됩니다.','SPACEKIJUN 계정이 연결되어 있으면 감시를 자동으로 시작합니다.','‘쿨메신저 연결’로 실행하고 로그인해 두세요.','해제하려면 같은 옵션을 끄세요.','파일을 옮기거나 새 버전으로 교체하면 그 실행 파일을 한 번 실행하세요.'],scene:Startup},
  {label:'종료·점검',title:'창 닫기와 프로그램 종료를 구분하세요',body:'창을 닫으면 트레이에서 계속 실행됩니다. 완전히 끝내려면 트레이 아이콘 메뉴에서 종료를 선택합니다.',points:['새 버전을 실행하기 전에도 기존 데스크를 트레이에서 종료하세요.','연동이 안 되면 계정 연결 → 쿨메신저 상세 확인 → 활동 기록 순으로 점검합니다.','트레이 아이콘이 보이지 않으면 작업 표시줄의 숨겨진 아이콘을 펼치세요.'],scene:Tray},
];
function Guide() {
  const params=new URLSearchParams(location.search);
  const [index,setIndex]=useState(Math.min(steps.length-1,Math.max(0,Number(params.get('step')||0))));
  const [replay,setReplay]=useState(0), [paused,setPaused]=useState(false), [scale,setScale]=useState(1);
  const host=useRef<HTMLDivElement>(null);
  const fixed=params.has('t')?Number(params.get('t')):null;
  const step=steps[index], Content=step.scene;
  const close=()=>window.parent!==window?window.parent.postMessage({type:'desk-guide-close'},location.protocol==='file:'?'*':location.origin):window.close();
  useEffect(()=>{const el=host.current!;const resize=()=>setScale(el.clientWidth/960);resize();const ro=new ResizeObserver(resize);ro.observe(el);return()=>ro.disconnect();},[]);
  useEffect(()=>{const key=(event:KeyboardEvent)=>{if(event.key==='Escape')close();if(event.key==='ArrowRight')setIndex(i=>Math.min(i+1,steps.length-1));if(event.key==='ArrowLeft')setIndex(i=>Math.max(0,i-1));};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[]);
  return <div className="guide"><header><div><small>SPACEKIJUN DESK · 사용 방법</small><h1>화면으로 익히는 업무 데스크</h1></div><button onClick={close} aria-label="안내 닫기" className="close">×</button></header><nav aria-label="안내 목차">{steps.map((item,i)=><button key={item.label} aria-current={index===i?'step':undefined} onClick={()=>{setIndex(i);setPaused(false);}}><span>{String(i+1).padStart(2,'0')}</span>{item.label}</button>)}</nav><main><section><div className="stage-heading"><span>화면 시연 · 예시 데이터</span><span>{String(index+1).padStart(2,'0')} / {String(steps.length).padStart(2,'0')}</span></div><div className="stage-host" ref={host} style={{height:600*scale}}><div className="stage" style={{transform:`scale(${scale})`}}><Scene key={`${index}-${replay}`} playKey={`${index}-${replay}`} paused={fixed!==null||paused||matchMedia('(prefers-reduced-motion: reduce)').matches} freezeAt={fixed??12}><Content/></Scene></div></div><div className="stage-foot">시연 화면은 설명용입니다. 실제 계정이나 설정은 변경되지 않습니다.</div></section><aside><small>STEP {String(index+1).padStart(2,'0')}</small><h2>{step.title}</h2><p>{step.body}</p><ul>{step.points.map(point=><li key={point}>{point}</li>)}</ul>{index===7&&<a href="https://spacekijun.lovable.app/profile" target="_blank" rel="noopener noreferrer">SPACEKIJUN 프로필 페이지 ↗</a>}</aside></main><footer><button onClick={()=>{setReplay(n=>n+1);setPaused(false);}}>↻ 다시 재생</button><button onClick={()=>setPaused(!paused)}>{paused?'시연 재생':'완료 화면 보기'}</button><span className="footer-spacer"/><button disabled={index===0} onClick={()=>setIndex(index-1)}>← 이전</button><button className="primary" onClick={()=>index===steps.length-1?close():setIndex(index+1)}>{index===steps.length-1?'안내 닫기':'다음 →'}</button></footer></div>;
}
createRoot(document.getElementById('root')!).render(<Guide/>);
