#!/usr/bin/env python3
"""Build the owner's private, experimental RysaMix system-font profiles.

Rysana variable outlines and positioning are preserved, while their advances
are narrowed. Han advances vary by family; Nerd and emoji use whole-cell advances.
MiSans is supplied locally and is never added to a source or release bundle.
"""
import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont

import final_fonts as final
import font_mixed_support as mixed

ROOT = final.ROOT
SOURCE_DIR = final.INPUT_ROOT / 'sources/rysana-mono'
RECIPE = SOURCE_DIR / 'recipe.json'


def recipe():
    return json.loads(RECIPE.read_text())


def checked_inputs(config, misans_source):
    faces = {}
    for face in config['faces']:
        faces[face['style']] = final.checked(SOURCE_DIR / face['file'], face['sha256'])
    catalog = json.loads((ROOT / 'sources/catalog.json').read_text())['sources']
    cubic = final.checked(final.input_path(catalog['cubic11']['path']), catalog['cubic11']['sha256'])
    records = json.loads((ROOT / 'sources/geist-mixed/sources.json').read_text())
    nerd_record = next(r for r in records if r['file'] == 'SymbolsNerdFontMono-Regular.ttf')
    nerd = final.checked(final.input_path('sources/geist-mixed/' + nerd_record['file']), nerd_record['sha256'])
    misans = final.checked(Path(misans_source).expanduser(), config['misans']['sha256'])
    return faces, cubic, nerd, misans


def is_misans_cjk(cp, config):
    # Keep Rysana for Latin and numbers, including their full-width forms.
    name = unicodedata.name(chr(cp), '')
    return (any(start <= cp <= end for start, end in config['cjkRanges'])
            and 'LATIN' not in name and 'DIGIT' not in name)


def add_donor(font, path, role, work, config):
    donor = TTFont(path, recalcTimestamp=False)
    scale_upem(donor, font['head'].unitsPerEm)
    cmap = donor.getBestCmap()
    if role == 'misans':
        points = {cp for cp in cmap if is_misans_cjk(cp, config)}
        replaced = points & set(font.getBestCmap())
        for table in font['cmap'].tables:
            if table.isUnicode() and table.format != 14:
                table.cmap = {cp: glyph for cp, glyph in table.cmap.items() if cp not in replaced}
    else:
        points = set(cmap) - set(font.getBestCmap())
        replaced = set()
    opts = subset.Options()
    opts.layout_features = ['*']
    opts.recalc_timestamp = False
    opts.glyph_names = True
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=points)
    sub.subset(donor)
    spacing = config['spacing']
    cell = spacing['cell']
    # Include unencoded GSUB alternates as well as cmap glyphs: a substitution
    # must not quietly return an old-width CJK or icon glyph.
    for name, (advance, lsb) in donor['hmtx'].metrics.items():
        if not advance:
            continue
        if role == 'nerd':
            width = cell * spacing['nerdCells']
        else:
            width = cell if advance <= spacing['sourceCell'] * 1.25 else cell * spacing['cjkCells']
        donor['hmtx'].metrics[name] = (width, lsb)
    print(f'  {role}: {len(points)} codepoints; {len(replaced)} source mappings replaced', flush=True)
    merged, _ = mixed._merge_missing(font, donor, work, role)
    return merged, {'selectedCodepoints': len(points), 'replacedCodepoints': len(replaced)}


def tighten_han(font, role, config, from_advance=None):
    """Reduce Han advances while retaining outlines and non-Han spacing."""
    cmap = font.getBestCmap()
    def han(cp):
        return 0x3400 <= cp <= 0x9fff or 0xf900 <= cp <= 0xfaff or 0x20000 <= cp <= 0x323af
    names = {glyph for cp, glyph in cmap.items() if han(cp)}
    width = config['spacing']['hanAdvance'][role]
    original_width = from_advance if from_advance is not None else config['spacing']['cell'] * config['spacing']['cjkCells']
    changed = 0
    for name in names:
        advance, lsb = font['hmtx'].metrics[name]
        if advance == original_width:
            font['hmtx'].metrics[name] = (width, lsb)
            changed += 1
    return changed


def set_names(font, original, family, style, version):
    names = font['name']
    old_ps_ids = {instance.postscriptNameID for instance in original['fvar'].instances
                  if instance.postscriptNameID != 0xffff}
    for name_id in old_ps_ids | {1, 2, 3, 4, 5, 6, 8, 10, 16, 17, 25}:
        names.removeNames(nameID=name_id)
    ps = family + '-' + style
    prefix = family + ('Italic' if style == 'Italic' else '')
    values = {1: family, 2: style, 3: version + ';LOCAL;' + ps,
              4: family + ' ' + style, 5: 'Version ' + version, 6: ps,
              8: 'FontMod local experiment',
              10: 'Private experiment derived from Rysana Mono and the documented donor fonts.',
              16: family, 17: style, 25: prefix}
    for platform, encoding, language in [(3, 1, 0x409), (1, 0, 0)]:
        for name_id, value in values.items():
            names.setName(value, name_id, platform, encoding, language)
    return ps


def prepare_emoji(config, output):
    # Reuse the owner's verified, same-recipe preparation when present. The
    # existing producer regenerates it from the pinned original otherwise.
    prior_font = ROOT / 'Final/Emoji3D-Production.ttf'
    prior_report = ROOT / 'Final/emoji-preparation.json'
    if prior_font.is_file() and prior_report.is_file():
        report = json.loads(prior_report.read_text())
        if (report.get('config') == config['emojiRecipe']
                and report.get('sha256') == final.sha(prior_font)):
            shutil.copyfile(prior_font, output / prior_font.name)
            shutil.copyfile(prior_report, output / prior_report.name)
    return final.emoji_file(config['emojiRecipe'], output)


def build_one(config, family, face, source, cubic, nerd, misans, emoji, work, output):
    original = TTFont(source, recalcTimestamp=False)
    if [(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
            for a in original['fvar'].axes] != [('wght', 100, 400, 900)]:
        raise ValueError('Unexpected Rysana variable axis')
    text = instantiateVariableFont(original, {'wght': 400}, inplace=False)
    text.flavor = None
    text.save(work / 'source.ttf')
    text = TTFont(work / 'source.ttf', recalcTimestamp=False)
    base_order = text.getGlyphOrder()[:]
    if base_order != original.getGlyphOrder():
        raise ValueError('Source glyph order changed during instancing')
    print('  adding Nerd glyphs', flush=True)
    text, nerd_report = add_donor(text, nerd, 'nerd', work, config)
    print('  adding ' + family['cjk'] + ' glyphs', flush=True)
    text, cjk_report = add_donor(text, cubic if family['cjk'] == 'cubic' else misans,
                                 family['cjk'], work, config)
    print('  adding full Emoji3D', flush=True)
    text, emoji_report = mixed.with_emoji(text, emoji, config['emojiRecipe']['targetPpem'], work)
    final.finalize_layout(text)
    final.symbol_aliases(text, config['symbolAliases'])
    final.restore_variation(text, original)

    # The static donor merge preserves the source glyph IDs as a prefix. Restore
    # variable GDEF/GPOS by decoding the source tables against those IDs, not
    # by copying source glyph names: post format 3 may regenerate those names.
    for tag in ('GDEF', 'GPOS'):
        table = newTable(tag)
        table.decompile(original.getTableData(tag), text)
        text[tag] = table

    spacing = config['spacing']
    source_cell, cell = spacing['sourceCell'], spacing['cell']
    for old, new in zip(base_order, text.getGlyphOrder()[:len(base_order)]):
        advance, lsb = text['hmtx'].metrics[new]
        if advance not in (0, source_cell, source_cell * 2):
            raise ValueError(f'Unexpected source advance for {old}: {advance}')
        if advance:
            text['hmtx'].metrics[new] = (cell * (advance // source_cell), lsb)
    for name in emoji_report['mapping'].values():
        advance, lsb = text['hmtx'].metrics[name]
        if advance:
            text['hmtx'].metrics[name] = (cell * spacing['emojiCells'], lsb)
    tighten_han(text, family['cjk'], config)
    name = set_names(text, original, family['name'], face['style'], config['version'])
    if len(text.getGlyphOrder()) > 65535:
        raise ValueError('Merged font exceeds the TrueType glyph limit')
    path = output / (name + '.ttf')
    text.flavor = None
    # The merger preserves the source dates; do not let TTFont replace the
    # modified date with wall-clock time when serializing identical builds.
    text.recalcTimestamp = False
    text.save(path)
    print(f'  saved {path.name}: {path.stat().st_size} bytes', flush=True)
    return {'family': family['name'], 'style': face['style'], 'postScript': name,
            'file': path.name, 'sha256': final.sha(path), 'bytes': path.stat().st_size,
            'glyphs': len(text.getGlyphOrder()), 'cjk': family['cjk'],
            'source': face['file'], 'sourceSha256': face['sha256'],
            'nerd': nerd_report, 'cjkCoverage': cjk_report,
            'emojiGlyphs': emoji_report['bitmapGlyphs'], 'emojiSourcePpem': emoji_report['ppem']}


def build(output, misans_source=None):
    config = recipe()
    misans_source = misans_source or Path(config['misans']['default']).expanduser()
    faces, cubic, nerd, misans = checked_inputs(config, misans_source)
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir()
    private_misans = inputs / 'MiSans-Regular.ttf'
    shutil.copyfile(misans, private_misans)
    final.checked(private_misans, config['misans']['sha256'])
    licenses = output / 'licenses'
    licenses.mkdir()
    for path in [SOURCE_DIR / 'LICENSE.txt', ROOT / 'sources/Cubic11-OFL.txt',
                 ROOT / 'sources/Noto3D-OFL.txt']:
        shutil.copyfile(path, licenses / ('Rysana-LICENSE.txt' if path == SOURCE_DIR / 'LICENSE.txt' else path.name))
    shutil.copytree(ROOT / 'sources/coverage/NerdFonts/licenses', licenses / 'NerdFonts')
    (output / 'NOTICE.md').write_text(
        '# Private RysaMix experiment\n\n'
        'Rysana Mono 1.0.0 provides the variable upright and italic outlines; '
        'Cubic 11 or MiSans 4.009 provides CJK, Symbols Nerd Font Mono provides icons, '
        'and Noto 3D provides the retained emoji repertoire. '
        'Rysana advances are 5% tighter; Han advances are narrower by family. '
        'The originals and component notices remain separately identified.\n\n'
        'The published MiSans license prohibits adaptation or redevelopment. '
        'No separate modification permission is recorded. This is the owner-requested '
        'local experiment, not a redistribution or public release. '
        'Review the upstream license and obtain any required rights before further use or distribution: '
        + config['misans']['licenseUrl'] + '\n')
    emoji, emoji_report = prepare_emoji(config, output)
    report = {'schemaVersion': 1, 'version': config['version'],
              'recipeSha256': final.sha(RECIPE), 'recipe': config,
              'emoji': emoji_report, 'misansInput': 'inputs/MiSans-Regular.ttf', 'assets': []}
    for family in config['families']:
        for face in config['faces']:
            print('Building', family['name'], face['style'], flush=True)
            # Keep failed work for diagnosis; remove only this build's successful scratch.
            work = Path(tempfile.mkdtemp(prefix='.work-', dir=output))
            item = build_one(config, family, face, faces[face['style']], cubic, nerd,
                             private_misans, emoji, work, output)
            report['assets'].append(item)
            final.write(output / 'provenance.json', report)
            shutil.rmtree(work)
    final.write(output / 'provenance.json', report)
    print(json.dumps({'output': str(output), 'assets': report['assets']}, ensure_ascii=False, indent=2))
    return report


def derive_trials(source, output):
    """Derive renamed and tighter trials from the checked previous trial."""
    source, output = (Path(p).expanduser().resolve() for p in (source, output))
    config = recipe()
    previous = json.loads((source / 'provenance.json').read_text())
    before = copy.deepcopy(previous['recipe'])
    after = copy.deepcopy(config)
    for data in (before, after):
        data.pop('version')
        data.pop('families')
        data['spacing'].pop('hanAdvance')
        data['spacing'].pop('policy')
    if before != after or previous['recipe']['spacing']['hanAdvance'] != {'cubic': 1106, 'misans': 1060}:
        raise ValueError('Source trial recipe differs beyond the approved naming and Han spacing')
    expected = {(x['cjk'], f['style']) for x in config['families'] for f in config['faces']}
    if {(x['cjk'], x['style']) for x in previous['assets']} != expected:
        raise ValueError('Source trial does not contain the required faces')
    checked_inputs(config, source / previous['misansInput'])
    final.checked(source / 'Emoji3D-Production.ttf', previous['emoji']['sha256'])
    output.mkdir(parents=True, exist_ok=False)
    for name in ('inputs', 'licenses'):
        shutil.copytree(source / name, output / name)
    for name in ('Emoji3D-Production.ttf', 'emoji-preparation.json', 'NOTICE.md'):
        shutil.copyfile(source / name, output / name)
    report = copy.deepcopy(previous)
    report.update(version=config['version'], recipe=config, recipeSha256=final.sha(RECIPE), assets=[])
    report['derivedFrom'] = {'recipeSha256': previous['recipeSha256'], 'assets': []}
    families = {x['cjk']: x['name'] for x in config['families']}
    for item in previous['assets']:
        path = final.checked(source / item['file'], item['sha256'])
        font = TTFont(path, recalcTimestamp=False)
        count = tighten_han(font, item['cjk'], config, previous['recipe']['spacing']['hanAdvance'][item['cjk']])
        if not count:
            raise ValueError('No Han glyphs found for ' + item['file'])
        family = families[item['cjk']]
        ps = set_names(font, font, family, item['style'], config['version'])
        dest = output / (ps + '.ttf')
        font.save(dest)
        original, rebuilt = TTFont(path, lazy=True), TTFont(dest, lazy=True)
        for tag in original.keys():
            if tag not in ('GlyphOrder', 'head', 'name', 'hmtx') and original.getTableData(tag) != rebuilt.getTableData(tag):
                raise ValueError('Unexpected changed table: ' + tag)
        result = dict(item, family=family, postScript=ps, file=dest.name,
                      sha256=final.sha(dest), bytes=dest.stat().st_size, tightenedHanGlyphs=count)
        report['assets'].append(result)
        report['derivedFrom']['assets'].append({'file': item['file'], 'sha256': item['sha256']})
        print(dest.name, count, flush=True)
    final.write(output / 'provenance.json', report)
    return report


def compact(source, emoji_cache, output):
    """Replace only verified bitmap data in a previous source-derived build."""
    source, emoji_cache, output = (Path(p).expanduser().resolve() for p in (source, emoji_cache, output))
    config = recipe()
    previous = json.loads((source / 'provenance.json').read_text())
    old_recipe = copy.deepcopy(previous['recipe'])
    new_without_emoji = {k: v for k, v in config.items() if k != 'emojiRecipe'}
    old_without_emoji = {k: v for k, v in old_recipe.items() if k != 'emojiRecipe'}
    old_emoji_recipe, new_emoji_recipe = old_recipe['emojiRecipe'], config['emojiRecipe']
    if (old_without_emoji != new_without_emoji
            or old_emoji_recipe.get('paletteColors', 256) != 256
            or new_emoji_recipe.get('paletteColors') != 64
            or old_emoji_recipe['targetPpem'] != new_emoji_recipe['targetPpem']
            or old_emoji_recipe['sourcePpem'] != new_emoji_recipe['sourcePpem']):
        raise ValueError('Compact requires the same recipe and a 256-to-64 palette change')
    expected = {(family['name'], face['style']) for family in config['families'] for face in config['faces']}
    if {(item['family'], item['style']) for item in previous['assets']} != expected:
        raise ValueError('Compact source does not contain all requested families and styles')
    old_emoji = final.checked(source / 'Emoji3D-Production.ttf', previous['emoji']['sha256'])
    new_report = json.loads((emoji_cache / 'emoji-preparation.json').read_text())
    new_emoji = final.checked(emoji_cache / 'Emoji3D-Production.ttf', new_report['sha256'])
    emoji_source = json.loads((ROOT / 'sources/emoji3d.json').read_text())
    if new_report['config'] != new_emoji_recipe or new_report['sourceSha256'] != emoji_source['sha256']:
        raise ValueError('Compact emoji cache is not from the pinned source and selected policy')
    final.checked(source / previous['misansInput'], config['misans']['sha256'])
    before_emoji = TTFont(old_emoji, recalcTimestamp=False)
    after_emoji = TTFont(new_emoji, recalcTimestamp=False)
    if (before_emoji.getGlyphOrder() != after_emoji.getGlyphOrder()
            or before_emoji.getBestCmap() != after_emoji.getBestCmap()
            or before_emoji.getTableData('GSUB') != after_emoji.getTableData('GSUB')):
        raise ValueError('Emoji coverage, shaping or glyph order changed')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / 'licenses', output / 'licenses')
    shutil.copytree(source / 'inputs', output / 'inputs')
    shutil.copyfile(source / 'NOTICE.md', output / 'NOTICE.md')
    shutil.copyfile(new_emoji, output / 'Emoji3D-Production.ttf')
    shutil.copyfile(emoji_cache / 'emoji-preparation.json', output / 'emoji-preparation.json')
    report = {'schemaVersion': 1, 'version': config['version'],
              'recipeSha256': final.sha(RECIPE), 'recipe': config,
              'emoji': new_report, 'misansInput': previous['misansInput'], 'assets': [],
              'compactFrom': {'recipeSha256': previous['recipeSha256'], 'assets': []}}
    ppem = new_emoji_recipe['targetPpem']
    old_strike, new_strike = before_emoji['sbix'].strikes[ppem], after_emoji['sbix'].strikes[ppem]
    source_order = before_emoji.getGlyphOrder()
    for item in previous['assets']:
        path = final.checked(source / item['file'], item['sha256'])
        font = TTFont(path, recalcTimestamp=False)
        count = len(font.getGlyphOrder()) - len(source_order)
        if count <= 0:
            raise ValueError('Missing appended Emoji3D glyph range')
        target_strike = font['sbix'].strikes[ppem]
        for index, source_name in enumerate(source_order):
            target_name = font.getGlyphName(count + index)
            expected = old_strike.glyphs[source_name]
            found = target_strike.glyphs[target_name]
            if (expected.graphicType != found.graphicType
                    or expected.imageData != found.imageData
                    or expected.originOffsetX != found.originOffsetX
                    or expected.originOffsetY != found.originOffsetY):
                raise ValueError('Existing emoji glyph mapping differs: ' + target_name)
            replacement = copy.deepcopy(new_strike.glyphs[source_name])
            replacement.glyphName = target_name
            target_strike.glyphs[target_name] = replacement
        dest = output / item['file']
        font.recalcTimestamp = False
        font.save(dest)
        rebuilt = TTFont(dest, lazy=True, recalcTimestamp=False)
        original = TTFont(path, lazy=True, recalcTimestamp=False)
        for tag in original.keys():
            if tag not in ('GlyphOrder', 'head', 'sbix') and original.getTableData(tag) != rebuilt.getTableData(tag):
                raise ValueError('Compact changed a non-bitmap table: ' + tag)
        old_head, new_head = bytearray(original.getTableData('head')), bytearray(rebuilt.getTableData('head'))
        old_head[8:12] = new_head[8:12] = b'\0' * 4
        if old_head != new_head:
            raise ValueError('Compact changed font-header metadata')
        record = dict(item, sha256=final.sha(dest), bytes=dest.stat().st_size)
        report['assets'].append(record)
        report['compactFrom']['assets'].append({'file': item['file'], 'sha256': item['sha256']})
        print(f'  {item["file"]}: {item["bytes"]} -> {record["bytes"]} bytes', flush=True)
    final.write(output / 'provenance.json', report)
    print(json.dumps({'output': str(output), 'fonts': len(report['assets']),
                      'bytes': sum(x['bytes'] for x in report['assets']),
                      'policy': 'only 3D emoji bitmap palettes changed'}, ensure_ascii=False))
    return report


def check(output):
    output = Path(output).expanduser().resolve()
    config = recipe()
    report = json.loads((output / 'provenance.json').read_text())
    if report['recipeSha256'] != final.sha(RECIPE) or report['recipe'] != config:
        raise ValueError('RysaMix recipe changed; rebuild into a new output directory')
    final.checked(output / report['misansInput'], config['misans']['sha256'])
    expected = {(family['name'], face['style']) for family in config['families'] for face in config['faces']}
    if {(x['family'], x['style']) for x in report['assets']} != expected:
        raise ValueError('RysaMix output does not contain all requested families and styles')
    emoji_path = final.checked(output / 'Emoji3D-Production.ttf', report['emoji']['sha256'])
    emoji_cmap = set(TTFont(emoji_path).getBestCmap())
    nerd_cmap = set(TTFont(final.input_path('sources/geist-mixed/SymbolsNerdFontMono-Regular.ttf')).getBestCmap())
    cubic_cmap = set(TTFont(final.input_path('sources/Cubic_11.ttf')).getBestCmap())
    misans_cmap = {cp for cp in TTFont(output / report['misansInput']).getBestCmap()
                   if is_misans_cjk(cp, config)}
    spacing = config['spacing']
    for item in report['assets']:
        path = final.checked(output / item['file'], item['sha256'])
        font = TTFont(path, recalcTimestamp=False)
        names = font['name']
        if (names.getDebugName(1), names.getDebugName(2), names.getDebugName(6)) != (item['family'], item['style'], item['postScript']):
            raise ValueError('Unexpected font identity: ' + str(path))
        if [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in font['fvar'].axes] != [('wght', 100, 400, 900)]:
            raise ValueError('Unexpected font weight axis: ' + str(path))
        cmap = font.getBestCmap()
        donor_cmap = cubic_cmap if item['cjk'] == 'cubic' else misans_cmap
        source_cmap = set(TTFont(SOURCE_DIR / item['source']).getBestCmap())
        if not (source_cmap | donor_cmap | nerd_cmap | emoji_cmap).issubset(cmap):
            raise ValueError('A source repertoire is incomplete: ' + str(path))
        samples = {'A': spacing['cell'], '0': spacing['cell'], '中': spacing['hanAdvance'][item['cjk']],
                   '漢': spacing['hanAdvance'][item['cjk']], '\uf120': spacing['cell'] * spacing['nerdCells'],
                   '😀': spacing['cell'] * spacing['emojiCells']}
        for char, advance in samples.items():
            if ord(char) not in cmap or font['hmtx'].metrics[cmap[ord(char)]][0] != advance:
                raise ValueError(f'Unexpected coverage or advance for {char} in {path}')
        if cmap.get(0xea00) != cmap.get(0xf099) or set(font['sbix'].strikes) != {config['emojiRecipe']['targetPpem']}:
            raise ValueError('Symbol alias or Emoji3D strike missing: ' + str(path))
        strike = font['sbix'].strikes[config['emojiRecipe']['targetPpem']]
        if sum(g.graphicType == 'png ' for g in strike.glyphs.values()) != item['emojiGlyphs']:
            raise ValueError('Emoji3D bitmap repertoire is incomplete: ' + str(path))
        if len(font.getGlyphOrder()) != item['glyphs'] or not getattr(font['GDEF'].table, 'VarStore', None):
            raise ValueError('Glyph count or source positioning variations changed: ' + str(path))
    print(json.dumps({'profile': 'rysamix', 'fonts': len(report['assets']), 'hashes': 'pass',
                      'weightAxis': '100–900', 'cell': spacing['cell'],
                      'hanAdvance': spacing['hanAdvance'],
                      'scope': 'private local system font candidate'}, ensure_ascii=False))
    return report


def deep_check(output, report):
    """Compare shaped source text, donor outlines and emoji bitmap samples."""
    hb = shutil.which('hb-shape')
    if not hb:
        raise ValueError('Deep check needs hb-shape from HarfBuzz')
    output = Path(output).expanduser().resolve()

    def shape(path, value, weight=None):
        command = [hb, '--no-glyph-names', '--show-extents', '--output-format=json']
        if weight is not None:
            command.append(f'--variations=wght={weight}')
        return json.loads(subprocess.check_output(command + [str(path), value], text=True))

    def cluster_signature(glyphs):
        # Shrinking the previous advance changes a mark's relative dx; compare
        # its actual position within the cluster instead of the raw offset.
        cursor, starts, result = 0, {}, []
        for glyph in glyphs:
            position = cursor + glyph['dx']
            cluster = glyph['cl']
            starts.setdefault(cluster, position)
            result.append((glyph['g'], cluster, position - starts[cluster], glyph['dy'],
                           glyph['xb'], glyph['yb'], glyph['w'], glyph['h']))
            cursor += glyph['ax']
        return result

    samples = ['abc XYZ 012 != -> => !== {x: 123}', 'café ā Æ résumé',
               '한글', 'مرحبا', 'สวัสดี']
    checks = 0
    with tempfile.TemporaryDirectory(prefix='rysamix-shape-') as temp:
        sources = {}
        for face in report['recipe']['faces']:
            font = TTFont(SOURCE_DIR / face['file'], recalcTimestamp=False)
            font.flavor = None
            path = Path(temp) / (face['style'] + '.ttf')
            font.save(path)
            sources[face['style']] = path
        for item in report['assets']:
            path = output / item['file']
            for weight in (100, 400, 700, 900):
                for sample in samples:
                    original = cluster_signature(shape(sources[item['style']], sample, weight))
                    actual = cluster_signature(shape(path, sample, weight))
                    if original != actual:
                        raise ValueError(f'Rysana shaping changed: {item["file"]}, {weight}, {sample!r}')
                    checks += 1

            target = TTFont(path)
            donor_path = final.input_path('sources/Cubic_11.ttf') if item['cjk'] == 'cubic' else output / report['misansInput']
            donor = TTFont(donor_path, recalcTimestamp=False)
            scale_upem(donor, target['head'].unitsPerEm)
            chars = '中漢文' if item['cjk'] == 'cubic' else '中漢文あㄅ'
            for char in chars:
                source_name = donor.getBestCmap()[ord(char)]
                target_name = target.getBestCmap()[ord(char)]
                if mixed.outlines(donor, [source_name])[source_name] != mixed.outlines(target, [target_name])[target_name]:
                    raise ValueError(f'Donor outline changed: {item["file"]}, {char}')
                checks += 1

            emoji = TTFont(output / 'Emoji3D-Production.ttf')
            emoji_strike = emoji['sbix'].strikes[report['recipe']['emojiRecipe']['targetPpem']]
            target_strike = target['sbix'].strikes[report['recipe']['emojiRecipe']['targetPpem']]
            for sequence in ('😀', '👩🏽‍💻', '🇹🇼', '1️⃣'):
                before = shape(output / 'Emoji3D-Production.ttf', sequence)
                after = shape(path, sequence, 400)
                if len(before) != 1 or len(after) != 1:
                    raise ValueError(f'Emoji sequence did not shape as one glyph: {sequence}')
                old = emoji_strike.glyphs[emoji.getGlyphName(before[0]['g'])]
                new = target_strike.glyphs[target.getGlyphName(after[0]['g'])]
                if old.graphicType != 'png ' or new.graphicType != 'png ' or hashlib.sha256(old.imageData).digest() != hashlib.sha256(new.imageData).digest():
                    raise ValueError(f'Emoji bitmap changed: {item["file"]}, {sequence}')
                checks += 1
    receipt = {'profile': 'rysamix', 'checks': checks, 'result': 'pass',
               'harfbuzz': subprocess.check_output([hb, '--version'], text=True).splitlines()[0],
               'scope': 'variable source shaping, CJK donor outlines and four emoji sequences'}
    final.write(output / 'deep-check.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return receipt


def native_manifest(output, report, replacements=None):
    output = Path(output).expanduser().resolve()
    entries = []
    for item in report['assets']:
        entry = {'name': item['postScript'], 'family': item['family'],
                 'hanRatio': report['recipe']['spacing']['hanAdvance'][item['cjk']] / report['recipe']['spacing']['cell'],
                 'file': str(output / item['file']), 'sha256': item['sha256'],
                 'sample': {'latin': 'ABC xyz 0123456789',
                            'mixed': 'ABC 012 简体中文 繁體中文 あいう 한글',
                            'requireMixedCoverage': True},
                 'probes': [{'text': '\uf120', 'glyphCount': 1},
                            {'text': '\uea00', 'glyphCount': 1},
                            {'text': '😀', 'glyphCount': 1},
                            {'text': '👩🏽‍💻', 'glyphCount': 1},
                            {'text': '🇹🇼', 'glyphCount': 1},
                            {'text': '1️⃣', 'glyphCount': 1}]}
        if replacements and item['postScript'] in replacements:
            entry['replaceSha256'] = replacements[item['postScript']]
        entries.append(entry)
    path = output / 'native-manifest.json'
    final.write(path, entries)
    return path


def native(mode, output, report, replace_from=None):
    replacements = {}
    if replace_from is not None:
        previous = json.loads(Path(replace_from).expanduser().read_text())
        if previous.get('mode') != 'installed':
            raise ValueError('Replacement requires a previous installed-font readback')
        for item in previous['fonts']:
            expected_path = Path.home() / 'Library/Fonts' / (item['postScript'] + '.ttf')
            if Path(item['file']) != expected_path or item['postScript'] in replacements:
                raise ValueError('Invalid or duplicate installed-font receipt')
            replacements[item['postScript']] = item['sha256']
    if mode == 'install':
        # Avoid an unexpected replacement or a partially written batch due to
        # a name collision. Existing identical files can be re-verified.
        for item in report['assets']:
            path = Path.home() / 'Library/Fonts' / (item['postScript'] + '.ttf')
            if path.exists() and final.sha(path) != item['sha256']:
                if replacements.get(item['postScript']) != final.sha(path):
                    raise ValueError('Existing font differs; refusing replacement: ' + str(path))
    manifest = native_manifest(output, report, replacements)
    command = ['swift', '-module-cache-path', str(ROOT / '.cache/swift-rysamix'),
               str(ROOT / 'scripts/native.swift'), mode, str(manifest)]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    if result.stderr:
        print(result.stderr, end='')
    receipt = json.loads(result.stdout)
    final.write(Path(output).expanduser().resolve() / (mode + '-receipt.json'), receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if mode == 'installed':
        command[-3:] = [str(ROOT / 'scripts/rysa_native_variations.swift'), str(manifest)]
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        if result.stderr:
            print(result.stderr, end='')
        variations = json.loads(result.stdout)
        final.write(Path(output).expanduser().resolve() / 'variations-receipt.json', variations)
        print(json.dumps(variations, ensure_ascii=False, indent=2))
