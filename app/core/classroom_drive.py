"""교실판 드라이브 — 선생님 구글 드라이브를 프로그램 안 탐색기에서 일반 폴더처럼.

승인 때 받은 토큰(전체 드라이브 `drive`, 1시간)으로 드라이브 API 를 직접 부른다. 토큰은 메모리에만 있다.

  · 탐색   폴더 목록(내 드라이브 · 공유 드라이브 · 공유 문서함), 경로 이동
  · 열기   파일을 수업 폴더에 받아 이 PC 의 프로그램으로 연다. 구글 문서·시트·슬라이드·그림은
           docx·xlsx·pptx·pdf 로 바꿔 받는다.
  · 되올리기 연 파일이 저장되면(크기·수정 시각이 바뀌고 2초 그대로면) 드라이브의 **같은 파일에 새 판으로** 올린다.
           구글 문서에서 바꿔 받은 파일은 원본(구글 문서)을 덮을 수 없어 같은 폴더에 «(교실에서 고침)» 새 파일로 올리고,
           그 뒤로는 그 새 파일을 갱신한다.
  · 올리기·새 폴더
  · 못 올린 파일 수업이 끝날 때 토큰이 끝나 못 올린 파일은 이 PC 에 남겨 두었다가(unsent/), 같은 선생님이 다음에
           연결하면 드라이브의 «교실에서 올리지 못한 파일» 폴더로 올리고 지운다.
  · 컴퓨터로 복사 고른 파일·폴더를 선생님이 고른 이 PC 의 폴더로 받는다(2026-10-14 요청). 수업이 끝나도 **지우지 않는다**
           — 남길지는 선생님이 정한다. 연 파일을 교실에서 고쳤으면 드라이브본이 아니라 그 최신본을 복사한다.
           복사한 것은 선생님별로 기억해 다음 수업에 «이 PC 에 복사한 파일»에서 바로 연다(PcShelf, 2026-10-15 요청).

열어 둔 파일(연 파일)은 수업 폴더(sessions/<수업>/drive/)에 받아 거기서 열고, 수업이 끝나면 올린 뒤 지운다.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .classroom_link import DATA_DIR

API = 'https://www.googleapis.com/drive/v3'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
FOLDER = 'application/vnd.google-apps.folder'
SHORTCUT = 'application/vnd.google-apps.shortcut'
EXPORTS = {
    'application/vnd.google-apps.document':
        ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
    'application/vnd.google-apps.spreadsheet':
        ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
    'application/vnd.google-apps.presentation':
        ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
    'application/vnd.google-apps.drawing': ('application/pdf', '.pdf'),
}
MAX_DOWNLOAD = 500 * 1024 * 1024
LIST_FIELDS = 'nextPageToken,files(id,name,mimeType,size,modifiedTime,shortcutDetails,capabilities/canEdit)'
UNSENT_DIR = os.path.join(DATA_DIR, 'unsent')
UNSENT_FOLDER = '교실에서 올리지 못한 파일'
SETTLE = 2.0                # 저장이 끝났다고 볼 때까지 크기·시각이 그대로여야 하는 초
MAX_COPY_FILES = 500        # 컴퓨터로 복사 한 번에 받는 파일 수 상한(폴더 안까지)
MAX_COPY_DEPTH = 10


class DriveError(RuntimeError):
    def __init__(self, message: str, auth: bool = False):
        super().__init__(message)
        self.auth = auth          # 토큰이 끝났거나 권한이 없다 — 다시 연결해야 한다


_BAD = str.maketrans({c: '_' for c in '<>:"/\\|?*'})


def safe_name(name: str, ext: str = '') -> str:
    stem = ''.join(ch for ch in (name or '') if ord(ch) >= 32).translate(_BAD).strip(' .') or '파일'
    if ext and not stem.lower().endswith(ext):
        stem += ext
    root, dot_ext = os.path.splitext(stem)
    return root[:120 - len(dot_ext)] + dot_ext


def _q(value: str) -> str:
    return value.replace('\\', '\\\\').replace("'", "\\'")


class Drive:
    def __init__(self, token: str, opener=urllib.request.urlopen):
        self.token = token
        self.opener = opener

    # 저수준 ------------------------------------------------------------------
    def _open(self, url: str, method: str = 'GET', data: bytes | None = None, headers: dict | None = None,
              timeout: int = 60):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={'Authorization': 'Bearer ' + self.token, **(headers or {})})
        try:
            return self.opener(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise DriveError('드라이브 연결 시간이 끝났습니다. QR 로 다시 연결해 주세요.', auth=True) from None
            if e.code == 403:
                body = ''
                try:
                    body = e.read().decode('utf-8', 'replace')
                except Exception:
                    pass
                if 'insufficient' in body.lower() or 'scope' in body.lower():
                    raise DriveError('드라이브 전체 권한이 없습니다. QR 승인 때 구글 창에서 허용해 주세요.', auth=True) from None
                raise DriveError('이 파일·폴더에 대한 권한이 없습니다.') from None
            if e.code == 404:
                raise DriveError('드라이브에서 찾지 못했습니다(지워졌거나 권한 없음).') from None
            raise DriveError(f'드라이브 요청이 실패했습니다({e.code}).') from None
        except (urllib.error.URLError, OSError):
            raise DriveError('인터넷 연결을 확인해 주세요.') from None

    def _json(self, url: str, method: str = 'GET', body: dict | None = None) -> dict:
        data = json.dumps(body).encode('utf-8') if body is not None else None
        headers = {'Content-Type': 'application/json; charset=UTF-8'} if body is not None else None
        with self._open(url, method, data, headers) as res:
            raw = res.read()
        return json.loads(raw.decode('utf-8')) if raw else {}

    # 탐색 --------------------------------------------------------------------
    def list(self, folder_id: str = 'root', drive_id: str | None = None) -> list[dict]:
        """폴더 안(휴지통 제외). folder_id='shared' 는 «공유 문서함»(나와 공유된 것)."""
        if folder_id == 'shared':
            query = 'sharedWithMe = true and trashed = false'
        else:
            query = f"'{_q(folder_id)}' in parents and trashed = false"
        params = {'q': query, 'fields': LIST_FIELDS, 'pageSize': 200, 'orderBy': 'folder,name_natural',
                  'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
        if drive_id:
            params.update({'corpora': 'drive', 'driveId': drive_id})
        items, token = [], None
        for _ in range(10):                      # 2,000개까지
            if token:
                params['pageToken'] = token
            page = self._json(f'{API}/files?' + urllib.parse.urlencode(params))
            items += page.get('files') or []
            token = page.get('nextPageToken')
            if not token:
                break
        return items

    def shared_drives(self) -> list[dict]:
        page = self._json(f'{API}/drives?' + urllib.parse.urlencode({'pageSize': 100, 'fields': 'drives(id,name)'}))
        return page.get('drives') or []

    def meta(self, file_id: str) -> dict:
        q = urllib.parse.urlencode({'fields': 'id,name,mimeType,size,modifiedTime,parents,shortcutDetails,driveId',
                                    'supportsAllDrives': 'true'})
        return self._json(f'{API}/files/{urllib.parse.quote(file_id)}?{q}')

    def resolve(self, meta: dict) -> dict:
        """바로가기면 원본으로"""
        if meta.get('mimeType') == SHORTCUT:
            target = (meta.get('shortcutDetails') or {}).get('targetId')
            if not target:
                raise DriveError('바로가기의 원본을 찾지 못했습니다.')
            return self.meta(target)
        return meta

    # 받기 --------------------------------------------------------------------
    def _save(self, url: str, path: str):
        written = 0
        with self._open(url, timeout=120) as res, open(path + '.part', 'wb') as out:
            while True:
                chunk = res.read(1 << 16)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_DOWNLOAD:
                    raise DriveError('파일이 너무 큽니다(500MB 넘음).')
                out.write(chunk)
        os.replace(path + '.part', path)

    def download(self, meta: dict, path: str):
        mime = meta.get('mimeType') or ''
        file_id = urllib.parse.quote(meta['id'])
        if mime in EXPORTS:
            self._save(f'{API}/files/{file_id}/export?' + urllib.parse.urlencode({'mimeType': EXPORTS[mime][0]}), path)
        elif mime.startswith('application/vnd.google-apps.'):
            raise DriveError('이 형식(구글 설문·사이트 등)은 교실 기기에서 열 수 없습니다.')
        elif int(meta.get('size') or 0) > MAX_DOWNLOAD:
            raise DriveError('파일이 너무 큽니다(500MB 넘음).')
        else:
            self._save(f'{API}/files/{file_id}?alt=media&supportsAllDrives=true', path)

    # 올리기 ------------------------------------------------------------------
    def _resumable(self, url: str, method: str, metadata: dict, path: str) -> dict:
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        size = os.path.getsize(path)
        with self._open(url, method, json.dumps(metadata).encode('utf-8'), {
                'Content-Type': 'application/json; charset=UTF-8',
                'X-Upload-Content-Type': mime, 'X-Upload-Content-Length': str(size)}) as res:
            location = res.headers.get('Location')
        if not location:
            raise DriveError('드라이브에 올리지 못했습니다.')
        with open(path, 'rb') as f:
            data = f.read()
        with self._open(location, 'PUT', data, {'Content-Type': mime}, timeout=300) as res:
            raw = res.read()
        return json.loads(raw.decode('utf-8')) if raw else {}

    def upload_new(self, path: str, parent: str, name: str | None = None) -> dict:
        meta = {'name': name or os.path.basename(path), 'parents': [parent]}
        return self._resumable(f'{UPLOAD}?uploadType=resumable&supportsAllDrives=true&fields=id,name,mimeType,modifiedTime',
                               'POST', meta, path)

    def update_content(self, file_id: str, path: str) -> dict:
        return self._resumable(
            f'{UPLOAD}/{urllib.parse.quote(file_id)}?uploadType=resumable&supportsAllDrives=true&fields=id,name,modifiedTime',
            'PATCH', {}, path)

    def create_folder(self, name: str, parent: str) -> dict:
        return self._json(f'{API}/files?supportsAllDrives=true&fields=id,name,mimeType',
                          'POST', {'name': name, 'mimeType': FOLDER, 'parents': [parent]})

    def find_or_create_folder(self, name: str, parent: str = 'root') -> str:
        q = urllib.parse.urlencode({'q': f"name = '{_q(name)}' and mimeType = '{FOLDER}' and '{parent}' in parents and trashed = false",
                                    'fields': 'files(id)', 'pageSize': 1})
        found = self._json(f'{API}/files?{q}').get('files') or []
        return found[0]['id'] if found else self.create_folder(name, parent)['id']


def unique_path(folder: str, name: str) -> str:
    path = os.path.join(folder, name)
    root, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path) or os.path.exists(path + '.part'):
        path = f'{root} ({n}){ext}'
        n += 1
    return path


def _stamp(path: str):
    try:
        st = os.stat(path)
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


class Workspace:
    """이번 수업에 연 드라이브 파일들 — 받아 두고, 저장되면 되올린다.

    token_fn() 은 지금 쓸 수 있는 토큰(없으면 None)을 돌려준다. 다시 연결하면 바뀐다.
    """

    def __init__(self, folder: str, token_fn, opener=urllib.request.urlopen, startfile=None, clock=time.time):
        self.folder = folder
        self.token_fn = token_fn
        self.opener = opener
        self.startfile = startfile or getattr(os, 'startfile', None)
        self.clock = clock
        self.entries: dict[str, dict] = {}       # 로컬 경로 → 기록
        self.lock = threading.RLock()

    def drive(self) -> Drive:
        token = self.token_fn()
        if not token:
            raise DriveError('드라이브가 연결되어 있지 않습니다. QR 로 다시 연결해 주세요.', auth=True)
        return Drive(token, self.opener)

    def open(self, file_id: str) -> str:
        """파일을 받아 연다. 이미 받은 파일이면 그대로 연다(고친 내용을 덮지 않는다)."""
        with self.lock:
            for path, entry in self.entries.items():
                if entry['source_id'] == file_id and os.path.exists(path):
                    self._start(path)
                    return path
        drive = self.drive()
        meta = drive.resolve(drive.meta(file_id))
        if meta.get('mimeType') == FOLDER:
            raise DriveError('폴더입니다.')
        exported = meta.get('mimeType') in EXPORTS
        ext = EXPORTS[meta['mimeType']][1] if exported else ''
        target_dir = os.path.join(self.folder, uuid.uuid4().hex[:8])   # 같은 이름 파일이 겹치지 않게
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, safe_name(meta.get('name', ''), ext))
        drive.download(meta, path)
        with self.lock:
            self.entries[path] = {
                'key': uuid.uuid4().hex[:10], 'source_id': meta['id'], 'name': os.path.basename(path), 'exported': exported,
                'upload_id': None if exported else meta['id'],
                'parent': (meta.get('parents') or ['root'])[0],
                'synced': _stamp(path), 'seen': _stamp(path), 'seen_at': self.clock(),
                'state': 'synced', 'message': '', 'uploaded_at': None,
            }
        self._start(path)
        return path

    def _start(self, path: str):
        if not self.startfile:
            raise DriveError('이 기기에서 파일을 열 수 없습니다.')
        self.startfile(path)

    def sync(self, final: bool = False) -> int:
        """바뀐 파일을 올린다. final=True 면 기다리지 않고 지금 상태로 올린다. 올린 개수를 돌려준다."""
        sent = 0
        with self.lock:
            paths = list(self.entries)
        for path in paths:
            entry = self.entries[path]
            now_stamp = _stamp(path)
            if now_stamp is None or now_stamp == entry['synced']:
                continue
            if now_stamp != entry['seen']:
                entry['seen'], entry['seen_at'] = now_stamp, self.clock()
                if not final:
                    entry['state'] = 'pending'
                    continue
            if not final and self.clock() - entry['seen_at'] < SETTLE:
                continue
            try:
                entry['state'] = 'uploading'
                drive = self.drive()
                if entry['upload_id']:
                    drive.update_content(entry['upload_id'], path)
                else:
                    root, ext = os.path.splitext(entry['name'])
                    made = drive.upload_new(path, entry['parent'], f'{root} (교실에서 고침){ext}')
                    entry['upload_id'] = made.get('id')
                entry.update(synced=now_stamp, state='synced', message='', uploaded_at=self.clock())
                sent += 1
            except DriveError as e:
                entry.update(state='failed', message=str(e))
            except OSError:
                entry.update(state='pending', message='파일이 아직 쓰이는 중입니다.')   # 프로그램이 잠가 둠
        return sent

    def unsynced(self) -> list[str]:
        with self.lock:
            return [p for p, e in self.entries.items() if _stamp(p) not in (None, e['synced'])]

    def snapshot(self) -> list[dict]:
        with self.lock:
            return [{'key': e['key'], 'source_id': e['source_id'], 'upload_id': e['upload_id'],
                     'exported': e['exported'], 'name': e['name'], 'state': e['state'], 'message': e['message'],
                     'uploaded_at': e['uploaded_at']} for e in self.entries.values()]

    def local_copy(self, file_id: str) -> str | None:
        """이 수업에서 연 파일이면 그 로컬본(교실에서 고친 최신본) 경로"""
        with self.lock:
            for path, entry in self.entries.items():
                if file_id in (entry['source_id'], entry['upload_id']) and os.path.exists(path):
                    return path
        return None

    def keep(self, key: str, dest_dir: str) -> str:
        """열어 둔 파일 하나를 선생님이 고른 폴더에 남긴다(수업이 끝나도 지우지 않는다)"""
        with self.lock:
            found = next(((p, e) for p, e in self.entries.items() if e['key'] == key), None)
        if not found or not os.path.exists(found[0]):
            raise DriveError('열어 둔 파일을 찾지 못했습니다.')
        target = unique_path(dest_dir, found[1]['name'])
        shutil.copy2(found[0], target)
        return target

    def copy_to_pc(self, items: list[dict], dest_dir: str, progress=None) -> dict:
        """고른 드라이브 항목(파일·폴더)을 이 PC 의 dest_dir 로 받는다.

        items: [{id, name, mimeType}] — 탐색기 목록에 있던 그대로. 폴더는 안까지(깊이·개수 상한).
        progress(done, total, name) 를 부른다. → {'copied': n, 'errors': [이름: 이유…], 'truncated': bool, 'paths': [고른 것의 자리]}
        """
        drive = self.drive()
        jobs: list[tuple[dict, str, bool]] = []    # (메타, 넣을 폴더, 고른 것 바로인가)
        tops: list[str] = []                       # 고른 것이 놓인 자리 — «이 PC 에 복사한 파일» 목록에(PcShelf)
        truncated = False

        def plan(item: dict, into: str, depth: int):
            nonlocal truncated
            if len(jobs) >= MAX_COPY_FILES:
                truncated = True
                return
            meta = drive.resolve(item) if item.get('mimeType') == SHORTCUT else item
            if meta.get('mimeType') == FOLDER:
                if depth >= MAX_COPY_DEPTH:
                    truncated = True
                    return
                sub_dir = unique_path(into, safe_name(meta.get('name', '폴더'))) if depth == 0 else                     os.path.join(into, safe_name(meta.get('name', '폴더')))
                os.makedirs(sub_dir, exist_ok=True)
                if depth == 0:
                    tops.append(sub_dir)
                for child in drive.list(meta['id']):
                    plan(child, sub_dir, depth + 1)
            else:
                jobs.append((meta, into, depth == 0))

        for item in items:
            plan(item, dest_dir, 0)
        errors, copied = [], 0
        for done, (meta, into, top) in enumerate(jobs):
            name = meta.get('name', '')
            if progress:
                progress(done, len(jobs), name)
            try:
                mime = meta.get('mimeType') or ''
                ext = EXPORTS[mime][1] if mime in EXPORTS else ''
                local = self.local_copy(meta['id'])
                if local:                                   # 교실에서 연(고친) 파일 — 그 최신본을
                    target = unique_path(into, os.path.basename(local))
                    shutil.copy2(local, target)
                else:
                    target = unique_path(into, safe_name(name, ext))
                    drive.download(meta, target)
                copied += 1
                if top:
                    tops.append(target)
            except (DriveError, OSError) as e:
                errors.append(f'{name}: {e}')
        if progress:
            progress(len(jobs), len(jobs), '')
        return {'copied': copied, 'errors': errors, 'truncated': truncated, 'paths': tops}

    def stash_unsent(self, teacher_email: str) -> int:
        """못 올린 파일을 이 PC 에 남긴다 — 같은 선생님이 다음에 연결하면 올린다."""
        paths = self.unsynced()
        if not paths or not teacher_email:
            return 0
        box = os.path.join(UNSENT_DIR, _teacher_key(teacher_email))
        os.makedirs(box, exist_ok=True)
        for path in paths:
            entry = self.entries[path]
            dest = os.path.join(box, uuid.uuid4().hex[:8] + '_' + entry['name'])
            try:
                shutil.copy2(path, dest)
            except OSError:
                pass
        return len(paths)


def _teacher_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()[:24]


def has_unsent(teacher_email: str) -> bool:
    box = os.path.join(UNSENT_DIR, _teacher_key(teacher_email or ''))
    return bool(teacher_email) and os.path.isdir(box) and bool(os.listdir(box))


def send_unsent(drive: Drive, teacher_email: str) -> int:
    """지난 수업에 못 올린 파일을 «교실에서 올리지 못한 파일» 폴더로 올리고 이 PC 에서 지운다."""
    box = os.path.join(UNSENT_DIR, _teacher_key(teacher_email or ''))
    if not os.path.isdir(box):
        return 0
    names = sorted(os.listdir(box))
    if not names:
        return 0
    folder = drive.find_or_create_folder(UNSENT_FOLDER)
    sent = 0
    for name in names:
        path = os.path.join(box, name)
        drive.upload_new(path, folder, name.split('_', 1)[-1])
        os.remove(path)
        sent += 1
    shutil.rmtree(box, ignore_errors=True)
    return sent


# 이 PC 에 복사한 파일 -----------------------------------------------------------
# «컴퓨터로 복사»·«이 PC 에 저장» 한 것을 선생님별로 기억해 두고, 다음 수업에 드라이브 창 왼쪽 «이 PC 에 복사한 파일»
# 에서 바로 연다(2026-10-15 요청 — 바탕 화면 어디에 받았는지 찾기 어려웠다). 파일은 선생님이 고른 자리에 그대로 있고
# 여기엔 경로만 남긴다. 지워졌거나 옮긴 것은 목록에서 저절로 빠진다. 드라이브 연결 없이도 된다.
COPIES_DIR = os.path.join(DATA_DIR, 'copies')
MAX_SHELF = 300
PC_ROOT = 'pc'
_HIDDEN = ('desktop.ini', 'thumbs.db')


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _recycle(path: str):
    """휴지통으로(되살릴 수 있게) — 바로 지우지 않는다"""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', wintypes.LPCWSTR),
                    ('pTo', wintypes.LPCWSTR), ('fFlags', ctypes.c_ushort), ('fAnyOperationsAborted', wintypes.BOOL),
                    ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', wintypes.LPCWSTR)]
    # FO_DELETE=3 · FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI. pFrom 은 널 두 개로 끝난다
    op = SHFILEOPSTRUCTW(None, 3, os.path.abspath(path) + '\0', None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
    if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) or op.fAnyOperationsAborted or os.path.exists(path):
        raise OSError('휴지통으로 옮기지 못했습니다(파일이 열려 있으면 닫고 다시 해 주세요).')


class PcShelf:
    """한 선생님이 이 PC 에 복사해 둔 것. 항목 id 는 «pc:<해시>»(복사한 것) · «pc:<해시>/하위/경로»(그 폴더 안)."""

    def __init__(self, email: str, startfile=None, recycle=None, clock=time.time):
        self.email = (email or '').strip().lower()
        self.startfile = startfile or getattr(os, 'startfile', None)
        self.recycle = recycle or _recycle
        self.clock = clock
        self.lock = threading.RLock()

    @property
    def _file(self) -> str:
        return os.path.join(COPIES_DIR, _teacher_key(self.email) + '.json')

    def _load(self) -> dict:
        try:
            with open(self._file, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict):
        os.makedirs(COPIES_DIR, exist_ok=True)
        tmp = self._file + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self._file)

    @staticmethod
    def _key(path: str) -> str:
        return hashlib.sha256(_norm(path).encode('utf-8')).hexdigest()[:12]

    def add(self, paths, dest: str | None = None):
        """방금 복사한 것(맨 위 파일·폴더)을 기억한다. 최근 것이 앞."""
        if not self.email:
            return
        with self.lock:
            data = self._load()
            fresh = [{'path': os.path.abspath(p), 'at': self.clock()} for p in paths if p]
            keys = {_norm(e['path']) for e in fresh}
            old = [e for e in data.get('items') or []
                   if isinstance(e, dict) and _norm(str(e.get('path') or '')) not in keys]
            data['items'] = (fresh[::-1] + old)[:MAX_SHELF]
            if dest:
                data['last_dest'] = os.path.abspath(dest)
            self._save(data)

    def last_dest(self) -> str | None:
        """지난번에 고른 폴더 — 폴더 고르기 창을 거기서 연다"""
        dest = self._load().get('last_dest') if self.email else None
        return dest if isinstance(dest, str) and os.path.isdir(dest) else None

    def _roots(self) -> list[dict]:
        """남아 있는 것만 — 지워졌거나 옮긴 것은 기록에서 뺀다"""
        if not self.email:
            return []
        with self.lock:
            data = self._load()
            items = [e for e in data.get('items') or [] if isinstance(e, dict) and isinstance(e.get('path'), str)]
            alive = [e for e in items if os.path.exists(e['path'])]
            if len(alive) != len(items):
                data['items'] = alive
                try:
                    self._save(data)
                except OSError:
                    pass
            return alive

    @staticmethod
    def _describe(item_id: str, path: str, when: float | None = None) -> dict:
        folder = os.path.isdir(path)
        try:
            st = os.stat(path)
        except OSError:
            st = None
        stamp = when if when is not None else (st.st_mtime if st else None)
        return {'id': item_id, 'name': os.path.basename(path.rstrip('\\/')) or path, 'place': path,
                'mimeType': FOLDER if folder else (mimetypes.guess_type(path)[0] or ''),
                'size': '' if folder or not st else str(st.st_size),
                'modifiedTime': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(stamp)) if stamp else ''}

    def count(self) -> int:
        return len(self._roots())

    def resolve(self, item_id: str) -> str:
        """id → 실제 경로. 기억해 둔 것과 그 안만 — 밖으로 나가는 경로(..)는 막는다."""
        head, _, rel = str(item_id or '').partition('/')
        key = head[len(PC_ROOT) + 1:] if head.startswith(PC_ROOT + ':') else ''
        root = next((e['path'] for e in self._roots() if self._key(e['path']) == key), None) if key else None
        if root is None:
            raise DriveError('이 PC 에서 찾지 못했습니다(지웠거나 옮긴 것 같습니다).')
        if not rel:
            return root
        target = os.path.abspath(os.path.join(root, *rel.split('/')))
        if os.path.commonpath([_norm(root), _norm(target)]) != _norm(root) or not os.path.exists(target):
            raise DriveError('이 PC 에서 찾지 못했습니다(지웠거나 옮긴 것 같습니다).')
        return target

    def list(self, item_id: str = PC_ROOT) -> list[dict]:
        if item_id in (None, '', PC_ROOT):
            return [self._describe(f"{PC_ROOT}:{self._key(e['path'])}", e['path'], e.get('at')) for e in self._roots()]
        folder = self.resolve(item_id)
        if not os.path.isdir(folder):
            raise DriveError('폴더가 아닙니다.')
        try:
            names = os.listdir(folder)
        except OSError:
            raise DriveError('폴더를 읽지 못했습니다.') from None
        names = [n for n in names if not n.startswith('~$') and n.lower() not in _HIDDEN]   # 오피스 잠금 파일 등
        names.sort(key=lambda n: (not os.path.isdir(os.path.join(folder, n)), n.casefold()))
        return [self._describe(f'{item_id}/{n}', os.path.join(folder, n)) for n in names[:2000]]

    def open(self, item_id: str) -> str:
        path = self.resolve(item_id)
        if os.path.isdir(path):
            raise DriveError('폴더입니다.')
        if not self.startfile:
            raise DriveError('이 기기에서 파일을 열 수 없습니다.')
        self.startfile(path)
        return path

    def forget(self, item_ids) -> int:
        """목록에서만 뺀다(파일은 그대로) — 복사한 것(맨 위) 단위"""
        keys = {str(i)[len(PC_ROOT) + 1:] for i in item_ids or [] if str(i).startswith(PC_ROOT + ':') and '/' not in str(i)}
        with self.lock:
            data = self._load()
            items = data.get('items') or []
            data['items'] = [e for e in items if not (isinstance(e, dict) and self._key(str(e.get('path') or '')) in keys)]
            if len(data['items']) != len(items):
                self._save(data)
            return len(items) - len(data['items'])

    def trash(self, item_ids) -> dict:
        """휴지통으로 옮긴다 → {'removed': n, 'errors': [...]}"""
        removed, errors = 0, []
        for item_id in item_ids or []:
            try:
                path = self.resolve(item_id)
                self.recycle(path)
                removed += 1
            except (DriveError, OSError) as e:
                errors.append(f"{str(item_id).rsplit('/', 1)[-1]}: {e}")
        self._roots()
        return {'removed': removed, 'errors': errors}
