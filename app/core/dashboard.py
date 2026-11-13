"""Read-only SPACEKIJUN home, using the linked user's existing RLS session.

Display rules follow spacekijun/src/hooks/useTodayTimetable, useWeeklySchedule,
useTasksJsonb, useNotifications and features/notice-board. No credentials reach UI.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import urllib.error
import urllib.parse
import urllib.request

from . import notify, supa_auth

KST = timezone(timedelta(hours=9))
PERIODS = {1: '09:00', 2: '10:00', 3: '11:00', 4: '12:50',
           5: '13:50', 6: '14:50', 7: '15:50'}


class Reader:
    def __init__(self):
        self.headers = supa_auth.auth_headers()
        self.session = supa_auth.load_session() or {}
        if not self.session.get('user_id'):
            raise ValueError('설정에서 SPACEKIJUN 계정을 연결해 주세요.')
        self.base = notify.config()['url'].rstrip('/') + '/rest/v1/'

    def get(self, table, params=None, body=None):
        url = self.base + table
        if params:
            url += '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={**self.headers, 'Content-Type': 'application/json'},
            data=None if body is None else json.dumps(body).encode(),
            method='GET' if body is None else 'POST')
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'데이터 조회 실패 ({exc.code}). 계정 연결을 확인하고 다시 시도해 주세요.') from None
        except (OSError, ValueError):
            raise RuntimeError('서버에 연결하지 못했습니다. 잠시 후 새로고침해 주세요.') from None


def assigned(value, name):
    if not name:
        return False
    if isinstance(value, str):
        return value == name
    values = value.values() if isinstance(value, dict) else value or []
    return any(isinstance(item, dict) and item.get('name') == name for item in values)


def task_rows(data, resource_id, today):
    rows = []
    for task in data.get('assigned_tasks') or []:
        meta = task.get('meta') or {}
        person = next((p for p in meta.get('assignees') or [] if p and p.get('id') == resource_id), None)
        if not person or task.get('status') in ('completed', 'cancelled') or person.get('status') == 'completed':
            continue
        raw = meta.get('deadlines') or [task.get('due_date')]
        dates = sorted(set(d[:10] for d in raw if isinstance(d, str) and len(d) >= 10))
        due = next((d for d in dates if d >= today), dates[-1] if dates else '')
        rows.append({'title': task.get('title') or '업무', 'detail': task.get('event_name') or '',
                     'date': due, 'deadlines': dates,
                     'label': '기한 초과' if due and due < today else '오늘 마감' if due == today else '마감' if due else '마감 없음'})
    return sorted(rows, key=lambda row: row['date'] or '9999')


def timetable(reader, resource):
    """이번 학기 시간표 한 주 전체 — 칸마다 {day 월=1…, period, title, detail}. 오늘 것은 snapshot 이 골라 쓴다."""
    settings = reader.get('system_settings', {'select': 'setting_value', 'setting_key': 'eq.academic_term', 'limit': 1})
    term = (settings[0].get('setting_value') if settings else None) or {}
    if not term.get('year') or term.get('semester') not in (1, 2):
        latest = reader.get('rpc/get_latest_timetable_term', body={})
        term = latest[0] if isinstance(latest, list) and latest else latest or {}
        term = {'year': term.get('academic_year'), 'semester': term.get('semester')}
    if not term.get('year'):
        return []
    student = resource.get('type') == 'student'
    rows = reader.get('student_timetable' if student else 'teacher_timetable', {
        'select': 'day_of_week,period,subject,teacher_name' if student else 'day_of_week,period,subject_name,grade,class_label',
        'resource_id' if student else 'teacher_resource_id': 'eq.' + resource['id'],
        'academic_year': 'eq.' + str(term['year']), 'semester': 'eq.' + str(term['semester']),
        'order': 'day_of_week.asc,period.asc'})
    cells = []
    for r in rows:
        if not (1 <= (r.get('period') or 0) <= 8 and 1 <= (r.get('day_of_week') or 0) <= 7):
            continue
        if student:
            title, detail = r.get('subject') or '수업', r.get('teacher_name') or ''
        else:
            title, detail = r.get('subject_name') or '수업', f"{r.get('grade')}-{r.get('class_label') or ''}"
        cells.append({'day': r['day_of_week'], 'period': r['period'], 'title': title, 'detail': detail})
    return cells


def today_lessons(cells, now, student):
    return [{'title': c['title'] if student else f"{c['title']} {c['detail']}",
             'time': PERIODS.get(c['period'], ''), 'label': f"{c['period']}교시", 'detail': '수업'}
            for c in cells if c['day'] == now.isoweekday()]


def identity(reader):
    """연결된 계정의 (user id, resource, 이름). 연결이 하나가 아니면 개인 정보를 묻기 전에 멈춘다.

    학생은 대부분 user_resource 연결이 없다 (2026-10-19: 재학생 630명 중 12명). 학생 계정이면 서버 규칙
    (current_student_code · owns_notification_resource)과 같게 **이메일 앞부분 = 학생 resource 의 meta.id**
    로 찾는다. 예전에는 여기서 교직원 오류로 멈춰 학생판 시간표·일정이 비었다."""
    uid = reader.session['user_id']
    links = reader.get('user_resource', {'select': 'resource_id', 'user_id': 'eq.' + uid, 'limit': 2})
    if not links:
        student = _student_identity(reader, uid)
        if student:
            return student
    if len(links) != 1:
        raise ValueError('계정에 연결된 교직원 정보를 확인할 수 없습니다. SPACEKIJUN 프로필을 확인해 주세요.')
    rid = links[0]['resource_id']
    resources = reader.get('resource', {'select': 'id,name,type', 'id': 'eq.' + rid, 'limit': 1})
    if not resources:
        raise ValueError('연결된 사용자 정보를 찾을 수 없습니다.')
    resource = resources[0]
    profiles = reader.get('profiles', {'select': 'name', 'id': 'eq.' + uid, 'limit': 1})
    name = profiles[0].get('name') if profiles else resource.get('name')
    return uid, resource, name or resource.get('name')


def _student_identity(reader, uid):
    """학생 계정이면 (uid, 학생 resource, 이름). 학생 계정이 아니면 None — 교직원 오류는 부른 쪽이 낸다."""
    profiles = reader.get('profiles', {'select': 'name,role,email', 'id': 'eq.' + uid, 'limit': 1})
    profile = profiles[0] if profiles else {}
    if profile.get('role') != 'student':
        return None
    code = (profile.get('email') or '').split('@')[0]
    rows = reader.get('resource', {'select': 'id,name,type', 'type': 'eq.student', 'status': 'eq.active',
                                   'meta->>id': 'eq.' + code, 'limit': 2}) if code else []
    if len(rows) != 1:
        raise ValueError('이 계정의 학생 정보를 찾을 수 없습니다. 스페이스기전 웹에서 내 정보를 확인하거나 '
                         '선생님께 알려 주세요.')
    return uid, rows[0], profile.get('name') or rows[0].get('name')


def meeting_title(meeting):
    meta = meeting.get('meta') or {}
    return meta.get('title') or meta.get('section_name') or meeting.get('kind') or '일정'


def saturday_off(moment, title):
    return moment.weekday() == 5 and any(s in title for s in ('토요휴업일', '휴업일', '토요일 휴업', '토요 휴업'))


def closes_school(meeting):
    """학교 전체가 쉬는 학사일정인가 (spacekijun/src/lib/schoolDay isClosingEntry — 토요휴업일·일부 학년은 빼고)"""
    meta = meeting.get('meta') or {}
    return (meeting.get('kind') == 'schedule' and meta.get('sbtr_dd_sc_nm') in ('휴업일', '공휴일')
            and (meta.get('title') or '').strip() != '토요휴업일' and not meta.get('no_class_grades'))


def month(year, month_no):
    """한 달 달력 — 6주 칸 전체의 {날짜: [일정]}와 쉬는 날. 일정 규칙은 이번 주 일정과 같다
    (학사일정 + 내가 맡은 일정). 여러 날 일정은 날마다 (spacekijun expandScheduleRows 와 같이
    끝이 다음 날 00:00 정각이면 그날은 빼고). 업무 마감은 패널이 받아 둔 업무에서 더한다."""
    first = datetime(year, month_no, 1, tzinfo=KST)
    start = first - timedelta(days=(first.weekday() + 1) % 7)       # 달력은 일요일부터
    end = start + timedelta(days=42)
    reader = Reader()
    uid, _resource, name = identity(reader)
    meetings = reader.get('meeting', [('select', 'starts_at,ends_at,kind,meta'),
        ('starts_at', 'lt.' + end.isoformat()), ('ends_at', 'gte.' + start.isoformat()), ('order', 'starts_at.asc')])
    days, closed = {}, set()
    first_key, last_key = start.date().isoformat(), (end - timedelta(days=1)).date().isoformat()
    for meeting in meetings:
        meta = meeting.get('meta') or {}
        title = meeting_title(meeting)
        begin = datetime.fromisoformat(meeting['starts_at'].replace('Z', '+00:00')).astimezone(KST)
        try:
            finish = datetime.fromisoformat(meeting['ends_at'].replace('Z', '+00:00')).astimezone(KST) - timedelta(microseconds=1)
        except (KeyError, AttributeError, TypeError, ValueError):
            finish = begin
        finish = max(finish, begin)
        if saturday_off(begin, title) or not (meeting.get('kind') == 'schedule' or assigned(meta.get('assignee'), name)):
            continue
        whole = bool(meta.get('date_only')) or finish.date() > begin.date()
        day = begin.date()
        for _ in range(62):
            key = day.isoformat()
            if key > last_key or day > finish.date():
                break
            if key >= first_key:
                days.setdefault(key, []).append({'title': title, 'time': '' if whole else begin.strftime('%H:%M'),
                    'label': '종일' if whole else '일정', 'kind': 'schedule' if meeting.get('kind') == 'schedule' else 'mine'})
                if closes_school(meeting):
                    closed.add(key)
            day += timedelta(days=1)
    if (supa_auth.load_session() or {}).get('user_id') != uid:
        raise ValueError('계정이 변경되었습니다. 다시 불러와 주세요.')
    for rows in days.values():
        rows.sort(key=lambda row: row['time'] or '')
    return {'month': f'{year:04d}-{month_no:02d}', 'start': first_key, 'days': days, 'closed': sorted(closed)}


def snapshot():
    reader = Reader()
    uid, resource, name = identity(reader)
    rid = resource['id']
    now = datetime.now(KST)
    today = now.date().isoformat()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7 - now.weekday())
    jobs = {
        'timetable': lambda: timetable(reader, resource),
        'meetings': lambda: reader.get('meeting', [('select', 'id,starts_at,ends_at,kind,meta'),
            ('starts_at', 'gte.' + start.isoformat()), ('starts_at', 'lt.' + end.isoformat()), ('order', 'starts_at.asc')]),
        'tasks': lambda: reader.get('rpc/get_my_tasks_jsonb', body={'p_user_id': uid, 'p_status': None, 'p_include_managed': True}),
        'notices': lambda: reader.get('department_notice', {'select': 'title,content,department,start_date,end_date',
            'start_date': 'lte.' + today, 'end_date': 'gte.' + today, 'order': 'created_at.desc', 'limit': 5}),
        'notifications': lambda: reader.get('notification_events', {'select': 'title,message,is_read,created_at',
            'resource_id': 'eq.' + rid, 'order': 'created_at.desc', 'limit': 5}),
    }
    student = resource.get('type') == 'student'
    if student:
        # 학생에게는 업무가 없고 부서 공지는 교직원만 읽는다 — 묻지 않는다 (서버 요청도 줄인다)
        jobs['tasks'] = jobs['notices'] = lambda: []
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {key: pool.submit(job) for key, job in jobs.items()}
        for key, future in futures.items():
            try:
                data[key] = future.result()
            except Exception:
                data[key] = []
                errors[key] = '불러오지 못했습니다. 새로고침해 주세요.'
    tasks = task_rows((data['tasks'][0] if data['tasks'] else {}), rid, today)
    today_rows = today_lessons(data['timetable'], now, student)
    week = []
    for meeting in data['meetings']:
        meta = meeting.get('meta') or {}
        moment = datetime.fromisoformat(meeting['starts_at'].replace('Z', '+00:00')).astimezone(KST)
        day = moment.date().isoformat()
        title = meeting_title(meeting)
        row = {'title': title, 'time': '' if meta.get('date_only') else moment.strftime('%H:%M'),
               'date': day, 'label': '종일' if meta.get('date_only') else '일정', 'detail': ''}
        mine = assigned(meta.get('assignee'), name)
        if day == today and not meta.get('date_only') and (meeting.get('kind') != 'duty' or mine):
            today_rows.append(row)
        if not saturday_off(moment, title) and (meeting.get('kind') == 'schedule' or mine):
            week.append(row)
    for task in tasks:
        for due in task['deadlines']:
            if today <= due < end.date().isoformat():
                week.append({'title': task['title'], 'date': due, 'time': '', 'label': '업무 마감', 'detail': ''})
    if (supa_auth.load_session() or {}).get('user_id') != uid:
        raise ValueError('계정이 변경되었습니다. 다시 불러와 주세요.')
    return {'name': name, 'date': today, 'updated_at': now.isoformat(),
            'today': sorted(today_rows, key=lambda row: row['time'] or '99:99'),
            'timetable_week': data['timetable'], 'periods': {str(k): v for k, v in PERIODS.items()},
            'week': sorted(week, key=lambda row: (row['date'], row['time'])),
            'tasks': tasks, 'notices': data['notices'], 'notifications': data['notifications'], 'errors': errors}
