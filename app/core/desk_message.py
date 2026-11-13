"""데스크 메시지 — 학생 ↔ 선생님 (2026-10-19 요청).

내용은 스페이스기전 알림(notification_events, type 'desk_message')으로만 오간다. 새 표는 없다.
  · 보내기·주소록은 서버 함수 send_desk_message · desk_message_directory 만 쓴다 — 보낸 사람은
    로그인 계정에서 서버가 정하고, 학생 → 재직 선생님 · 선생님 → 재학 학생만 된다
    (deploy/supabase/20261019_desk_message.sql).
  · 받은 메시지 읽기·읽음 표시는 본인 세션(RLS: 본인 알림만)으로 한다.
  · 내가 보낸 것은 서버 함수 desk_message_sent 로 읽는다 — 보낸 사람 본인 것만 (2026-10-21,
    deploy/supabase/20261021_desk_message_sent.sql). 그래서 어느 PC 에서 열어도 대화가 같다.
    전에는 보낸 PC 에만 DPAPI 로 남겨 다른 PC 에서는 내 말이 빠졌다 — 그 파일은 보이면 지운다.
  · 사진 (2026-10-22): 붙여넣기·끌어 놓기로 한 번에 4장. 화면(popover.js)이 긴 변 1600px·1.2MB 안팎으로 줄여
    보내고, 여기서 다시 확인한다. 서버(desk_message_images)에는 **7일만** 있다 — 보낸 사람·받는 사람만 받는다
    (deploy/supabase/20261022_desk_message_images.sql). 대화에 보인 사진은 이 PC 의 **캡처 보관함 폴더에 파일로**
    남는다(보낸 것은 보낼 때). 그래서 7일이 지나도 남고, 지우는 것은 캡처 보관함에서 한다. 지운 사진은
    다시 받아 오지 않는다 — 사진 id → 파일 이름을 IMAGE_INDEX 에 적어 두고, 적힌 파일이 없으면 지운 것으로 본다.
  · 처음 보낼 때 허락받기 (2026-10-31): 학생은 대화가 진행 중인 선생님께만 보낸다. 용건을 보내면(request_permission) 선생님이
    허락·거절하고(decide), 선생님은 대화를 끝낼 수 있다(end_session). 막는 것은 서버 send_desk_message_v2 다
    (spacekijun supabase/migrations/20261031130000_desk_message_session.sql).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from . import edition, notify, supa_auth

TYPE = 'desk_message'
MAX_BODY = 1000                 # 서버와 같은 한도
LEGACY_SENT_PATH = os.path.join(edition.DATA_DIR, 'desk-messages-sent.bin')   # 1.0.19 까지 이 PC 에 남기던 것
SENT_KEEP = 300                 # 대화에 보이는 보낸 메시지 수
FIELDS = 'id,title,message,meta,is_read,created_at'
OUR_ERRORS = {'28000', '42501', '22023', '22001', 'P0002', '54000'}   # 서버 함수가 사람이 읽을 글로 낸 오류
MAX_IMAGES = 4                  # 한 번에 보내는 사진 수 (서버와 같은 한도)
MAX_IMAGE_BYTES = 1536 * 1024   # 한 장 (서버와 같은 한도)
MAX_IMAGE_SIDE = 8000
IMAGE_TYPES = {'JPEG': ('image/jpeg', '.jpg'), 'PNG': ('image/png', '.png'), 'WEBP': ('image/webp', '.webp')}
IMAGE_INDEX = os.path.join(edition.DATA_DIR, 'desk-message-images.json')   # 사진 id → 캡처 보관함 파일 이름
PREVIEW = 640                   # 대화에 보이는 미리보기 긴 변 (px)
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

_index_lock = threading.Lock()


class MessageError(RuntimeError):
    pass


def _request(method: str, path: str, params: dict | None = None, body=None, prefer: str | None = None):
    url = notify.config()['url'].rstrip('/') + '/rest/v1/' + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    headers = {**supa_auth.auth_headers(), 'Content-Type': 'application/json'}
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(url, headers=headers, method=method,
                                 data=None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8'))
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        # 서버 함수가 낸 오류(받는 사람 없음 · 한도 넘음 등)는 그대로 보인다 — 사람이 읽는 문장이다
        # 한도·받는 사람 없음은 PostgREST 가 500 으로 돌려준다(P0002·54000) — 우리 함수가 일부러 낸 코드면 글을 보인다
        try:
            error = json.loads(exc.read().decode('utf-8', 'replace'))
            detail, code = error.get('message') or '', error.get('code') or ''
        except (OSError, ValueError, AttributeError):
            detail, code = '', ''
        ours = code in OUR_ERRORS or exc.code in (400, 403, 404)
        if ours and detail and not detail.startswith(('permission denied', 'Could not find')):
            raise MessageError(detail) from None
        raise MessageError(f'메시지 서버 요청 실패 ({exc.code}). 계정 연결을 확인해 주세요.') from None
    except (OSError, ValueError):
        raise MessageError('서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.') from None


def directory() -> dict:
    """보낼 수 있는 사람 — {'role': 'student'|'teacher', 'me': 내 표시 이름, 'people': [...]}"""
    data = _request('POST', 'rpc/desk_message_directory', body={})
    if not isinstance(data, dict) or not isinstance(data.get('people'), list):
        raise MessageError('주소록을 불러오지 못했습니다.')
    return data


def received(limit: int = 60) -> list[dict]:
    rows = _request('GET', 'notification_events', {'select': FIELDS, 'type': 'eq.' + TYPE,
                                                    'order': 'created_at.desc', 'limit': str(limit)})
    return [shape(row) for row in rows or []]


def unread_after(after: str | None) -> list[dict]:
    """새로 온 안 읽은 메시지 (알림을 띄울 것). after 는 이미 알린 가장 늦은 created_at."""
    params = {'select': FIELDS, 'type': 'eq.' + TYPE, 'is_read': 'eq.false',
              'order': 'created_at.desc', 'limit': '20'}
    if after:
        params['created_at'] = 'gt.' + after
    return [shape(row) for row in _request('GET', 'notification_events', params) or []]


def unread_count() -> int:
    rows = _request('GET', 'notification_events', {'select': 'id', 'type': 'eq.' + TYPE,
                                                    'is_read': 'eq.false', 'limit': '100'})
    return len(rows or [])


def mark_read(ids: list[str]) -> None:
    ids = [str(i) for i in ids if isinstance(i, str) and len(i) == 36][:100]
    if ids:
        _request('PATCH', 'notification_events', {'id': 'in.(' + ','.join(ids) + ')', 'type': 'eq.' + TYPE},
                 body={'is_read': True}, prefer='return=minimal')


def send(recipient: str, body: str, label: str = '', reply_to: str | None = None,
         images: list | None = None, folder=None) -> dict:
    """보낸다. images 는 화면이 줄여 보낸 [{'data': base64, ...}] — 형식·크기는 여기서 다시 본다.
    보낸 사진은 folder(캡처 보관함)에 곧바로 남긴다."""
    body = (body or '').strip()
    if images is not None and (not isinstance(images, list) or len(images) > MAX_IMAGES):
        raise MessageError(f'사진은 한 번에 {MAX_IMAGES}장까지 보낼 수 있습니다.')
    pictures = [_checked_image(item) for item in images or []]
    if not body and not pictures:
        raise MessageError('메시지 내용을 써 주세요.')
    if len(body) > MAX_BODY:
        raise MessageError(f'메시지는 {MAX_BODY}자까지 보낼 수 있습니다 (지금 {len(body)}자).')
    if not isinstance(recipient, str) or len(recipient) != 36:
        raise MessageError('받는 사람을 골라 주세요.')
    result = _request('POST', 'rpc/send_desk_message_v2', body={
        'p_recipient_resource_id': recipient, 'p_body': body, 'p_reply_to_notification_id': reply_to or None,
        'p_images': [{'data': base64.b64encode(raw).decode('ascii'), 'mime': mime, 'width': w, 'height': h}
                     for raw, mime, w, h in pictures] or None})
    if not isinstance(result, dict) or not result.get('notification_id'):
        raise MessageError('메시지를 보내지 못했습니다.')
    if folder is not None:
        for picture, placed in zip(pictures, result.get('images') or []):
            try:
                _keep(folder, placed.get('id'), picture[0], picture[1], label or result.get('recipient_name') or '',
                      datetime.now())
            except (OSError, ValueError, AttributeError):
                pass                       # 보내기는 됐다 — 이 PC 에 못 남겨도 서버에서 다시 받는다
    return result


def sessions() -> dict:
    """학생이 선생님께 보내도 되는지 (2026-10-31, 20261031130000_desk_message_session.sql) —
    {'role': 'student'|'teacher', 'sessions': {상대 id: 'pending'|'active'|'declined'|'ended'}}. 없는 상대는 아직 허락받지 않은 것."""
    data = _request('POST', 'rpc/desk_message_sessions', body={})
    if not isinstance(data, dict) or not isinstance(data.get('sessions'), list):
        raise MessageError('대화 상태를 불러오지 못했습니다.')
    return {'role': data.get('role') or '',
            'sessions': {row['peer']: row.get('status') or '' for row in data['sessions']
                         if isinstance(row, dict) and row.get('peer')}}


def request_permission(teacher: str, body: str) -> dict:
    """학생: 용건을 써서 허락을 구한다."""
    body = (body or '').strip()
    if not body:
        raise MessageError('용건을 써 주세요.')
    if len(body) > MAX_BODY:
        raise MessageError(f'용건은 {MAX_BODY}자까지 쓸 수 있습니다 (지금 {len(body)}자).')
    if not isinstance(teacher, str) or not UUID.match(teacher):
        raise MessageError('받는 사람을 골라 주세요.')
    return _request('POST', 'rpc/desk_message_request', body={'p_teacher_resource_id': teacher, 'p_body': body}) or {}


def decide(student: str, approve: bool) -> dict:
    """선생님: 요청을 허락하거나 거절한다."""
    if not isinstance(student, str) or not UUID.match(student) or not isinstance(approve, bool):
        raise MessageError('요청을 다시 골라 주세요.')
    return _request('POST', 'rpc/desk_message_decide',
                    body={'p_student_resource_id': student, 'p_approve': approve}) or {}


def end_session(student: str) -> dict:
    """선생님: 대화를 끝낸다 — 학생은 다시 허락을 구해야 한다."""
    if not isinstance(student, str) or not UUID.match(student):
        raise MessageError('대화를 다시 골라 주세요.')
    return _request('POST', 'rpc/desk_message_end_session', body={'p_student_resource_id': student}) or {}


def shape(row: dict) -> dict:
    """알림 한 줄 → 화면이 쓰는 받은 메시지. 사진만 보낸 것은 body 가 '사진 N장'(트레이 알림·목록에 쓴다)이고
    photo_only 가 참이다 — 대화 말풍선은 글을 빼고 사진만 보인다."""
    meta = row.get('meta') or {}
    return {'id': row.get('id'), 'from': meta.get('sender_resource_id') or '',
            'from_label': meta.get('sender_label') or meta.get('sender_name') or (row.get('title') or '').removeprefix('[메시지] '),
            'role': meta.get('sender_role') or '', 'body': row.get('message') or '', 'time': row.get('created_at') or '',
            'read': bool(row.get('is_read')), 'quote': meta.get('quote') or '', 'replied': bool(meta.get('replied_at')),
            'images': _image_refs(meta.get('images')), 'photo_only': bool(meta.get('photo_only')),
            'kind': _kind(meta.get('kind'))}


def _kind(value) -> str:
    """요청('session_request')·허락/거절/종료 안내('session_event') 구별 — 보이는 모양만 정한다. 허락 여부는 서버 표가 정한다."""
    return value if value in ('session_request', 'session_event') else ''


def _image_refs(value) -> list[dict]:
    """meta.images → [{'id','w','h'}] — 모양이 어긋난 것은 버린다 (받는 사람이 자기 알림 meta 를 고칠 수 있다)."""
    refs = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict) and isinstance(item.get('id'), str) and UUID.match(item['id']):
            w, h = item.get('w'), item.get('h')
            refs.append({'id': item['id'], 'w': w if isinstance(w, int) else 0, 'h': h if isinstance(h, int) else 0})
    return refs[:MAX_IMAGES]


def sent(limit: int = SENT_KEEP) -> list[dict]:
    """내가 보낸 메시지 — 서버에서 (어느 PC 에서나 같다). [{'id','to','to_label','body','time','read'}]"""
    rows = _request('POST', 'rpc/desk_message_sent', body={'p_limit': limit})
    if not isinstance(rows, list):
        raise MessageError('보낸 메시지를 불러오지 못했습니다.')
    _forget_legacy()
    return [{'id': row.get('id'), 'to': row.get('to') or '', 'to_label': row.get('to_label') or '',
             'body': row.get('body') or '', 'time': row.get('time') or '',
             'read': bool(row.get('read')), 'images': _image_refs(row.get('images')),
             'photo_only': bool(row.get('photo_only')), 'kind': _kind(row.get('kind'))}
            for row in rows if isinstance(row, dict) and row.get('to')]


def _forget_legacy() -> None:
    """서버가 보낸 메시지를 다 갖고 있으니 이 PC 에 따로 남겼던 사본은 지운다."""
    try:
        os.remove(LEGACY_SENT_PATH)
    except OSError:
        pass


def conversations(inbox: list[dict], outbox: list[dict]) -> list[dict]:
    """받은 것과 보낸 것을 상대마다 묶는다 — 최근 대화가 위로. 대화 안은 오래된 것부터."""
    threads: dict[str, dict] = {}
    for item in inbox:
        if not item['from']:
            continue
        thread = threads.setdefault(item['from'], {'id': item['from'], 'label': item['from_label'], 'messages': []})
        thread['label'] = thread['label'] or item['from_label']
        thread['messages'].append({**item, 'mine': False})
    for item in outbox:
        thread = threads.setdefault(item['to'], {'id': item['to'], 'label': item.get('to_label') or '', 'messages': []})
        thread['label'] = thread['label'] or item.get('to_label') or ''
        thread['messages'].append({'id': item['id'], 'body': item['body'], 'time': item['time'], 'mine': True,
                                   'read': True, 'quote': '', 'replied': False,
                                   'images': item.get('images') or [], 'photo_only': bool(item.get('photo_only')),
                                   'kind': item.get('kind') or ''})
    for thread in threads.values():
        thread['messages'].sort(key=lambda m: _when(m['time']))
        thread['unread'] = sum(1 for m in thread['messages'] if not m['mine'] and not m['read'])
        thread['last'] = thread['messages'][-1]['time'] if thread['messages'] else ''
    return sorted(threads.values(), key=lambda t: _when(t['last']), reverse=True)


def _when(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (AttributeError, ValueError):
        return 0.0


# ── 사진 ─────────────────────────────────────────────────────
def _checked_image(item) -> tuple[bytes, str, int, int]:
    """화면이 보낸 사진 한 장 → (바이트, mime, 가로, 세로). 정말 JPEG·PNG·WebP 그림인지 열어 본다."""
    data = item.get('data') if isinstance(item, dict) else None
    if not isinstance(data, str) or len(data) > MAX_IMAGE_BYTES * 4 // 3 + 64:
        raise MessageError('사진 한 장은 1.5MB 까지 보낼 수 있습니다. 더 작게 줄여 주세요.')
    try:
        raw = base64.b64decode(data.split(',', 1)[-1], validate=True)
    except ValueError:
        raise MessageError('사진 파일이 올바르지 않습니다.') from None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise MessageError('사진 한 장은 1.5MB 까지 보낼 수 있습니다. 더 작게 줄여 주세요.')
    mime, width, height = _inspect(raw)
    return raw, mime, width, height


def _inspect(raw: bytes) -> tuple[str, int, int]:
    """(mime, 가로, 세로). 그림이 아니거나 JPEG·PNG·WebP 가 아니면 MessageError."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            kind, (width, height) = picture.format, picture.size
            picture.verify()
    except Exception:
        raise MessageError('사진 파일이 올바르지 않습니다.') from None
    if kind not in IMAGE_TYPES:
        raise MessageError('사진은 JPEG·PNG·WebP 만 보낼 수 있습니다.')
    if not (0 < width <= MAX_IMAGE_SIDE and 0 < height <= MAX_IMAGE_SIDE):
        raise MessageError('사진 크기가 올바르지 않습니다.')
    return IMAGE_TYPES[kind][0], width, height


def _load_index() -> dict:
    try:
        with open(IMAGE_INDEX, encoding='utf-8') as source:
            data = json.load(source)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_index(data: dict) -> None:
    os.makedirs(os.path.dirname(IMAGE_INDEX), exist_ok=True)
    temporary = IMAGE_INDEX + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as target:
        json.dump(data, target, ensure_ascii=False)
    os.replace(temporary, IMAGE_INDEX)


def _file_name(folder, label: str, when: datetime, extension: str) -> str:
    """'메시지 사진 2026-10-22 14.03.05 김선생 선생님.jpg' — 파일 이름에 못 쓰는 글자는 뺀다."""
    who = ''.join(ch for ch in label or '' if ch not in '\\/:*?"<>|' and ord(ch) >= 32).strip()[:40]
    stem = f"메시지 사진 {when.strftime('%Y-%m-%d %H.%M.%S')}" + (f' {who}' if who else '')
    name, number = stem + extension, 2
    while os.path.exists(os.path.join(folder, name)):
        name, number = f'{stem} ({number}){extension}', number + 1
    return name


def _keep(folder, image_id, raw: bytes, mime: str, label: str, when: datetime) -> str | None:
    """사진을 캡처 보관함에 파일로 남기고 id 를 적어 둔다. 이미 적힌 id 면(지운 것 포함) 새로 남기지 않는다."""
    if not isinstance(image_id, str) or not UUID.match(image_id):
        return None
    extension = next((ext for value, ext in IMAGE_TYPES.values() if value == mime), '.jpg')
    with _index_lock:
        index = _load_index()
        if image_id in index:
            return index[image_id]
        os.makedirs(folder, exist_ok=True)
        name = _file_name(folder, label, when, extension)
        with open(os.path.join(folder, name), 'wb') as target:
            target.write(raw)
        index[image_id] = name
        _save_index(index)
    return name


def _preview(path) -> str:
    from PIL import Image
    with Image.open(path) as picture:
        picture.thumbnail((PREVIEW, PREVIEW))
        canvas = picture.convert('RGBA')
        flat = Image.new('RGB', canvas.size, (255, 255, 255))
        flat.paste(canvas, mask=canvas.getchannel('A'))
        buffer = io.BytesIO()
        flat.save(buffer, 'JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def image(folder, image_id: str, label: str = '') -> dict:
    """대화에 보일 사진 한 장 — {'src': 미리보기, 'name': 보관함 파일 이름}.
    이 PC 에 있으면 그것을, 없으면 서버에서 받아 캡처 보관함에 남긴 뒤 보인다.
    {'removed': True}: 보관함에서 지웠다(다시 받지 않는다) · {'expired': True}: 서버의 7일이 지났다."""
    if not isinstance(image_id, str) or not UUID.match(image_id):
        raise MessageError('사진 id 가 올바르지 않습니다.')
    with _index_lock:
        name = _load_index().get(image_id)
    if name is not None:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            return {'removed': True}
        return {'src': _preview(path), 'name': name}
    row = _request('POST', 'rpc/desk_message_image', body={'p_image_id': image_id})
    if not isinstance(row, dict) or not row.get('data'):
        return {'expired': True}
    try:
        raw = base64.b64decode(row['data'])
    except ValueError:
        raise MessageError('사진을 받지 못했습니다.') from None
    mime = _inspect(raw)[0]
    try:
        when = datetime.fromisoformat(str(row.get('created_at')).replace('Z', '+00:00')).astimezone()
    except ValueError:
        when = datetime.now()
    name = _keep(folder, image_id, raw, mime, label, when)
    return {'src': _preview(os.path.join(folder, name)), 'name': name}


def local_path(folder, image_id) -> str | None:
    """이 PC 에 남은 사진 파일 — 없거나 지웠으면 None."""
    with _index_lock:
        name = _load_index().get(image_id) if isinstance(image_id, str) else None
    path = os.path.join(folder, name) if name else None
    return path if path and os.path.isfile(path) else None


def full_image(folder, image_id) -> dict:
    """크게 볼 사진 — 이 PC 캡처 보관함의 원본 그대로 {'src': data URL, 'name'} (2026-10-22, 대화의 사진 보기).
    한 장은 보낼 때 1.5MB 로 묶였지만, 보관함에서 바꿔 넣었을 수 있어 너무 크면 미리보기만큼 줄여 보낸다."""
    path = local_path(folder, image_id)
    if not path:
        return {'removed': True}
    name = os.path.basename(path)
    if os.path.getsize(path) > 8 * 1024 * 1024:
        return {'src': _preview(path), 'name': name}
    mime = {'.png': 'image/png', '.webp': 'image/webp'}.get(os.path.splitext(name)[1].lower(), 'image/jpeg')
    with open(path, 'rb') as source:
        return {'src': f'data:{mime};base64,' + base64.b64encode(source.read()).decode('ascii'), 'name': name}


def renamed(old: str, new: str) -> None:
    """캡처 보관함에서 이름을 바꾸면 사진 id 가 새 이름을 가리키게 한다 (지운 것으로 보지 않게)."""
    with _index_lock:
        index = _load_index()
        hits = [image_id for image_id, name in index.items() if name == old]
        for image_id in hits:
            index[image_id] = new
        if hits:
            _save_index(index)
