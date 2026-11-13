"""별사이 목장 그림 — codex 원화(.tmp_ranch/<이름>-raw.png) → 진짜 픽셀 스프라이트 → app/web/ranch/sprites/.

  python scripts/ranch-art/build.py

· 동물(자세 다섯: 가만히·기쁨·먹기·잠·시무룩)은 다마고찌의 process.py(spacekijun scripts/tamagotchi-codex)로 격자를 맞춰 줄이고,
  칸 크기를 맞춘 시트 한 장(<이름>.png, 가로 다섯 칸, 아래 정렬)으로 만든다 — 다마고찌 캐릭터 시트와 같은 모양.
· 다마고찌 캐릭터(둘기·달의 정령·검은 고양이)는 spacekijun public/images/tamagotchi/gacha/char_*.png 를 그대로 쓴다.
· 소품(items1·items2)은 items.png 한 장에 모으고, 방문자(visitors)는 한 칸짜리 시트로.
· atlas.json = {sheets: {이름: {cell: [w, h], frames: n}}, items: {이름: [x, y, w, h]}} — ranch.js 가 읽는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / '.tmp_ranch'
OUT = ROOT / 'app' / 'web' / 'ranch' / 'sprites'
SPACEKIJUN = Path(os.environ.get('SPACEKIJUN_REPO') or ROOT.parent / 'spacekijun')
PROCESS = SPACEKIJUN / 'scripts' / 'tamagotchi-codex' / 'process.py'
GACHA = SPACEKIJUN / 'public' / 'images' / 'tamagotchi' / 'gacha'

ANIMALS = ['rabbit', 'chick', 'fox', 'alpaca', 'kitten', 'puppy', 'lamb', 'duckling']
POSES = ['idle', 'happy', 'eat', 'sleep', 'sulk']
TAMA = ['char_scarfpigeon', 'char_moonmoth', 'char_blackcat']
ITEMS = {'items1': ['food', 'shard', 'fence', 'house', 'water', 'feeder'],
         'items2': ['curtain', 'seed', 'lunch', 'egg', 'bottle', 'flowers'],
         'items3': ['poop', 'medicine', 'broom', 'jar', 'pigeonbox', 'pile']}
VISITORS = {'visitors': ['visitor_pigeon', 'visitor_clerk', 'visitor_airship']}


def process(raw: Path, names: list[str], work: Path, extra: list[str]) -> list[Image.Image]:
    prefix = work / raw.stem
    subprocess.run([sys.executable, '-I', str(PROCESS), str(raw), str(prefix), ','.join(names), *extra],
                   check=True, stdout=subprocess.DEVNULL)
    return [Image.open(f'{prefix}-{name}.png').convert('RGBA') for name in names]


BACKDROPS = ['meadow', 'academy', 'drowned', 'isekai']
BG_BLOCK = 6                # 배경 원화의 게임 화소 한 칸 = 6×6 (지시문과 같다)


def backdrop_layers(raw: Path) -> list[Image.Image]:
    """배경 원화 → 층 셋(위에서부터 먼·중간·가까운). 원화를 세로로 셋으로 나눠 칸마다 칠한 줄만 자르고, 마젠타를 지운 뒤
    게임 화소 한 칸(BG_BLOCK)의 가운데를 찍어 줄인다. 아래(바닥선)를 맞춰 쓰므로 위쪽 빈 줄은 잘라 낸다."""
    import numpy as np
    img = np.array(Image.open(raw).convert('RGB')).astype(int)
    magenta = (abs(img[..., 0] - 255) + img[..., 1] + abs(img[..., 2] - 255)) < 140
    fringe = (img[..., 1] < 70) & (img[..., 0] > 170) & (img[..., 2] > 170)
    fg = ~(magenta | fringe)
    height = img.shape[0]
    out = []
    for k in range(3):
        y0, y1 = height * k // 3, height * (k + 1) // 3
        # 칠한 줄(폭의 1% 넘게)이 모인 덩어리 중 가장 큰 것 — 칸 경계의 잡티 줄이 층에 섞이지 않게(2026-11-06 실측: 56칸으로 부풀었다)
        filled = fg[y0:y1].sum(1) > img.shape[1] * 0.01
        runs, start = [], None
        for r, on in enumerate(list(filled) + [False]):
            if on and start is None:
                start = r
            if not on and start is not None:
                if runs and start - runs[-1][1] < 40:                    # 가까운 덩어리(비공정·깃발)는 잇는다
                    runs[-1] = (runs[-1][0], r, runs[-1][2] + int(fg[y0 + start:y0 + r].sum()))
                else:
                    runs.append((start, r, int(fg[y0 + start:y0 + r].sum())))
                start = None
        if not runs:
            raise SystemExit(f'{raw.name}: {k + 1}번째 층이 비었어요 — 다시 그리세요')
        r0, r1, _ = max(runs, key=lambda run: run[2])
        top, bottom = y0 + r0, y0 + r1
        h, w = min(50, (bottom - top) // BG_BLOCK), img.shape[1] // BG_BLOCK     # 띠(그림 52칸)에 들어가게 — 바닥 쪽을 남긴다
        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        px = layer.load()
        for gy in range(h):
            sy = bottom - (h - gy) * BG_BLOCK + BG_BLOCK // 2           # 바닥에서부터 칸을 맞춘다
            for gx in range(w):
                sx = gx * BG_BLOCK + BG_BLOCK // 2
                if fg[sy, sx]:
                    r, g, b = img[sy, sx]
                    px[gx, gy] = (int(r), int(g), int(b), 255)
        out.append(layer)
    return out


def cut_hires(raw: Path, count: int) -> list[Image.Image]:
    """고해상도 원화 → 자세 count 개 (원화 해상도 그대로, 마젠타만 지운다). 2026-11-06 — 격자로 줄이면 뭉개진다는 지적."""
    import numpy as np
    rgb = np.array(Image.open(raw).convert('RGB')).astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    bg = ((abs(r - 255) + g + abs(b - 255)) < 150) | ((g < 80) & (r > 160) & (b > 160) & (abs(r - b) < 70))
    alpha = np.where(bg, 0, 255).astype('uint8')
    # 가장자리의 마젠타 번짐 — 배경과 닿은 칸은 분홍기를 빼 준다
    edge = (~bg) & (np.roll(bg, 1, 0) | np.roll(bg, -1, 0) | np.roll(bg, 1, 1) | np.roll(bg, -1, 1))
    tinted = edge & (r > g + 60) & (b > g + 60)
    rgb[tinted] = np.stack([g[tinted] + 30, g[tinted] + 20, g[tinted] + 30], -1).clip(0, 255)
    rgba = np.dstack([rgb.clip(0, 255).astype('uint8'), alpha])
    cols = (alpha > 0).sum(0) > 2
    spans, start = [], None
    for x, on in enumerate(list(cols) + [False]):
        if on and start is None:
            start = x
        if not on and start is not None:
            if x - start > 20:
                spans.append((start, x))
            start = None
    if len(spans) != count:
        w = rgba.shape[1] / count
        spans = [(int(i * w), int((i + 1) * w)) for i in range(count)]
    out = []
    for x0, x1 in spans:
        im = Image.fromarray(rgba[:, x0:x1], 'RGBA')
        out.append(im.crop(im.getbbox()))
    return out


def sheet(frames: list[Image.Image]) -> Image.Image:
    w, h = max(f.width for f in frames), max(f.height for f in frames)
    out = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        out.paste(f, (i * w + (w - f.width) // 2, h - f.height), f)
    return out


def main() -> int:
    if not PROCESS.is_file():
        sys.exit(f'다마고찌 process.py 가 없습니다: {PROCESS} (SPACEKIJUN_REPO 로 위치 지정)')
    OUT.mkdir(parents=True, exist_ok=True)
    atlas = {'sheets': {}, 'items': {}}
    missing = []
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        # 동물 2판(2026-11-06) — 다마고찌 화풍보다 세밀한 픽셀(원화 한 칸 = 3×3), 옆모습, 어른(a_)·아기(b_) 따로.
        # 격자는 process.py 가 원화에서 찾는다(--height 를 주지 않는다 — 줄이면 화질이 뭉개진다, 2026-11-06 사용자 지적)
        for name in ANIMALS:
            for stage, tag in (('a', 'adult'), ('b', 'baby')):
                raw = RAW / f'{stage}_{name}-raw.png'
                if not raw.is_file():
                    missing.append(f'{stage}_{name}')
                    continue
                frames = cut_hires(raw, len(POSES))
                k = (160 if stage == 'a' else 120) / frames[0].height     # 미리 부드럽게 줄여 둔다 — 크기 6 에서도 모자라지 않게
                frames = [f.resize((max(1, round(f.width * k)), max(1, round(f.height * k))), Image.LANCZOS) for f in frames]
                image = sheet(frames)
                image.save(OUT / f'{name}_{tag}.png')
                atlas['sheets'][f'{name}_{tag}'] = {'cell': [image.width // len(POSES), image.height], 'frames': len(POSES),
                                                   'body': frames[0].height, 'hires': True}
                print(f'{name}_{tag}: {image.size}')
        for name in TAMA:
            src = GACHA / f'{name}.png'
            if not src.is_file():
                missing.append(name)
                continue
            shutil.copyfile(src, OUT / f'{name}.png')
            image = Image.open(src)
            atlas['sheets'][name] = {'cell': [image.width // 5, image.height], 'frames': 5}
            print(f'{name}: {image.size} (다마고찌)')
        for group, names in VISITORS.items():
            raw = RAW / f'{group}-raw.png'
            if not raw.is_file():
                missing.append(group)
                continue
            for name, frame in zip(names, process(raw, names, work, ['--keep-lines=0.25'])):
                frame.save(OUT / f'{name}.png')
                atlas['sheets'][name] = {'cell': [frame.width, frame.height], 'frames': 1}
                print(f'{name}: {frame.size}')
        pieces = []
        for group, names in ITEMS.items():
            raw = RAW / f'{group}-raw.png'
            if not raw.is_file():
                missing.append(group)
                continue
            pieces += list(zip(names, process(raw, names, work, ['--keep-lines=0.25'])))
        if pieces:
            width, height = sum(p.width + 1 for _, p in pieces), max(p.height for _, p in pieces)
            board = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            x = 0
            for name, piece in pieces:
                board.paste(piece, (x, height - piece.height), piece)
                atlas['items'][name] = [x, height - piece.height, piece.width, piece.height]
                x += piece.width + 1
            board.save(OUT / 'items.png')
            print(f'items: {board.size} ({len(pieces)}개)')
    # 동작·외곽선·말풍선 (2026-11-07) — 걷기 6프레임은 서 있는 자세와 같은 키로. 외곽선 = 그림 둘레만 남긴 흰 테두리(품질 색을 화면에서 입힌다)
    from PIL import ImageFilter, ImageChops
    for name in ANIMALS:
        for stage, tag in (('a', 'adult'), ('b', 'baby')):
            raw = RAW / f'w{stage}_{name}-raw.png'
            key = f'{name}_{tag}'
            if key in atlas['sheets'] and raw.is_file():
                frames = cut_hires(raw, 6)
                k = atlas['sheets'][key]['body'] / frames[0].height
                frames = [f.resize((max(1, round(f.width * k)), max(1, round(f.height * k))), Image.LANCZOS) for f in frames]
                image = sheet(frames)
                image.save(OUT / f'{key}_walk.png')
                atlas['sheets'][f'{key}_walk'] = {'cell': [image.width // 6, image.height], 'frames': 6, 'body': frames[0].height, 'hires': True}
                print(f'{key}_walk: {image.size}')
            elif key in atlas['sheets']:
                missing.append(f'w{stage}_{name}')
    for key in [k for k, m in atlas['sheets'].items() if m.get('hires')]:
        image = Image.open(OUT / f'{key}.png').convert('RGBA')
        alpha = image.getchannel('A').point(lambda v: 255 if v > 40 else 0)
        ring = ImageChops.subtract(alpha.filter(ImageFilter.MaxFilter(7)), alpha)
        line = Image.new('RGBA', image.size, (255, 255, 255, 0))
        line.putalpha(ring)
        line.save(OUT / f'{key}_line.png')
        atlas['sheets'][key]['line'] = True
    raw = RAW / 'bubbles-raw.png'
    if raw.is_file():
        icons = cut_hires(raw, 8)
        icons = [f.resize((max(1, round(f.width * 48 / f.height)), 48), Image.LANCZOS) for f in icons]
        image = sheet(icons)
        image.save(OUT / 'bubbles.png')
        atlas['sheets']['bubbles'] = {'cell': [image.width // 8, image.height], 'frames': 8, 'body': 48, 'hires': True,
                                      'names': ['happy', 'dirty', 'findFood', 'full', 'love', 'healthy', 'hungry', 'sick']}
        print(f'bubbles: {image.size}')
    else:
        missing.append('bubbles')
    # 배경 층 (2026-11-06) — 한 장에 위아래로 그린 먼·중간·가까운 층 셋을 잘라 게임 화소로 줄이고, 층을 위아래로 쌓은 한 장으로.
    # profile = 8 화소 칸마다 «바닥에서 몇 화소까지 칠했나»(세 층 중 가장 높은 것) — 창 모양(누를 자리 = 보이는 자리)을 만든다
    atlas['bgs'] = {}
    for bg in BACKDROPS:
        raw = RAW / f'bg_{bg}-raw.png'
        if not raw.is_file():
            missing.append(f'bg_{bg}')
            continue
        layers = backdrop_layers(raw)
        width = min(layer.width for layer in layers)
        layers = [layer.crop((0, 0, width, layer.height)) for layer in layers]
        board = Image.new('RGBA', (width, sum(layer.height for layer in layers)), (0, 0, 0, 0))
        meta, y = [], 0
        for layer in layers:
            board.paste(layer, (0, y))
            meta.append({'y': y, 'w': width, 'h': layer.height})
            y += layer.height
        board.save(OUT / f'bg_{bg}.png')
        step, profile = 8, []
        for x0 in range(0, width, step):
            top = 0
            for layer in layers:
                alpha = layer.getchannel('A').crop((x0, 0, min(width, x0 + step), layer.height))
                rows = [r for r in range(layer.height) if alpha.crop((0, r, alpha.width, r + 1)).getextrema()[1] > 0]
                if rows:
                    top = max(top, layer.height - rows[0])
            profile.append(top)
        # 층 높이가 서로 다르면 가장 높은 층 기준으로 바닥 맞춤(ranch.js 가 바닥에 붙여 그린다)
        atlas['bgs'][bg] = {'layers': meta, 'step': step, 'profile': profile}
        atlas['sheets'][f'bg_{bg}'] = {'cell': [width, board.height], 'frames': 1}
        print(f'bg_{bg}: {width}×{[m["h"] for m in meta]} profile max {max(profile)}')
    # 스크립트로 싣는다 — 데스크 창은 file:// 로 열려 fetch 로는 못 읽는다
    (OUT / 'atlas.js').write_text('// scripts/ranch-art/build.py 가 만든다 — 고치지 말 것\nwindow.RANCH_ATLAS = '
                                  + json.dumps(atlas, ensure_ascii=False) + ';\n', encoding='utf-8')
    (OUT / 'atlas.json').unlink(missing_ok=True)
    if missing:
        print('원화가 없어 건너뜀:', ', '.join(missing), '— bash scripts/ranch-art/generate.sh 로 그린다')
    return 0


if __name__ == '__main__':
    sys.exit(main())
