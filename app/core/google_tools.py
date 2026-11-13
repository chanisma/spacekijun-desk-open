"""구글 수업 도구(web/gtools.js)의 구글 API 다리 — 클래스룸·슬라이드 발표·설문지를 «구글 로그인 없이»(2026-10-14 요청).

QR 승인 때 받은 토큰(드라이브 + 클래스룸 범위, 1시간)으로 기기가 구글 API 를 직접 부른다. 토큰은 화면(JS)에 주지 않는다.
화면이 부를 수 있는 주소는 아래 허용 목록뿐이다 — 쓰기는 «클래스룸 공지 올리기» 하나.
안드로이드판 GoogleApi.kt 와 같은 규칙이다.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

READ_PREFIXES = (
    'https://classroom.googleapis.com/v1/courses',
    'https://classroom.googleapis.com/v1/userProfiles/',
    'https://forms.googleapis.com/v1/forms/',
    'https://slides.googleapis.com/v1/presentations/',
    'https://www.googleapis.com/drive/v3/files?',
)
POST_ANNOUNCEMENT = re.compile(r'^https://classroom\.googleapis\.com/v1/courses/[A-Za-z0-9_-]+/announcements$')
API_NAMES = {'classroom': 'Google Classroom', 'forms': 'Google Forms', 'slides': 'Google Slides', 'www': 'Google Drive'}


def allowed(method: str, url: str) -> bool:
    if not isinstance(url, str) or '..' in url or '#' in url or '@' in url or len(url) > 4000:
        return False
    if method == 'GET':
        return url.startswith(READ_PREFIXES)
    if method == 'POST':
        return bool(POST_ANNOUNCEMENT.match(url))
    return False


def api_name(url: str) -> str:
    host = url.split('/')[2].split('.')[0] if url.count('/') >= 2 else ''
    return API_NAMES.get(host, 'Google')


def explain(status: int, text: str, url: str) -> dict:
    """구글 오류 → 화면이 알아듣는 이유(reason). 오류 본문·토큰은 싣지 않는다."""
    lower = (text or '').lower()
    if status == 401:
        return {'ok': False, 'reason': 'auth', 'status': status}
    if status == 403 and ('service_disabled' in lower or 'has not been used' in lower or 'is disabled' in lower
                          or 'accessnotconfigured' in lower):
        return {'ok': False, 'reason': 'disabled', 'api': api_name(url), 'status': status}
    if status == 403 and ('insufficient' in lower or 'scope' in lower):
        return {'ok': False, 'reason': 'scope', 'status': status}
    if status == 404:
        return {'ok': False, 'reason': 'notfound', 'status': status}
    if status == 403:
        return {'ok': False, 'reason': 'forbidden', 'status': status, 'error': '이 항목에 대한 권한이 없습니다.'}
    return {'ok': False, 'reason': 'error', 'status': status, 'error': f'구글 요청이 실패했습니다({status}).'}


def call(token: str | None, method, url, body=None, opener=urllib.request.urlopen) -> dict:
    method = str(method or 'GET').upper()
    url = str(url or '')
    if not allowed(method, url):
        return {'ok': False, 'reason': 'denied', 'error': '허용하지 않은 요청입니다.'}
    if not token:
        return {'ok': False, 'reason': 'auth'}
    data = None
    headers = {'Authorization': 'Bearer ' + token}
    if method == 'POST':
        if not isinstance(body, dict) or not str(body.get('text') or '').strip():
            return {'ok': False, 'reason': 'denied', 'error': '공지 내용이 비어 있습니다.'}
        # 공지는 글과 게시 상태만 — 화면이 다른 필드(대상 학생 등)를 섞지 못하게
        data = json.dumps({'text': str(body['text'])[:30000], 'state': 'PUBLISHED'}).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=UTF-8'
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with opener(request, timeout=30) as res:
            raw = res.read()
        return {'ok': True, 'data': json.loads(raw.decode('utf-8')) if raw else {}}
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode('utf-8', 'replace')
        except Exception:
            text = ''
        return explain(e.code, text, url)
    except (urllib.error.URLError, OSError, ValueError):
        return {'ok': False, 'reason': 'network', 'error': '인터넷 연결을 확인해 주세요.'}
