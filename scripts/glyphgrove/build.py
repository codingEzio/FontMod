#!/usr/bin/env python3
"""Rebuild Glyphgrove Pixel from pinned component fonts; no external profile required."""
import argparse, copy, json, tempfile, shutil
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont
import font_ops as final
import font_mixed_support as mixed

def add_donor(font, path, role, work, config):
    donor = TTFont(path, recalcTimestamp=False)
    scale_upem(donor, font['head'].unitsPerEm)
    cmap = donor.getBestCmap()
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
    ps = family.replace(' ', '') + '-' + style
    prefix = family.replace(' ', '') + ('Italic' if style == 'Italic' else '')
    values = {1: family, 2: style, 3: version + ';LOCAL;' + ps,
              4: family + ' ' + style, 5: 'Version ' + version, 6: ps,
              8: 'Glyphgrove project',
              10: 'Glyphgrove Pixel Mono derived from Rysana Mono and its documented donor fonts.',
              16: family, 17: style, 25: prefix}
    for platform, encoding, language in [(3, 1, 0x409), (1, 0, 0)]:
        for name_id, value in values.items():
            names.setName(value, name_id, platform, encoding, language)
    return ps

def build_one(config, family, face, source, cubic, nerd, emoji, work, output):
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
    text, cjk_report = add_donor(text, cubic,
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
def main():
    p=argparse.ArgumentParser();p.add_argument('--inputs', type=Path, required=True);p.add_argument('--recipe', type=Path, required=True);p.add_argument('--output', type=Path, required=True);args=p.parse_args()
    config=json.loads(args.recipe.read_text()); inputs=args.inputs.resolve(); output=args.output.resolve()
    checkout=Path(__file__).resolve().parents[2]
    if any(path.is_relative_to(checkout) for path in (inputs, args.recipe.resolve(), output)):
        p.error('Inputs, recipe and output must be outside the source checkout')
    for name,digest in config['inputSha256'].items(): final.checked(inputs/name,digest)
    output.mkdir(parents=True,exist_ok=False)
    source=TTFont(inputs/'Noto3D-64.ttf',recalcTimestamp=False); strike=source['sbix'].strikes[55]
    for glyph in strike.glyphs.values():
        if glyph.graphicType=='png ':glyph.imageData=final.png_resize(glyph.imageData,28/55,64)
        glyph.originOffsetX=round(glyph.originOffsetX*28/55);glyph.originOffsetY=round(glyph.originOffsetY*28/55)
    strike.ppem=28;source['sbix'].strikes={28:strike}; emoji=output/'Emoji3D-Production.ttf';source.save(emoji)
    if final.sha(emoji)!=config['preparedEmojiSha256']:raise ValueError('Prepared Emoji differs from pinned reference')
    assets=[]
    for face in config['faces']:
        with tempfile.TemporaryDirectory(prefix='glyphgrove-',dir=output) as tmp:
            assets.append(build_one(config,{'name':'Glyphgrove Pixel Mono','cjk':'cubic'},face,inputs/face['file'],inputs/'Cubic_11.ttf',inputs/'SymbolsNerdFontMono-Regular.ttf',emoji,Path(tmp),output))
    final.write(output/'build-report.json',{'assets':assets,'inputs':config['inputSha256'],'emojiSha256':final.sha(emoji)})
if __name__=='__main__':main()
