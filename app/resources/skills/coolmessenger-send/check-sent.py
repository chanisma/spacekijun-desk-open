"""
보낸 쪽지 확인기 — 쿨메신저 로컬 DB(.udb = SQLite)의 tbl_send 를 읽기 전용으로 조회한다.

    python check-sent.py                       # 최근 3건
    python check-sent.py --last 10             # 최근 10건
    python check-sent.py --after 1052          # MessageKey 가 1052 보다 큰 것(= 방금 보낸 것)
    python check-sent.py --contains 홍길동     # 받는이·제목·본문에 포함된 것만
    python check-sent.py --max-key             # 현재 마지막 MessageKey 만 출력 (발송 전 기준점)
    python check-sent.py --body-chars 200      # 본문 앞 200자까지 (기본 80, 0 이면 본문 숨김)

보는 것
  · key        MessageKey — 늘어났는지로 "정말 나갔는지"를 판정한다
  · 받는이     수신자 전원이 들어 있는지
  · 도착       즉시 | 예약 <시각>   ← ScheduledDate. 예약이면 그 시각에 도착한다
  · 본문       MessageText(전문). 숫자·이름이 의도대로 들어갔는지

⚠️ tbl_send.Title 은 앞 약 29자만 저장된다. 제목 전체 일치로 발송 여부를 판정하지 말 것(긴 제목은 항상 불일치).
⚠️ 앱이 켜져 있어도 안전하다 — 원본을 임시 폴더로 복사(WAL 포함)해 read-only 로 연다. 원본은 건드리지 않는다.
⚠️ 본문에는 동료·학생 정보가 들어 있을 수 있다. 확인에 필요한 만큼만 보고, 통째로 다른 곳에 복사하지 말 것.
"""
import argparse
import glob
import os
import shutil
import sqlite3
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):          # 콘솔이 cp949 여도 한글이 안 깨지게
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

LOCAL = os.path.expandvars(r'%LOCALAPPDATA%\CoolMessenger\Memo')


def find_udb(path=None):
    if path:
        return path
    files = glob.glob(os.path.join(LOCAL, '*.udb'))
    if not files:
        sys.exit('.udb 를 찾지 못했습니다: %s (쿨메신저 설치·로그인 확인)' % LOCAL)
    return max(files, key=os.path.getsize)      # 가장 큰 것 = 본인 계정


def open_ro(src):
    tmp = tempfile.mkdtemp(prefix='cmsent_')
    dst = os.path.join(tmp, 'm.udb')
    shutil.copy(src, dst)
    for ext in ('-wal', '-shm'):
        if os.path.exists(src + ext):
            shutil.copy(src + ext, dst + ext)
    return sqlite3.connect('file:%s?mode=ro' % dst.replace(os.sep, '/'), uri=True), tmp


def squeeze(s, n):
    s = ' '.join((s or '').split())
    return s[:n] + ('…' if len(s) > n else '')


def main():
    ap = argparse.ArgumentParser(description='보낸 쪽지 확인 (읽기 전용)')
    ap.add_argument('--last', type=int, default=3, help='최근 N건 (기본 3)')
    ap.add_argument('--after', type=int, help='이 MessageKey 보다 큰 것만')
    ap.add_argument('--contains', help='받는이·제목·본문에 이 글자가 든 것만')
    ap.add_argument('--max-key', action='store_true', help='마지막 MessageKey 만 출력')
    ap.add_argument('--body-chars', type=int, default=80, help='본문 미리보기 글자 수 (0=숨김)')
    ap.add_argument('--udb', help='.udb 경로 직접 지정')
    a = ap.parse_args()

    con, tmp = open_ro(find_udb(a.udb))
    try:
        if a.max_key:
            r = con.execute('SELECT MAX(MessageKey) FROM tbl_send').fetchone()
            print(r[0] or 0)
            return
        sql = ('SELECT MessageKey, SendDate, ScheduledDate, Receiver, Title, FilePath, MessageText '
               'FROM tbl_send')
        where, args = [], []
        if a.after is not None:
            where.append('MessageKey > ?')
            args.append(a.after)
        if a.contains:
            where.append('(Receiver LIKE ? OR Title LIKE ? OR MessageText LIKE ?)')
            args += ['%' + a.contains + '%'] * 3
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY MessageKey DESC LIMIT ?'
        args.append(a.last if a.after is None else 50)
        rows = list(reversed(con.execute(sql, args).fetchall()))
        if not rows:
            print('(조건에 맞는 보낸 쪽지 없음)')
            return
        for key, sent, sched, to, title, files, text in rows:
            when = ('예약 ' + sched) if sched else '즉시'
            print('key=%s | 발송 %s | 도착 %s' % (key, sent, when))
            print('  받는이: %s' % (to or '').strip())
            print('  제목  : %s' % (title or '').strip())
            print('  첨부  : %s' % (files if files else '(없음)'))
            if a.body_chars > 0:
                print('  본문  : %s' % squeeze(text, a.body_chars))
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
