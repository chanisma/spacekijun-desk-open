"""Pack original imagegen facility animations and three-layer backgrounds.

Source PNGs remain unchanged. Compile with: python scripts/ranch-art/build-environment.py
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'app/web/ranch/environment'


def bands(mask, gap=8):
    runs = []
    for n in np.flatnonzero(mask):
        n = int(n)
        if not runs or n - runs[-1][1] > gap:
            runs.append([n, n + 1])
        else:
            runs[-1][1] = n + 1
    return runs


def source(name):
    path = OUT / f'{name}-source.png'
    im = Image.open(path).convert('RGBA')
    rgba = np.array(im)
    rgba[:, :, 3] = np.where(rgba[:, :, 3] >= 160, 255, 0)
    return Image.fromarray(rgba), {'source': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def palette(im):
    a = np.array(im)
    colors = a[a[:, :, 3] > 0, :3].reshape(1, -1, 3)
    return Image.fromarray(colors).quantize(colors=64, method=Image.Quantize.MEDIANCUT)


def shrink(im, size, pal):
    im = im.resize(size, Image.Resampling.NEAREST)
    a = im.getchannel('A')
    im = im.convert('RGB').quantize(palette=pal, dither=Image.Dither.NONE).convert('RGBA')
    im.putalpha(a)
    return im


def main():
    sheets, bgs, manifest = {}, {}, {}
    for name, height in {'broom': 56, 'feeder': 72, 'jar': 60, 'curtain': 76}.items():
        im, receipt = source(name)
        mask = np.array(im.getchannel('A')) > 0
        rows = bands(mask.sum(1) > max(5, im.width * .005))
        if len(rows) != 2:
            raise ValueError(f'{name}: expected 2 rows, got {rows}')
        frames, boxes = [], []
        for y0, y1 in rows:
            cols = bands(mask[y0:y1].sum(0) > 5)
            if len(cols) != 4:
                raise ValueError(f'{name}: expected 4 columns, got {cols}')
            for x0, x1 in cols:
                tile = im.crop((x0, y0, x1, y1))
                box = tile.getbbox()
                frames.append(tile.crop(box))
                boxes.append([x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]])
        cell, base, scale = 112, 104, height / frames[0].height
        board, bounds, pal = Image.new('RGBA', (cell * 4, cell * 2)), [], palette(im)
        for i, frame in enumerate(frames):
            size = tuple(max(1, round(n * scale)) for n in frame.size)
            if max(size) > cell - 8:
                raise ValueError(f'{name}/{i} exceeds cell: {size}')
            tile = shrink(frame, size, pal)
            x, y = (cell - tile.width) // 2, base - tile.height
            board.alpha_composite(tile, (i % 4 * cell + x, i // 4 * cell + y))
            bounds.append([x, y, x + tile.width, base])
        board.save(OUT / f'{name}.webp', lossless=True, method=6)
        sheets[f'facility_{name}'] = {'src': f'ranch/environment/{name}.webp',
            'facility': True, 'original': True, 'cell': [cell, cell], 'columns': 4,
            'frames': 8, 'anchor': [cell // 2, base], 'bounds': bounds, 'flip': False,
            'pixelRatio': 2, 'bodyHeight': height / 2}
        manifest[name] = {**receipt, 'boxes': boxes, 'frames': 8, 'texture_height': height}
        print(f'{name}: 8 frames, {height}px body')

    for name in ['meadow', 'academy', 'drowned', 'isekai']:
        im, receipt = source(f'bg-{name}')
        mask = np.array(im.getchannel('A')) > 0
        rows = bands(mask.sum(1) > max(5, im.width * .005), gap=12)
        if len(rows) != 3:
            raise ValueError(f'{name}: expected 3 separated layers, got {rows}')
        w, h, pal = 1536, 104, palette(im)
        board = Image.new('RGBA', (w, h * 3))
        layers = []
        union = Image.new('L', (w, h))
        for i, (y0, y1) in enumerate(rows):
            # 원경·중경·전경 높이를 구분해 앞층이 뒤층 전체를 가리지 않게 한다.
            tile = shrink(im.crop((0, y0, im.width, y1)), (w, [96, 68, 24][i]), pal)
            layer = Image.new('RGBA', (w, h))
            layer.alpha_composite(tile, (0, h - tile.height))
            board.alpha_composite(layer, (0, i * h))
            union = Image.fromarray(np.maximum(np.array(union), np.array(layer.getchannel('A'))))
            layer_profile = []
            for x in range(0, w, 8):
                box = layer.getchannel('A').crop((x, 0, min(w, x + 8), h)).getbbox()
                layer_profile.append(h - box[1] if box else 0)
            layers.append({'y': i * h, 'w': w, 'h': h, 'step': 8,
                           'profile': layer_profile, 'overlap': 32, 'phase': [0, .37, .69][i]})
        profile = []
        for x in range(0, w, 8):
            box = union.crop((x, 0, min(w, x + 8), h)).getbbox()
            profile.append(h - box[1] if box else 0)
        board.save(OUT / f'bg-{name}.webp', lossless=True, method=6)
        sheets[f'bg_{name}'] = {'src': f'ranch/environment/bg-{name}.webp',
            'cell': [w, h * 3], 'frames': 1, 'original': True}
        bgs[name] = {'layers': layers, 'step': 8, 'profile': profile, 'original': True}
        manifest[f'bg-{name}'] = {**receipt, 'rows': rows, 'layers': 3, 'size': [w, h]}
        print(f'{name}: 3 layers, {w}x{h}')
    # 전체 물건 시트도 시설과 같은 원화/팔레트 밀도로 다시 만든다.
    im, receipt = source('items')
    mask = np.array(im.getchannel('A')) > 0
    rows = bands(mask.sum(1) > max(5, im.width * .005), gap=8)
    if len(rows) != 4:
        raise ValueError(f'items: expected 4 rows, got {rows}')
    names = ['fence', 'house', 'water', 'flowers', 'food', 'pile', 'medicine', 'bottle',
             'seed', 'lunch', 'egg', 'shard', 'feeder', 'poop', 'foodBag', 'sprout']
    item_frames, boxes = [], []
    for y0, y1 in rows:
        cols = bands(mask[y0:y1].sum(0) > 4, gap=8)
        if len(cols) != 4:
            raise ValueError(f'items: expected 4 columns, got {cols}')
        for x0, x1 in cols:
            tile = im.crop((x0, y0, x1, y1)); box = tile.getbbox()
            item_frames.append(tile.crop(box)); boxes.append([x0+box[0], y0+box[1], x0+box[2], y0+box[3]])
    pal, item_meta = palette(im), {}
    board = Image.new('RGBA', (96*5, 96*4))
    for i, (name, frame) in enumerate(zip(names, item_frames)):
        scale = 72 / max(frame.size)
        tile = shrink(frame, tuple(max(1, round(n*scale)) for n in frame.size), pal)
        x, y = i%5*96+(96-tile.width)//2, i//5*96+88-tile.height
        board.alpha_composite(tile, (x,y)); item_meta[name]=[x,y,tile.width,tile.height]
    # 오래된 저장자료/장식 경로에서도 시설 아이콘이 옛 색으로 돌아가지 않게 한다.
    for i, (icon, kind) in enumerate({'broom':'broom','pigeonbox':'feeder','jar':'jar','curtain':'curtain'}.items(), 16):
        b=sheets[f'facility_{kind}']['bounds'][0]
        frame=Image.open(OUT/f'{kind}.webp').crop(tuple(b))
        scale=min(1,72/max(frame.size));tile=frame.resize(tuple(max(1,round(n*scale)) for n in frame.size),Image.Resampling.NEAREST)
        x,y=i%5*96+(96-tile.width)//2,i//5*96+88-tile.height
        board.alpha_composite(tile,(x,y));item_meta[icon]=[x,y,tile.width,tile.height]
    board.save(OUT/'items.webp',lossless=True,method=6)
    manifest['items']={**receipt,'names':names,'boxes':boxes,'icons':20,'size':list(board.size)}
    aliases = {'tp1': 'meadow', 'tp2': 'academy', 'tp3': 'drowned', 'tp4': 'isekai'}
    js = '// Generated by scripts/ranch-art/build-environment.py — original imagegen artwork.\n'
    js += 'Object.assign(window.RANCH_ATLAS.sheets,' + json.dumps(sheets, separators=(',', ':')) + ');\n'
    js += 'Object.assign(window.RANCH_ATLAS.bgs ||= {},' + json.dumps(bgs, separators=(',', ':')) + ');\n'
    js += 'window.RANCH_ATLAS.bgAliases=' + json.dumps(aliases) + ';\n'
    js += 'window.RANCH_ATLAS.facilityIcons={broom:"broom",pigeonbox:"feeder",jar:"jar",curtain:"curtain"};\n'
    js += 'window.RANCH_ATLAS.items=' + json.dumps(item_meta) + ';\n'
    js += 'window.RANCH_ATLAS.itemsSrc="ranch/environment/items.webp";\n'
    js += 'for(const [old,id] of Object.entries(window.RANCH_ATLAS.bgAliases)){window.RANCH_ATLAS.sheets["bg_"+old]=window.RANCH_ATLAS.sheets["bg_"+id];window.RANCH_ATLAS.bgs[old]=window.RANCH_ATLAS.bgs[id];}\n'
    js += 'window.RANCH_DATA.BACKDROPS.splice(0,window.RANCH_DATA.BACKDROPS.length,...window.RANCH_DATA.BACKDROPS.filter(b=>!window.RANCH_ATLAS.bgAliases[b.id]));\n'
    (OUT / 'atlas.js').write_text(js, encoding='utf8')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
