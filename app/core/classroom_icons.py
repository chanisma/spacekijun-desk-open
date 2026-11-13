"""교실판 독 아이콘 — 실제 아이콘을 쓴다(2026-10-14 사용자 요청).

  · 구글 앱       web/icons/google/<키>.png — 구글 공식 제품 아이콘(gstatic)을 받아 프로그램에 넣어 두었다
  · PC 프로그램    이 PC 에 설치된 실행 파일에서 아이콘을 뽑는다(PowerPoint·한글…). 없으면 글자 타일
  · 웹사이트      그 사이트의 파비콘(구글 파비콘 서비스)
  · 드라이브 항목  구글 드라이브의 파일 형식 아이콘(drive-thirdparty)

뽑거나 받은 그림은 %LOCALAPPDATA%/SpacekijunClassroom/icons 에 PNG 로 두고, 독에는 data URI 로 넘긴다
(독 창이 읽을 수 있는 곳은 app/web 뿐이다). 실패하면 None — 독이 글자 타일로 그린다.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import hashlib
import io
import os
import urllib.parse
import urllib.request

from .classroom_link import DATA_DIR

ICONS_DIR = os.path.join(DATA_DIR, 'icons')
SIZE = 64

_user32 = ctypes.WinDLL('user32')
_gdi32 = ctypes.WinDLL('gdi32')


class _ICONINFO(ctypes.Structure):
    _fields_ = [('fIcon', wt.BOOL), ('xHotspot', wt.DWORD), ('yHotspot', wt.DWORD),
                ('hbmMask', wt.HBITMAP), ('hbmColor', wt.HBITMAP)]


class _BITMAP(ctypes.Structure):
    _fields_ = [('bmType', wt.LONG), ('bmWidth', wt.LONG), ('bmHeight', wt.LONG), ('bmWidthBytes', wt.LONG),
                ('bmPlanes', wt.WORD), ('bmBitsPixel', wt.WORD), ('bmBits', ctypes.c_void_p)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                ('biBitCount', wt.WORD), ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


_user32.PrivateExtractIconsW.argtypes = [wt.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.POINTER(wt.HICON), ctypes.POINTER(wt.UINT), wt.UINT, wt.UINT]
_user32.PrivateExtractIconsW.restype = wt.UINT
_user32.GetIconInfo.argtypes = [wt.HICON, ctypes.POINTER(_ICONINFO)]
_user32.DestroyIcon.argtypes = [wt.HICON]
_user32.GetDC.argtypes = [wt.HWND]
_user32.GetDC.restype = wt.HDC
_user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
_gdi32.GetObjectW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p]
_gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
_gdi32.DeleteObject.argtypes = [wt.HANDLE]


def _bits(hdc, hbm, width, height) -> bytes:
    header = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(width * height * 4)
    _gdi32.GetDIBits(hdc, hbm, 0, height, buf, ctypes.byref(header), 0)
    return buf.raw


def _icon_png(hicon) -> bytes | None:
    from PIL import Image
    info = _ICONINFO()
    if not _user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    hdc = _user32.GetDC(None)
    try:
        if not info.hbmColor:
            return None
        bm = _BITMAP()
        _gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, abs(bm.bmHeight)
        image = Image.frombuffer('RGBA', (w, h), _bits(hdc, info.hbmColor, w, h), 'raw', 'BGRA', 0, 1)
        if image.getchannel('A').getextrema()[1] == 0:        # 옛 아이콘 — 투명도는 마스크에 있다
            mask = Image.frombuffer('RGBA', (w, h), _bits(hdc, info.hbmMask, w, h), 'raw', 'BGRA', 0, 1)
            alpha = mask.convert('L').point(lambda v: 0 if v else 255)
            image = image.copy()
            image.putalpha(alpha)
        out = io.BytesIO()
        image.save(out, 'PNG')
        return out.getvalue()
    finally:
        _user32.ReleaseDC(None, hdc)
        for handle in (info.hbmColor, info.hbmMask):
            if handle:
                _gdi32.DeleteObject(handle)


def exe_icon_png(path: str, size: int = SIZE) -> bytes | None:
    """실행 파일의 첫 아이콘을 size 로 뽑아 PNG"""
    hicon, icon_id = wt.HICON(), wt.UINT()
    if not _user32.PrivateExtractIconsW(path, 0, size, size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0) \
            or not hicon:
        return None
    try:
        return _icon_png(hicon)
    finally:
        _user32.DestroyIcon(hicon)


def _cached(name: str, make) -> str | None:
    """ICONS_DIR/name 이 있으면 그것, 없으면 make() 로 만들어 둔다 → data URI"""
    path = os.path.join(ICONS_DIR, name)
    data = None
    if os.path.exists(path):
        with open(path, 'rb') as f:
            data = f.read()
    else:
        try:
            data = make()
        except Exception:
            data = None
        if data:
            os.makedirs(ICONS_DIR, exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii') if data else None


def _fetch(url: str, opener=urllib.request.urlopen) -> bytes | None:
    from PIL import Image
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 SpacekijunClassroom'})
    with opener(req, timeout=8) as res:
        raw = res.read(512 * 1024)
    image = Image.open(io.BytesIO(raw))                  # 그림이 맞는지 확인하고 PNG 로 통일
    out = io.BytesIO()
    image.convert('RGBA').save(out, 'PNG')
    return out.getvalue()


def program_icon(path: str) -> str | None:
    key = hashlib.sha1(f'{path}|{os.path.getmtime(path) if os.path.exists(path) else 0}'.encode()).hexdigest()[:16]
    return _cached(f'exe-{key}.png', lambda: exe_icon_png(path))


def favicon(url: str, opener=urllib.request.urlopen) -> str | None:
    host = urllib.parse.urlsplit(url).hostname or ''
    if not host:
        return None
    return _cached('site-' + hashlib.sha1(host.encode()).hexdigest()[:16] + '.png',
                   lambda: _fetch('https://www.google.com/s2/favicons?' + urllib.parse.urlencode({'domain': host, 'sz': 64}), opener))


def drive_type_icon(mime: str, opener=urllib.request.urlopen) -> str | None:
    if not mime or '/' not in mime:
        return None
    return _cached('drive-' + hashlib.sha1(mime.encode()).hexdigest()[:16] + '.png',
                   lambda: _fetch('https://drive-thirdparty.googleusercontent.com/64/type/' + mime, opener))
