"""Verified merge primitives for the final font producer. No legacy recipes."""
import copy, hashlib
from pathlib import Path
from fontTools import merge, subset
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.otlLib.builder import buildLigatureSubstSubtable, buildLookup
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

def set_copyright(font, text):
    """Preserve full source attribution without forcing Unicode into Mac Roman."""
    font['name'].setName(text, 0, 3, 1, 0x409)
    try:
        text.encode('mac_roman')
    except UnicodeEncodeError:
        font['name'].removeNames(nameID=0, platformID=1)
    else:
        font['name'].setName(text, 0, 1, 0, 0)


def outlines(font, names=None):
    glyphs = font.getGlyphSet()
    result = {}
    for name in names or font.getGlyphOrder():
        pen = DecomposingRecordingPen(glyphs)
        glyphs[name].draw(pen)
        result[name] = pen.value
    return result


def _merge_missing(base, donor, work, profile_name):
    before_order = base.getGlyphOrder()[:]
    before_cmap = base.getBestCmap().copy()
    before_outlines = outlines(base)
    before_metrics = dict(base['hmtx'].metrics)
    # These sources have no vertical substitution features. Preserve horizontal
    # GSUB/GPOS/GDEF; vertical metrics and the Nerd FontForge editor-only PfEd
    # table are explicitly outside this horizontal-text delivery.
    excluded_tables = [t for t in ('vhea', 'vmtx', 'PfEd') if t in base or t in donor]
    left, right = work / (profile_name + '-base.ttf'), work / (profile_name + '-donor.ttf')
    base.save(left); donor.save(right)
    options = merge.Options(); options.drop_tables = ['vhea', 'vmtx', 'PfEd']
    combined = merge.Merger(options=options).merge([str(left), str(right)])
    combined['head'].created, combined['head'].modified = base['head'].created, base['head'].modified
    copyright_text = '\n'.join(filter(None, [base['name'].getDebugName(0), donor['name'].getDebugName(0)]))
    set_copyright(combined, copyright_text)
    combined.recalcTimestamp = False
    merged_order = combined.getGlyphOrder()
    mapping = dict(zip(before_order, merged_order[:len(before_order)]))
    if len(mapping) != len(before_order):
        raise ValueError('Coverage merge lost existing glyphs')
    after_outlines = outlines(combined, list(mapping.values()))
    for old, new in mapping.items():
        if after_outlines[new] != before_outlines[old] or combined['hmtx'].metrics[new] != before_metrics[old]:
            raise ValueError(f'Coverage merge changed existing outline/advance: {old}')
    for cp, old in before_cmap.items():
        if combined.getBestCmap().get(cp) != mapping[old]:
            raise ValueError(f'Coverage merge replaced existing cmap: U+{cp:04X}')
    expected = set(before_cmap) | set(donor.getBestCmap())
    if set(combined.getBestCmap()) != expected:
        raise ValueError('Coverage cmap union incomplete')
    return combined, excluded_tables


def slim_emoji(source,ppem,destination,sample=None):
    """Keep an original bitmap strike, never resample; optional declared preview subset."""
    font=TTFont(source,recalcTimestamp=False)
    if ppem not in font['sbix'].strikes: raise ValueError('Source does not contain requested strike')
    font['sbix'].strikes={ppem:font['sbix'].strikes[ppem]}
    if sample:
        options=subset.Options();options.layout_features=['*'];options.recalc_timestamp=False
        worker=subset.Subsetter(options=options);worker.populate(text=sample);worker.subset(font)
    font.save(destination)
    return font


def with_emoji(text,source,ppem,work,sample=None):
    """Merge full GSUB closure + original PNGs; restore ASCII and add keycap rules."""
    emoji=slim_emoji(source,ppem,work/'emoji.ttf',sample)
    source_order=emoji.getGlyphOrder()[:];source_cmap=emoji.getBestCmap().copy()
    source_images={n:hashlib.sha256(g.imageData).hexdigest() for n,g in emoji['sbix'].strikes[ppem].glyphs.items() if g.graphicType=='png '}
    # sbix offsets/PPEM describe raster pixels, independent of design UPEM.
    # scale_upem visits outlines/metrics; original bitmap strike is unchanged.
    scale_upem(emoji,text['head'].unitsPerEm)
    text_cmap=text.getBestCmap().copy();text_order=text.getGlyphOrder()[:];text_count=len(text_order)
    text_outlines=outlines(text);text_metrics=dict(text['hmtx'].metrics)
    # Disjoint cmap inputs avoid Merger's locale-dependent duplicate rewrites.
    for table in text['cmap'].tables:
        if table.isUnicode() and hasattr(table,'cmap'):
            table.cmap={cp:n for cp,n in table.cmap.items() if cp not in source_cmap}
    text.save(work/'text.ttf');emoji.save(work/'emoji.ttf')
    options=merge.Options();options.drop_tables=['sbix','vhea','vmtx']
    combined=merge.Merger(options=options).merge([str(work/'text.ttf'),str(work/'emoji.ttf')])
    # Merger creates wall-clock head dates by default. Preserve the pinned
    # text source dates so identical recipes produce identical font bytes.
    combined['head'].created=text['head'].created
    combined['head'].modified=text['head'].modified
    target_order=combined.getGlyphOrder();mapping=dict(zip(source_order,target_order[text_count:]))
    # post format 3 regenerates names after uncoded ASCII glyphs are saved.
    # Preserve text by stable glyph ORDER/ID, never by pre-save glyph names.
    text_mapping=dict(zip(text_order,target_order[:text_count]))
    merged_text=outlines(combined,list(text_mapping.values()))
    for old,new in text_mapping.items():
        if merged_text[new]!=text_outlines[old] or combined['hmtx'].metrics[new]!=text_metrics[old]:raise ValueError('Merging emoji changed text outlines or advances')
    if len(mapping)!=len(source_order): raise ValueError('Emoji glyph-order merge lost glyphs')
    strike=copy.deepcopy(emoji['sbix'].strikes[ppem]);strike.glyphs={mapping[n]:g for n,g in strike.glyphs.items()}
    for name,glyph in strike.glyphs.items(): glyph.glyphName=name
    sbix=newTable('sbix');sbix.version=1;sbix.flags=1;sbix.strikes={ppem:strike};combined['sbix']=sbix
    restored={cp:text_mapping[name] for cp,name in text_cmap.items() if cp<128}
    for table in combined['cmap'].tables:
        if table.isUnicode() and hasattr(table,'cmap'): table.cmap.update(restored)
    # Keep normal ASCII text in Doto; keycap sequences still form Noto ligatures.
    ligatures={}
    for cp in map(ord,'#*0123456789'):
        if cp not in source_cmap: continue
        first=source_cmap[cp];output=None
        for lookup in emoji['GSUB'].table.LookupList.Lookup:
            for sub in lookup.SubTable:
                if lookup.LookupType==7: sub=sub.ExtSubTable
                for lig in getattr(sub,'ligatures',{}).get(first,[]):
                    if source_cmap[0x20E3] in lig.Component: output=mapping[lig.LigGlyph];break
        if output:
            base=restored[cp];mark=mapping[source_cmap[0x20E3]];vs=mapping[source_cmap[0xFE0F]]
            ligatures[(base,mark)]=output;ligatures[(base,vs,mark)]=output
    if ligatures:
        lookup=buildLookup([buildLigatureSubstSubtable(ligatures)])
        gsub=combined['GSUB'].table;index=len(gsub.LookupList.Lookup);gsub.LookupList.Lookup.append(lookup);gsub.LookupList.LookupCount+=1
        for record in gsub.FeatureList.FeatureRecord:
            if record.FeatureTag=='ccmp': record.Feature.LookupListIndex.insert(0,index);record.Feature.LookupCount+=1
    # Explicit VS16 mappings retain emoji presentation for ASCII + selector.
    uvs=CmapSubtable.newSubtable(14);uvs.platformID=0;uvs.platEncID=5;uvs.language=0xFF;uvs.cmap={}
    uvs.uvsDict={0xFE0F:[(cp,mapping[source_cmap[cp]]) for cp in map(ord,'#*0123456789') if cp in source_cmap]}
    text_symbols=[(cp,text_mapping[text_cmap[cp]]) for cp in source_cmap if cp>=128 and cp in text_cmap]
    if text_symbols: uvs.uvsDict[0xFE0E]=text_symbols
    combined['cmap'].tables=[t for t in combined['cmap'].tables if t.format!=14]+[uvs]
    copyright_text=text['name'].getDebugName(0)+'\n'+emoji['name'].getDebugName(0)
    set_copyright(combined,copyright_text)
    return combined,{'sourceGlyphs':len(source_order),'bitmapGlyphs':len(source_images),'ppem':ppem,'pixelSize':48 if ppem==41 else 64,
                    'sourceCoverage':sorted(source_cmap),'mapping':mapping,'glyphIds':{n:combined.getGlyphID(g) for n,g in mapping.items()},'imageHashes':source_images,
                    'asciiGlyphIds':{cp:combined.getGlyphID(g) for cp,g in restored.items()},
                    'previewSubset':bool(sample),'keycapRules':len(ligatures),'textGlyphsPreserved':text_count,'textOutlinesAndAdvancesMatch':True}


def rename(font, family):
    for p,e,l in [(3,1,0x409),(1,0,0)]:
        for n,value in {1:family,2:'Regular',3:family+'-1.0',4:family+' Regular',6:family.replace(' ','')+'-Regular',16:family,17:'Regular'}.items():
            font['name'].setName(value,n,p,e,l)
    font['OS/2'].usWeightClass=400
    font['OS/2'].fsSelection=(font['OS/2'].fsSelection & ~0x21)|0x40
    font['head'].macStyle=0
    font.recalcTimestamp=False


def portable_record(value,root):
    """Normalize source references without changing the checked producer release."""
    if isinstance(value,dict):
        return {portable_record(key,root):portable_record(item,root) for key,item in value.items()}
    if isinstance(value,list):return [portable_record(item,root) for item in value]
    if isinstance(value,str):
        prefix=str(root.resolve())
        result='.' if value==prefix else value.replace(prefix+'/','')
        if Path(result).is_absolute() or any(marker in result for marker in ('/Users/','/home/','/private/','/var/folders/','/tmp/')):
            raise ValueError('Portable metadata contains an external absolute source path')
        return result
    return value
