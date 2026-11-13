"""별사이 목장 효과 그림(재화·똥·파리·청소) — 직접 그린 픽셀 그림을 만든다 (2026-11-11).

python scripts/ranch-art/build-effects.py

참고 게임에서 뽑은 효과 그림(ranch/tinypasture/, 이 PC 시험용 · 배포 금지)을 대신한다. 시트 이름·칸 크기·프레임 수는
ranch.js 가 기대하는 것과 같다(fx_<이름>, 가로 한 줄). 그림은 이 스크립트가 도형으로 직접 찍는다 — 원본을 읽지 않는다.
나오는 것: app/web/ranch/effects/*.webp (무손실) · atlas.js
"""
from __future__ import annotations

import colorsys
import json
import math
import random
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'app' / 'web' / 'ranch' / 'effects'


def rgba(hex_color: str, alpha: int = 255) -> tuple:
    h = hex_color.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


class Sheet:
    def __init__(self, cell: tuple[int, int], frames: int):
        self.cell, self.frames = cell, frames
        self.img = Image.new('RGBA', (cell[0] * frames, cell[1]), (0, 0, 0, 0))

    def put(self, frame: int, x: int, y: int, color: tuple):
        cw, ch = self.cell
        if 0 <= x < cw and 0 <= y < ch:
            self.img.putpixel((frame * cw + x, y), color)

    def bounds(self) -> list[list[int]]:
        cw, ch = self.cell
        out = []
        for f in range(self.frames):
            box = self.img.crop((f * cw, 0, (f + 1) * cw, ch)).getbbox()
            out.append(list(box) if box else [0, 0, cw, ch])
        return out


# ── 동전: 가로 폭이 줄었다 늘어나며 도는 8×8, 5장 ──────────────────────
def coin(light: str, mid: str, dark: str) -> Sheet:
    s = Sheet((8, 8), 5)
    widths = [8, 6, 3, 6, 8]
    for f, w in enumerate(widths):
        half = w / 2
        for y in range(8):
            dy = (y + 0.5 - 4) / 4
            span = half * math.sqrt(max(0.0, 1 - dy * dy))
            for x in range(8):
                dx = x + 0.5 - 4
                if abs(dx) > span + 0.15:
                    continue
                edge = abs(dx) > span - 1.0 or abs(dy) > 0.8
                if edge:
                    color = rgba(dark)
                elif w >= 6 and dx < -0.5 and dy < 0:
                    color = rgba(light)
                else:
                    color = rgba(mid)
                s.put(f, x, y, color)
        if w >= 6:                                   # 가운데 별 무늬
            s.put(f, 4 if f != 3 else 3, 4, rgba(light))
    return s


# ── 보석: 위는 평평한 사다리꼴, 아래는 뾰족한 14×12, 반짝임이 지나가는 5장 ──
def gem(palette) -> Sheet:
    s = Sheet((14, 12), 5)
    for f in range(5):
        light, mid, dark = palette(f)
        for y in range(12):
            if y < 4:                                # 윗면: 위가 좁다
                half = 4 + y * 0.75
            else:                                    # 아랫면: 끝으로 좁아진다
                half = 6.9 * (11.5 - y) / 7.5
            for x in range(14):
                dx = x + 0.5 - 7
                if abs(dx) > half:
                    continue
                if abs(dx) > half - 1 or y == 0 or y == 11:
                    color = rgba(dark)
                elif y == 3 or (y < 3 and dx < 0):
                    color = rgba(light)
                else:
                    color = rgba(mid)
                s.put(f, x, y, color)
        shine = 3 + f * 2                            # 대각선 반짝임
        for k in range(3):
            s.put(f, shine + k, 2 + k, (255, 255, 255, 230))
    return s


def tone(hex_light, hex_mid, hex_dark):
    return lambda _f: (hex_light, hex_mid, hex_dark)


def rainbow(f):
    hue = f / 5
    out = []
    for light, sat in ((0.85, 0.35), (0.62, 0.75), (0.38, 0.8)):
        r, g, b = colorsys.hls_to_rgb(hue, light, sat)
        out.append('#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255)))
    return tuple(out)


# ── 똥: 둥근 단을 쌓은 더미 ───────────────────────────────────────
POOP = ('#a8774a', '#7a5233', '#4e321e')


def pile(cell, tiers) -> Sheet:
    s = Sheet(cell, 1)
    cw, ch = cell
    for (cy, half, height) in tiers:                 # 아래 단부터
        for y in range(cy - height, cy):
            dy = (y + 0.5 - (cy - height / 2)) / (height / 2)
            span = half * math.sqrt(max(0.0, 1 - dy * dy * 0.6))
            for x in range(cw):
                dx = x + 0.5 - cw / 2
                if abs(dx) > span:
                    continue
                edge = abs(dx) > span - 1 or y == cy - height
                color = POOP[2] if edge else (POOP[0] if dx < -1 and dy < 0 else POOP[1])
                s.put(0, x, y, rgba(color))
    top = tiers[-1]
    s.put(0, cw // 2, top[0] - top[2] - 1, rgba(POOP[2]))   # 꼭지
    return s


# ── 파리: 두 마리가 맴도는 14×12, 7장 ────────────────────────────
def flies() -> Sheet:
    s = Sheet((14, 12), 7)
    body, wing = rgba('#2b2b33'), (220, 235, 255, 200)
    for f in range(7):
        for k, phase in enumerate((0.0, math.pi)):
            a = f / 7 * 2 * math.pi + phase
            x = round(7 + math.cos(a) * 4.5)
            y = round(6 + math.sin(a * 2) * 3.5 + (k - 0.5))
            s.put(f, x, y, body)
            s.put(f, x + 1, y, body)
            up = (f + k) % 2 == 0
            s.put(f, x, y - 1 if up else y + 1, wing)
            s.put(f, x + 1, y - 1 if up else y + 1, wing)
    return s


# ── 청소: 더미가 납작해지고 먼지 구름이 퍼졌다 반짝임으로 사라지는 64×50, 12장 ──
def clean_puff() -> Sheet:
    s = Sheet((64, 50), 12)
    rng = random.Random(1111)
    puffs = [(rng.uniform(-1, 1), rng.uniform(-1, 0.2), rng.uniform(0.6, 1.0)) for _ in range(9)]
    sparks = [(rng.uniform(-1, 1), rng.uniform(-1, -0.2)) for _ in range(6)]
    base_x, base_y = 32, 34
    for f in range(12):
        if f < 5:                                    # 더미가 눌린다
            squash = 1 - f * 0.17
            for y in range(int(6 * squash) + 1):
                half = 5 - y * 0.6 / max(squash, 0.2)
                for x in range(64):
                    dx = x + 0.5 - base_x
                    if abs(dx) <= half:
                        s.put(f, x, base_y - y, rgba(POOP[1] if abs(dx) < half - 1 else POOP[2]))
        grow = min(1.0, (f + 1) / 7)                 # 구름이 퍼진다
        fade = 1.0 if f < 8 else max(0.0, 1 - (f - 7) / 4)
        for px, py, r in puffs:
            cx = base_x + px * 18 * grow
            cy = base_y - 6 + py * 12 * grow
            radius = r * (2 + 6 * grow) * (0.6 + 0.4 * fade)
            if fade <= 0 or radius < 1:
                continue
            for y in range(int(cy - radius) - 1, int(cy + radius) + 2):
                for x in range(int(cx - radius) - 1, int(cx + radius) + 2):
                    d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                    if d > radius:
                        continue
                    shade = '#f3e9d8' if d < radius - 1.2 else '#cdbba0'
                    s.put(f, x, y, rgba(shade, int(235 * fade)))
        if f >= 4:                                   # 반짝임
            t = (f - 4) / 7
            for sx, sy in sparks:
                cx = round(base_x + sx * 20)
                cy = round(base_y - 8 + sy * 14 - t * 6)
                arm = 2 if f % 2 == 0 else 1
                alpha = int(255 * (1 - t * 0.8))
                for k in range(-arm, arm + 1):
                    s.put(f, cx + k, cy, (255, 246, 190, alpha))
                    s.put(f, cx, cy + k, (255, 246, 190, alpha))
    return s


SHEETS = {
    'coin_copper_ani': (lambda: coin('#f2b57a', '#c9773f', '#7a4220'), 8),
    'coin_gold_ani': (lambda: coin('#fff1a0', '#f2c230', '#9a6a10'), 8),
    'diamond_blue_ani': (lambda: gem(tone('#c8ecff', '#5fb8f0', '#1f5f9e')), 12),
    'diamond_yellow_ani': (lambda: gem(tone('#fff6c0', '#f5cf3d', '#a57a0e')), 12),
    'diamond_rainbow_ani': (lambda: gem(rainbow), 12),
    'shit_small': (lambda: pile((16, 10), [(10, 6.5, 4), (6, 4.5, 3), (3, 2.5, 2)]), 10),
    'shit_big': (lambda: pile((19, 13), [(13, 8.5, 5), (8, 6.0, 4), (4, 3.5, 3)]), 13),
    'shit_flies': (flies, 12),
    'fx_poop': (clean_puff, 35),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    atlas = {}
    for name, (make, anchor_y) in SHEETS.items():
        sheet = make()
        path = OUT / f'{name}.webp'
        sheet.img.save(path, 'WEBP', lossless=True)
        atlas[f'fx_{name}'] = {'src': f'ranch/effects/{name}.webp', 'cell': list(sheet.cell), 'frames': sheet.frames,
                               'bounds': sheet.bounds(), 'anchorY': anchor_y, 'original': True}
        print(f'  {path.relative_to(ROOT)}  {sheet.img.size}')
    text = ('// Generated by scripts/ranch-art/build-effects.py — 직접 그린 효과 그림(재화·똥·파리·청소).\n'
            'Object.assign(window.RANCH_ATLAS.sheets,' + json.dumps(atlas, ensure_ascii=False, separators=(',', ':')) + ');\n')
    (OUT / 'atlas.js').write_text(text, encoding='utf-8', newline='\n')
    print(f'  atlas.js : 시트 {len(atlas)}개')


if __name__ == '__main__':
    main()
