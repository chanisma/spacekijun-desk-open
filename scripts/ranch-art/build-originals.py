"""Compile imagegen's six-by-six original character sheets into game atlases.

python scripts/ranch-art/build-originals.py [--species rabbit chick ...]
Generated art is preserved in originals/*-source.png. This compiler only cuts,
normalizes pixel size/palette/alpha and packs frames; it does not draw anatomy.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'app/web/ranch/originals'
DESIGNS = {
    'rabbit': ('달씨앗 토끼', '아기 달씨앗 토끼', [17, 26], '달씨앗 언덕'),
    'chick': ('해콩 닭', '해콩 병아리', [14, 22], '아침 꽃밭'),
    'duckling': ('물방울 오리', '아기 물방울 오리', [15, 24], '물빛 우편 연못'),
    'lamb': ('구름솜 양', '아기 구름솜 양', [17, 25], '구름 낮잠 들판'),
    'kitten': ('책갈피 고양이', '아기 책갈피 고양이', [18, 27], '별빛 도서관 정원'),
    'puppy': ('도토리 강아지', '아기 도토리 강아지', [18, 27], '도토리 문지기 숲'),
    'fox': ('노을꼬리 여우', '아기 노을꼬리 여우', [18, 27], '노을 잎새 숲'),
    'alpaca': ('별구름 알파카', '아기 별구름 알파카', [22, 34], '별구름 고원'),
}
# 시설(35px 그림을 논리 높이 20~22칸에 표시)과 비슷한 픽셀 밀도.
# 화면 몸 크기와 저장 해상도를 분리해 축소 과정의 눈/귀 디테일 손실을 줄인다.
PIXEL_RATIO = 2
CELL, BASE = 48 * PIXEL_RATIO, 44 * PIXEL_RATIO


def bands(values, gap):
    runs = []
    for n in np.flatnonzero(values):
        n = int(n)
        if not runs or n - runs[-1][1] > gap:
            runs.append([n, n + 1])
        else:
            runs[-1][1] = n + 1
    return runs


def split_sheet(path):
    image = Image.open(path).convert('RGBA')
    rgba = np.asarray(image)
    mask = rgba[:, :, 3] >= 160
    rows = bands(mask.sum(1) > max(15, image.width * .015), max(4, image.height // 160))
    if len(rows) != 6:
        raise ValueError(f'{path.name}: expected 6 separated rows, found {rows}')
    frames, boxes = [], []
    for y0, y1 in rows:
        cols = bands(mask[y0:y1].sum(0) > 3, max(4, image.width // 160))
        if len(cols) != 6:
            raise ValueError(f'{path.name}: row {y0} expected 6 sprites, found {cols}')
        for x0, x1 in cols:
            tile = rgba[y0:y1, x0:x1].copy()
            tile[:, :, 3] = np.where(tile[:, :, 3] >= 160, 255, 0)
            frame = Image.fromarray(tile)
            box = frame.getbbox()
            frames.append(frame.crop(box))
            boxes.append([x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]])
    # Use the same compact palette for adult and baby; transparent RGB never enters it.
    colors = rgba[mask, :3].reshape(1, -1, 3)
    palette = Image.fromarray(colors).quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    return frames, palette, boxes


def clip(frames, duration):
    return {'frames': frames, 'times': [round(i * duration / len(frames), 4) for i in range(len(frames))],
            'duration': duration}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--species', nargs='+', choices=list(DESIGNS), default=list(DESIGNS))
    selected = parser.parse_args().species
    sheets, report, designs = {}, {}, {}
    for species in selected:
        source = OUT / f'{species}-v2-source.png'
        frames, palette, boxes = split_sheet(source)
        name, baby, heights, origin = DESIGNS[species]
        designs[species] = {'name': name, 'baby': baby, 'origin': origin, 'size': heights}
        report[species] = {'source': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                           'source_boxes': boxes, 'stages': {}}
        for stage, start, height in [('adult', 0, heights[1]), ('baby', 18, heights[0])]:
            group = frames[start:start + 18]
            scale = height * PIXEL_RATIO / group[0].height
            board = Image.new('RGBA', (CELL * 6, CELL * 3))
            bounds = []
            for i, frame in enumerate(group):
                size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
                if max(size) > CELL - 4:
                    raise ValueError(f'{species}/{stage}/{i}: sprite exceeds cell: {size}')
                tile = frame.resize(size, Image.Resampling.NEAREST)
                alpha = tile.getchannel('A')
                tile = tile.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE).convert('RGBA')
                tile.putalpha(alpha)
                x, y = (CELL - tile.width) // 2, BASE - tile.height
                board.alpha_composite(tile, (i % 6 * CELL + x, i // 6 * CELL + y))
                bounds.append([x, y, x + tile.width, BASE])
            filename = f'{species}_{stage}.webp'
            board.save(OUT / filename, lossless=True, method=6)
            metadata = {'src': f'ranch/originals/{filename}', 'native': True, 'original': True,
                'cell': [CELL, CELL], 'columns': 6, 'frames': 18, 'anchor': [CELL // 2, BASE],
                'bounds': bounds, 'flip': species == 'kitten',
                # 원화의 방향 예외는 렌더러가 보정한다. 원본 PNG는 그대로 보관한다.
                'frameFlip': [12, 13, 14, 15] if species == 'rabbit' else [],
                'artVersion': 2, 'pixelRatio': PIXEL_RATIO,
                'clips': {'idle_0': clip([0, 0, 0, 1, 0], 2.4),
                          'move': clip([2, 3, 4, 5], {'rabbit': .48, 'chick': .48, 'duckling': .64, 'lamb': .72, 'kitten': .56, 'puppy': .56, 'fox': .6, 'alpaca': .8}[species]),
                          'eat': clip([6, 7, 7, 8, 7, 8, 9], 1.8), 'interact_0': clip([10, 10, 11, 11, 10, 11, 11, 0], 1.6),
                          'sleep_loop': clip([12, 13, 14, 15], 2.4), 'idle_1_loop': clip([16, 17], 1.6)}}
            key = f'{species}_{stage}'
            for quality in range(5):
                sheets[key + (f'_t{quality}' if quality else '')] = metadata
            report[species]['stages'][stage] = {'sheet': filename, 'body_height': height,
                'texture_body_height': height * PIXEL_RATIO, 'pixel_ratio': PIXEL_RATIO,
                'palette_colors': 64, 'frames': 18}
        print(f'{species}: 36 frames, adult {heights[1]}px / baby {heights[0]}px')
    script = '// Generated by scripts/ranch-art/build-originals.py — original art, imagegen.\n'
    script += 'Object.assign(window.RANCH_ATLAS.sheets, ' + json.dumps(sheets, separators=(',', ':')) + ');\n'
    script += 'for (const [id, design] of Object.entries(' + json.dumps(designs, ensure_ascii=False) + ')) {\n'
    script += '  Object.assign(window.RANCH_DATA.SPECIES.find(s => s.id === id), design);\n'
    script += '  delete window.RANCH_ATLAS.sheets[`${id}_adult_walk`]; delete window.RANCH_ATLAS.sheets[`${id}_baby_walk`];\n}\n'
    (OUT / 'atlas.js').write_text(script, encoding='utf-8')
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
