#!/usr/bin/env python3
"""Build one private Web kit with shared, lazily loaded RysaMix components."""
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont

import final_fonts as final
import rysa_mono as rysa

ROOT = final.ROOT


def ranges(points):
    values = sorted(set(points))
    if not values:
        raise ValueError('Empty Unicode range')
    chunks = []
    start = last = values[0]
    for cp in values[1:]:
        if cp == last + 1:
            last = cp
        else:
            chunks.append(f'U+{start:04X}' if start == last else f'U+{start:04X}-{last:04X}')
            start = last = cp
    chunks.append(f'U+{start:04X}' if start == last else f'U+{start:04X}-{last:04X}')
    return ','.join(chunks)


def static_name(font, family):
    names = font['name']
    for name_id in (1, 2, 3, 4, 5, 6, 8, 10, 16, 17, 25):
        names.removeNames(nameID=name_id)
    values = {1: family, 2: 'Regular', 3: '0.1;LOCAL;' + family,
              4: family + ' Regular', 5: 'Version 0.1', 6: family + '-Regular',
              8: 'FontMod local experiment', 16: family, 17: 'Regular'}
    for platform, encoding, language in [(3, 1, 0x409), (1, 0, 0)]:
        for name_id, value in values.items():
            names.setName(value, name_id, platform, encoding, language)
    font['OS/2'].usWeightClass = 400
    font['OS/2'].fsSelection = (font['OS/2'].fsSelection & ~0x21) | 0x40
    font['head'].macStyle = 0
    font.recalcTimestamp = False


def save_woff(font, path):
    font.flavor = 'woff2'
    font.recalcTimestamp = False
    font.save(path)
    reread = TTFont(path, lazy=True)
    if reread.flavor != 'woff2':
        raise ValueError('Invalid WOFF2: ' + str(path))
    return {'file': 'fonts/' + path.name, 'sha256': final.sha(path), 'bytes': path.stat().st_size}


def base_face(face, config, fonts):
    original = TTFont(rysa.SOURCE_DIR / face['file'], recalcTimestamp=False)
    cell, source_cell = config['spacing']['cell'], config['spacing']['sourceCell']
    for glyph, (advance, lsb) in original['hmtx'].metrics.items():
        if advance not in (0, source_cell, source_cell * 2):
            raise ValueError('Unexpected Rysana source width: ' + glyph)
        if advance:
            original['hmtx'].metrics[glyph] = (cell * (advance // source_cell), lsb)
    rysa.set_names(original, original, 'RysaMixWebBase', face['style'], config['version'])
    for instance in original['fvar'].instances:
        instance.postscriptNameID = 0xffff
    return save_woff(original, fonts / ('Base-' + face['style'] + '.woff2'))


def cjk_face(path, points, family, fonts):
    font = TTFont(path, recalcTimestamp=False)
    if 'sbix' in font:
        del font['sbix']
    options = subset.Options()
    options.layout_features = ['*']
    options.recalc_timestamp = False
    options.glyph_names = True
    worker = subset.Subsetter(options=options)
    worker.populate(unicodes=points)
    worker.subset(font)
    if 'fvar' in font:
        font = instantiateVariableFont(font, {'wght': 400}, inplace=False)
    static_name(font, family)
    result = save_woff(font, fonts / (family + '.woff2'))
    if not points.issubset(TTFont(fonts / (family + '.woff2')).getBestCmap()):
        raise ValueError('Web CJK coverage was lost: ' + family)
    return result


def nerd_face(config, fonts):
    path = final.input_path('sources/geist-mixed/SymbolsNerdFontMono-Regular.ttf')
    font = TTFont(path, recalcTimestamp=False)
    scale_upem(font, 1000)
    for glyph, (advance, lsb) in font['hmtx'].metrics.items():
        if advance:
            font['hmtx'].metrics[glyph] = (config['spacing']['cell'] * config['spacing']['nerdCells'], lsb)
    for tag in ('PfEd', 'vhea', 'vmtx'):
        if tag in font:
            del font[tag]
    final.symbol_aliases(font, config['symbolAliases'])
    static_name(font, 'RysaMixWebNerd')
    return save_woff(font, fonts / 'Nerd.woff2')


def common_cjk(cp):
    han = 0x3400 <= cp <= 0x9fff or 0xf900 <= cp <= 0xfaff or 0x20000 <= cp <= 0x323af
    if not han:
        return True
    for encoding in ('gb2312', 'big5'):
        try:
            chr(cp).encode(encoding)
            return True
        except UnicodeEncodeError:
            pass
    return False


def split_cjk(path, points, name, fonts):
    font = TTFont(path, recalcTimestamp=False)
    options = subset.Options()
    options.layout_features = ['*']
    options.recalc_timestamp = False
    options.glyph_names = True
    worker = subset.Subsetter(options=options)
    worker.populate(unicodes=points)
    worker.subset(font)
    result = save_woff(font, fonts / name)
    if not points.issubset(TTFont(fonts / name).getBestCmap()):
        raise ValueError('Web CJK shard lost coverage: ' + name)
    return result


def face_rule(family, file, style, unicode_points=None):
    value = '@font-face {\n  font-family: ' + json.dumps(family) + ';\n  src: url(' + json.dumps(file) + ') format("woff2");\n  font-style: ' + style + '; font-weight: 100 900; font-display: swap;\n'
    if unicode_points is not None:
        value += '  unicode-range: ' + ranges(unicode_points) + ';\n'
    return value + '}'


def export(source, destination, archive=True):
    source, destination = Path(source).expanduser().resolve(), Path(destination).expanduser().absolute()
    report = rysa.check(source)
    config = report['recipe']
    rysa.checked_inputs(config, source / report['misansInput'])
    if destination.exists() or destination.is_symlink():
        raise ValueError('Choose a new Web bundle directory: ' + str(destination))
    zip_path = destination.with_name(destination.name + '.zip')
    if archive and zip_path.exists():
        raise ValueError('Web bundle ZIP already exists: ' + str(zip_path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.rysa-web-', dir=destination.parent))
    print('Web bundle staging:', stage, flush=True)
    fonts = stage / 'fonts'
    fonts.mkdir()
    emoji_font = TTFont(source / 'Emoji3D-Production.ttf', recalcTimestamp=False)
    emoji_points = set(emoji_font.getBestCmap()) - set(range(128))
    base_source = TTFont(rysa.SOURCE_DIR / config['faces'][0]['file'])
    base_points = set(base_source.getBestCmap())
    if set(TTFont(rysa.SOURCE_DIR / config['faces'][1]['file']).getBestCmap()) != base_points:
        raise ValueError('Rysana regular and italic coverage differs')
    nerd_source = TTFont(final.input_path('sources/geist-mixed/SymbolsNerdFontMono-Regular.ttf'))
    nerd_points = set(nerd_source.getBestCmap()) | {int(k, 16) for k in config['symbolAliases']}
    cubic_points = set(TTFont(final.input_path('sources/Cubic_11.ttf')).getBestCmap())
    mi_points = {cp for cp in TTFont(source / report['misansInput']).getBestCmap()
                 if rysa.is_misans_cjk(cp, config)}
    pixel = next(a for a in report['assets'] if a['cjk'] == 'cubic' and a['style'] == 'Regular')
    mi = next(a for a in report['assets'] if a['cjk'] == 'misans' and a['style'] == 'Regular')
    pixel_cjk = cubic_points - base_points - nerd_points - emoji_points
    mi_cjk = mi_points - emoji_points
    assets = {}
    print('  shared Rysana variable faces', flush=True)
    for face in config['faces']:
        assets['base' + face['style']] = base_face(face, config, fonts)
    print('  shared Nerd and full Emoji3D', flush=True)
    assets['nerd'] = nerd_face(config, fonts)
    assets['emoji'] = save_woff(emoji_font, fonts / 'Emoji3D.woff2')
    print('  Cubic Chinese', flush=True)
    assets['pixelCJK'] = cjk_face(source / pixel['file'], pixel_cjk, 'RysaMixWebPixelCJK', fonts)
    print('  MiSans Chinese', flush=True)
    full_mi = cjk_face(source / mi['file'], mi_cjk, 'RysaMixWebMiCJK', fonts)
    mi_common = {cp for cp in mi_cjk if common_cjk(cp)}
    mi_extra = mi_cjk - mi_common
    full_mi_path = stage / full_mi['file']
    assets['miCJKCommon'] = split_cjk(full_mi_path, mi_common, 'MiCJK-Common.woff2', fonts)
    assets['miCJKExtra'] = split_cjk(full_mi_path, mi_extra, 'MiCJK-Extra.woff2', fonts)
    full_mi_path.unlink()

    families = {item['cjk']: item['name'] for item in config['families']}
    pixel_ranges = ((base_points - emoji_points) | (nerd_points - emoji_points - base_points)
                    | pixel_cjk | emoji_points)
    mi_ranges = ((base_points - emoji_points - mi_points)
                 | (nerd_points - emoji_points - base_points - mi_points)
                 | mi_common | mi_extra | emoji_points)
    # C0 controls are not visible glyphs and are handled by the browser itself.
    for item, available in ((pixel, pixel_ranges), (mi, mi_ranges)):
        native = {cp for cp in TTFont(source / item['file']).getBestCmap() if cp >= 32}
        if not native.issubset(available):
            raise ValueError('Web Unicode ranges lost visible source coverage: ' + item['family'])
    rules = []
    for kind in ('cubic', 'misans'):
        family = families[kind]
        base = base_points - emoji_points - (mi_points if kind == 'misans' else set())
        nerd = nerd_points - emoji_points - base_points - (mi_points if kind == 'misans' else set())
        donors = [(assets['pixelCJK']['file'], pixel_cjk)] if kind == 'cubic' else [
            (assets['miCJKCommon']['file'], mi_common), (assets['miCJKExtra']['file'], mi_extra)]
        for style in ('normal', 'italic'):
            face = assets['baseRegular' if style == 'normal' else 'baseItalic']['file']
            rules += [face_rule(family, face, style, base), face_rule(family, assets['nerd']['file'], style, nerd),
                      face_rule(family, assets['emoji']['file'], style, emoji_points)]
            rules.extend(face_rule(family, file, style, points) for file, points in donors)
    rules.append(face_rule('RysaMixEmojiSequence', assets['emoji']['file'], 'normal'))
    rules += ['.rysamix-pixel { font-family: ' + json.dumps(families['cubic']) + ', ui-monospace, monospace; font-synthesis: none; }',
              '.rysamix-misans { font-family: ' + json.dumps(families['misans']) + ', ui-monospace, monospace; font-synthesis: none; }',
              '.rysamix-emoji { font-family: "RysaMixEmojiSequence", "Apple Color Emoji", sans-serif; font-style: normal; font-weight: 400; }']
    (stage / 'fonts.css').write_text('\n\n'.join(rules) + '\n')
    examples = []
    for kind, cls in [('cubic', 'rysamix-pixel'), ('misans', 'rysamix-misans')]:
        examples.append('<section><h2>' + html.escape(families[kind]) + '</h2>'
                        '<p class="' + cls + '">ABC xyz 0123 · 简体中文 繁體中文 · あいう 한글</p>'
                        '<p class="' + cls + '"><i>Italic 斜體</i> · <span class="nerd">&#xf120; &#xf07b; &#xf121;</span> · '
                        '<span class="rysamix-emoji">😀 👩🏽‍💻 🇹🇼 1️⃣</span></p></section>')
    (stage / 'example.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RysaMix Web</title><link rel="stylesheet" href="fonts.css"><style>body{margin:2rem;font:16px/1.6 system-ui}section{border-top:1px solid #bbb;padding:1rem 0}h2{font-size:16px;overflow-wrap:anywhere}p{font-size:24px;overflow-wrap:anywhere}</style><h1>RysaMix Web</h1>'+''.join(examples)+'</html>')
    shutil.copytree(source / 'licenses', stage / 'licenses')
    shutil.copyfile(source / 'NOTICE.md', stage / 'NOTICE.md')
    examples_text = '<link rel="stylesheet" href="fonts.css">\n<p class="rysamix-pixel">Hello 中文 <span class="rysamix-emoji">👩🏽‍💻 1️⃣</span></p>\n<p class="rysamix-misans">Hello 中文</p>'
    notes = {
        'README.en.md': '# RysaMix Web — private experiment\n\nUse either class, or the named family directly. Normal/italic share CJK, Nerd and Emoji files. MiSans CJK is split into common GB2312/Big5 characters and an additional shard; no supported characters are removed. The browser loads each file only when needed. Use the emoji class for complete sequences such as keycaps. System fallback covers unsupported characters. The full 28 PPEM Emoji3D repertoire uses a 64-color palette. Emoji3D uses sbix; verify rendering in each target browser. MiSans restrictions remain; this kit is private and not for redistribution.\n\n',
        'README.zh-Hant.md': '# RysaMix Web — 本機實驗\n\n使用任一 CSS 類別，或直接指定家族名稱。正常與斜體共用中文、Nerd 和 Emoji 檔案；MiSans 中文拆成常用 GB2312／Big5 字元與其餘字元，沒有刪減原有覆蓋，瀏覽器按需載入。完整 Emoji 序列（如數字鍵帽）請使用 emoji 類別；未支援的字由系統字型補上。Emoji3D 保留完整圖形與 28 PPEM，調色盤為 64 色。Emoji3D 使用 sbix；請在各目標瀏覽器驗證顯示。MiSans 授權限制仍適用，此套件僅供私人實驗，不可再散布。\n\n',
        'README.zh-Hans.md': '# RysaMix Web — 本机实验\n\n使用任一 CSS 类，或直接指定家族名称。正常与斜体共用中文、Nerd 和 Emoji 文件；MiSans 中文拆成常用 GB2312／Big5 字符与其余字符，没有删减原有覆盖，浏览器按需加载。完整 Emoji 序列（如数字键帽）请使用 emoji 类；未支持的字由系统字体补上。Emoji3D 保留完整图形与 28 PPEM，调色板为 64 色。Emoji3D 使用 sbix；请在各目标浏览器验证显示。MiSans 许可限制仍然适用，此套件仅供私人实验，不可再分发。\n\n'}
    for name, text in notes.items():
        (stage / name).write_text(text + '```html\n' + examples_text + '\n```\n')
    manifest = {'schemaVersion': 1, 'distribution': 'private-experiment', 'families': families,
                'assets': assets, 'sourceRecipeSha256': report['recipeSha256'],
                'sourceFonts': [{'file': a['file'], 'sha256': a['sha256']} for a in report['assets']],
                'unicodeCounts': {'emoji': len(emoji_points), 'base': len(base_points),
                                  'nerd': len(nerd_points), 'pixelCJK': len(pixel_cjk),
                                  'miCJKCommon': len(mi_common), 'miCJKExtra': len(mi_extra)},
                'bitmapPolicy': config['emojiRecipe']['pngPolicy'],
                'fontBytes': sum(x['bytes'] for x in assets.values()),
                'files': {str(p.relative_to(stage)): final.sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}}
    final.write(stage / 'bundle.json', manifest)
    for name, digest in manifest['files'].items():
        if final.sha(stage / name) != digest:
            raise ValueError('Web bundle readback failed: ' + name)
    os.rename(stage, destination)
    result = {'directory': str(destination), 'fontBytes': manifest['fontBytes'],
              'assets': assets, 'distribution': 'private-experiment', 'readbackVerified': True}
    if archive:
        with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_STORED) as package:
            for file in sorted(destination.rglob('*')):
                if file.is_file():
                    package.write(file, file.relative_to(destination))
        with zipfile.ZipFile(zip_path) as package:
            expected = manifest['files'] | {'bundle.json': final.sha(destination / 'bundle.json')}
            if set(package.namelist()) != set(expected) or any(hashlib.sha256(package.read(name)).hexdigest() != digest for name, digest in expected.items()):
                raise ValueError('Web bundle ZIP readback failed')
        result.update(zip=str(zip_path), zipBytes=zip_path.stat().st_size, zipSha256=final.sha(zip_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
