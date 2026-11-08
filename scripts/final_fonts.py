#!/usr/bin/env python3
"""Build the owner's final mixed families from pinned original inputs.

No consumer or installed-font mutation. The manifest owns names, geometry and
size policy; complete Noto cmap/GSUB is retained with smaller PNGs. Code keeps
source gvar deltas; appended glyphs have no variation. All sources are local.
"""
import argparse, copy, hashlib, io, json, struct, tempfile, zlib
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._s_b_i_x import Strike
import font_mixed_support as core
from font_mixed_support import _merge_missing
from font_mixed_support import with_emoji
from font_mixed_support import rename
from input_root import resolve_input_root

ROOT=Path(__file__).resolve().parents[1]
INPUT_ROOT=resolve_input_root(ROOT)
def input_path(name):
    return INPUT_ROOT / name
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def checked(p,h):
    if sha(p)!=h:raise ValueError('Source digest mismatch: '+str(p))
    return p

def png_resize(raw, factor, colors=256):
    """Keep alpha and 3D appearance; bounded 256-color palette per small glyph."""
    from PIL import Image
    image=Image.open(io.BytesIO(raw)).convert("RGBA")
    image=image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.LANCZOS)
    image=image.quantize(colors=colors,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE)
    buffer=io.BytesIO();image.save(buffer,format="PNG",optimize=True,compress_level=9)
    return buffer.getvalue()

def emoji_file(config,output):
    m=json.loads((ROOT/'sources/emoji3d.json').read_text());source=checked(input_path(m['path']),m['sha256']);dest=output/'Emoji3D-Production.ttf'
    cache=output/'emoji-preparation.json'
    if dest.exists()and cache.exists():
        r=json.loads(cache.read_text())
        if r['config']==config and r['sourceSha256']==sha(source)and r['sha256']==sha(dest):return dest,r
    font=TTFont(source,recalcTimestamp=False);strike=font['sbix'].strikes[config['sourcePpem']];ratio=config['targetPpem']/config['sourcePpem'];images=0
    for glyph in strike.glyphs.values():
        if glyph.graphicType=='png ':glyph.imageData=png_resize(glyph.imageData,ratio,config.get('paletteColors',256));images+=1
        glyph.originOffsetX=round(glyph.originOffsetX*ratio);glyph.originOffsetY=round(glyph.originOffsetY*ratio)
    strike.ppem=config['targetPpem'];font['sbix'].strikes={strike.ppem:strike};font.save(dest)
    reread=TTFont(dest);original=TTFont(source)
    assert reread.getBestCmap()==original.getBestCmap()
    assert reread.getTableData('GSUB')==original.getTableData('GSUB')
    report={'config':config,'sourceSha256':sha(source),'sourceBytes':source.stat().st_size,'sha256':sha(dest),'bytes':dest.stat().st_size,'bitmapImages':images,'cmapUnchanged':True,'gsubUnchanged':True}
    write(cache,report);print('emoji',json.dumps(report),flush=True);return dest,report

def height_only(font,height):
    glyphs=font.getGlyphSet();records={}
    for name in font.getGlyphOrder():
        rec=DecomposingRecordingPen(glyphs);glyphs[name].draw(rec);records[name]=rec
    metrics=dict(font['hmtx'].metrics)
    for name,rec in records.items():
        pen=TTGlyphPen(None);rec.replay(TransformPen(pen,(1,0,0,height,0,0)));font['glyf'][name]=pen.glyph()
    for tag,fields in [('hhea',['ascent','descent']),('OS/2',['sTypoAscender','sTypoDescender','usWinAscent','usWinDescent','sxHeight','sCapHeight'])]:
        for field in fields:
            if hasattr(font[tag],field):setattr(font[tag],field,round(getattr(font[tag],field)*height))
    assert font['hmtx'].metrics==metrics

def add_missing(font,path,work,role):
    donor=TTFont(path,recalcTimestamp=False);scale_upem(donor,font['head'].unitsPerEm);points=set(donor.getBestCmap())-set(font.getBestCmap())
    opts=subset.Options();opts.layout_features=['*'];opts.recalc_timestamp=False;opts.glyph_names=True
    sub=subset.Subsetter(options=opts);sub.populate(unicodes=points);sub.subset(donor)
    return _merge_missing(font,donor,work,role)[0]

def restore_variation(font,original):
    # Merges preserve the original prefix order. Re-key deltas by glyph ID,
    # because serialization can regenerate post-format-3 names.
    old=original.getGlyphOrder();new=font.getGlyphOrder();mapping=dict(zip(old,new[:len(old)]))
    for tag in ['fvar','avar','gvar','cvar','MVAR']:
        if tag in original:font[tag]=copy.deepcopy(original[tag])
    font['gvar'].variations={mapping[n]:copy.deepcopy(original['gvar'].variations.get(n,[]))for n in old}
    for n in new[len(old):]:font['gvar'].variations[n]=[]
    # HVAR is indexed by the source glyph order; append zero-delta mappings.
    if 'HVAR'in original:
        font['HVAR']=copy.deepcopy(original['HVAR']);table=font['HVAR'].table
        zero=None
        for outer,data in enumerate(table.VarStore.VarData):
            for inner,item in enumerate(data.Item):
                if not any(item):zero=(outer<<16)|inner;break
            if zero is not None:break
        if zero is None:
            data=table.VarStore.VarData[0];zero=len(data.Item);data.Item.append([0]*data.VarRegionCount);data.ItemCount=len(data.Item)
        from fontTools.ttLib.tables import otTables
        for field in ['AdvWidthMap','LsbMap','RsbMap']:
            oldmap=getattr(table,field,None)
            if oldmap is None and field!='AdvWidthMap':continue
            index=otTables.VarIdxMap();index.mapping={mapping[n]:(oldmap.mapping.get(n,0)if oldmap else i)for i,n in enumerate(old)};index.mapping.update({n:zero for n in new[len(old):]});setattr(table,field,index)
    for a in font['fvar'].axes:
        for rec in original['name'].names:
            if rec.nameID==a.axisNameID:font['name'].names.append(copy.deepcopy(rec))
    for inst in font['fvar'].instances:
        inst.postscriptNameID=0xffff
        for rec in original['name'].names:
            if rec.nameID==inst.subfamilyNameID:font['name'].names.append(copy.deepcopy(rec))

def finalize_layout(font):
    # Core Text can choose the Latin script for a mixed emoji run, whereas
    # HarfBuzz chooses DFLT. All ccmp records need the source emoji lookups.
    records=[r for r in font['GSUB'].table.FeatureList.FeatureRecord if r.FeatureTag=='ccmp']
    lookups=list(dict.fromkeys(i for r in records for i in r.Feature.LookupListIndex))
    for r in records:r.Feature.LookupListIndex=lookups[:];r.Feature.LookupCount=len(lookups)


def symbol_aliases(font, aliases):
    cmap=font.getBestCmap()
    for alias, source in aliases.items():
        cp, donor=int(alias,16),int(source,16)
        if donor not in cmap:raise ValueError(f'Missing alias source {source}')
        for table in font['cmap'].tables:
            if table.isUnicode() and table.format != 14:table.cmap[cp]=cmap[donor]

def height_axis(font, source_order, spec):
    from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance
    from fontTools.ttLib.tables.TupleVariation import TupleVariation
    axis=spec['heightAxis'];tag=axis['tag'];values=axis['values'];default=axis['default']
    font['fvar']=newTable('fvar');a=Axis();a.axisTag=tag;a.minValue=min(values);a.defaultValue=default;a.maxValue=max(values);a.flags=0;a.axisNameID=font['name'].addName('Glyph height (%)');font['fvar'].axes=[a];font['fvar'].instances=[]
    for value in values:
        i=NamedInstance();i.subfamilyNameID=font['name'].addName(f'Height {value}%');i.coordinates={tag:value};i.postscriptNameID=0xffff;font['fvar'].instances.append(i)
    font['gvar']=newTable('gvar');font['gvar'].variations={n:[] for n in font.getGlyphOrder()}
    for name in font.getGlyphOrder()[:len(source_order)]:
        glyph=font['glyf'][name]
        if not glyph.numberOfContours:continue
        coords,_,_=glyph.getCoordinates(font['glyf'])
        for endpoint,support in [(min(values),(-1,-1,0)),(max(values),(0,1,1))]:
            delta=[(0,round(y*endpoint/default)-y) for x,y in coords]+[(0,0)]*4
            font['gvar'].variations[name].append(TupleVariation({tag:support},delta))
    # Vertical safety envelope; horizontal metrics and donor outlines never vary.
    for table,fields in [('hhea',['ascent','descent']),('OS/2',['sTypoAscender','sTypoDescender','usWinAscent','usWinDescent'])]:
        for field in fields:setattr(font[table],field,round(getattr(font[table],field)*max(values)/default))


def build(config,output):
    output.mkdir(parents=True,exist_ok=True);emoji,emoji_report=emoji_file(config['emoji'],output)
    catalog=json.loads((ROOT/'sources/catalog.json').read_text())['sources'];records=json.loads((ROOT/'sources/geist-mixed/sources.json').read_text())
    for r in records:checked((input_path('sources/geist-mixed/'+r['file']) if r['file'].endswith(('.ttf','.woff2')) else ROOT/'sources/geist-mixed'/r['file']),r['sha256'])
    paths={'pixel':checked(input_path('sources/geist-mixed/GeistPixel-Variable.ttf'),config['pixelSourceSha256']),'mono':input_path('sources/geist-mixed/GeistMono-Variable.ttf'),'doto':checked(input_path(catalog['doto']['path']),catalog['doto']['sha256'])};cubic=checked(input_path(catalog['cubic11']['path']),catalog['cubic11']['sha256']);nerd=input_path('sources/geist-mixed/SymbolsNerdFontMono-Regular.ttf')
    license_dir=output/'licenses';license_dir.mkdir(exist_ok=True)
    for rel in ['sources/OFL.txt','sources/Cubic11-OFL.txt','sources/Noto3D-OFL.txt','sources/geist-mixed/Geist-OFL.txt','sources/geist-mixed/GeistPixelVariable-OFL.txt']:
        p=ROOT/rel;(license_dir/p.name).write_bytes(p.read_bytes())
    # All original component notices for the complete Nerd donor.
    for p in (ROOT/'sources/coverage/NerdFonts/licenses').glob('*'):
        if p.is_file():(license_dir/p.name).write_bytes(p.read_bytes())
    report={'version':config['version'],'recipe':config,'emoji':emoji_report,'inputs':{k:{'file':str(v.relative_to(INPUT_ROOT)),'sha256':sha(v)}for k,v in {**paths,'cubic11':cubic,'nerd':nerd}.items()},'sources':{'text':[r for r in records if r['file'] in {'GeistPixel-Variable.ttf','GeistPixelVariable-OFL.txt','GeistMono-Variable.ttf','Geist-OFL.txt','SymbolsNerdFontMono-Regular.ttf'}],**catalog,'emoji':json.loads((ROOT/'sources/emoji3d.json').read_text())},'assets':[]}
    prior=json.loads((output/'provenance.json').read_text())if(output/'provenance.json').exists()else{}
    for spec in config['fonts']:
        name=spec['family']
        existing=next((a for a in prior.get('assets',[])if a['family']==name),None)
        if existing and prior.get('recipe')==config and prior.get('emoji')==emoji_report and all((output/existing[k]).exists()and sha(output/existing[k])==existing[k+'Sha256']for k in ['ttf','woff2']):
            report['assets'].append(existing);print('verified unchanged',name,flush=True);continue
        print('building',name,flush=True)
        with tempfile.TemporaryDirectory(prefix='final-font-')as temp:
            work=Path(temp);original=TTFont(paths[spec['source']],recalcTimestamp=False)
            variable=spec.get('variableWeight')
            text=instantiateVariableFont(original,spec.get('axes',{'wght':400}),inplace=False)
            text.flavor=None;text.save(work/'source.ttf');text=TTFont(work/'source.ttf',recalcTimestamp=False)
            if spec.get('height'):height_only(text,spec['height'])
            expected=core.outlines(text);metrics=dict(text['hmtx'].metrics);source_order=text.getGlyphOrder()[:]
            text=add_missing(text,nerd,work,'nerd');text=add_missing(text,cubic,work,'cubic')
            text,em=with_emoji(text,emoji,config['emoji']['targetPpem'],work)
            finalize_layout(text)
            rename(text,name)
            symbol_aliases(text,config['symbolAliases'])
            if spec.get('heightAxis'):height_axis(text,source_order,spec)
            if variable:restore_variation(text,original)
            ttf=output/(name+'.ttf');text.flavor=None;text.save(ttf);reread=TTFont(ttf,recalcTimestamp=False)
            assert reread['name'].getDebugName(1)==name
            assert set(TTFont(cubic).getBestCmap()).issubset(reread.getBestCmap())
            for weight in ([100,400,700,900]if variable else [400]):
                actual=instantiateVariableFont(reread,{'wght':weight},inplace=False)if variable else reread
                actual.flavor=None;actual.save(work/'actual.ttf');actual=TTFont(work/'actual.ttf')
                reference=instantiateVariableFont(original,{'wght':weight},inplace=False)if variable else None
                if reference:
                    # Reload to normalize composite representation before comparison.
                    reference.flavor=None;reference.save(work/'reference.ttf');reference=TTFont(work/'reference.ttf');exp=core.outlines(reference);met=reference['hmtx'].metrics;order=reference.getGlyphOrder()
                else:exp=expected;met=metrics;order=source_order
                got=core.outlines(actual);amap=actual.getBestCmap();rcmap=(reference if reference else TTFont(work/'source.ttf')).getBestCmap()
                for cp,old in rcmap.items():
                    if cp in em.get('sourceCoverage',[])and cp>=128:continue
                    new=amap[cp]
                    if got[new]!=exp[old]or actual['hmtx'].metrics[new]!=met[old]:raise ValueError(f'Source geometry/metrics changed {name} {weight} U+{cp:04X}')
            reread.flavor='woff2';woff=output/(name+'.woff2');reread.save(woff)
            for p in [ttf,woff]:
                if p.stat().st_size>config['emoji']['maxFontBytes']:raise ValueError('Font exceeds recipe budget: '+str(p))
            report['assets'].append({'family':name,'ttf':ttf.name,'woff2':woff.name,'ttfBytes':ttf.stat().st_size,'woff2Bytes':woff.stat().st_size,'ttfSha256':sha(ttf),'woff2Sha256':sha(woff),'variableWeight':variable,'commonScriptEmojiComposition':True,'heightAxis':spec.get('heightAxis'),'sourceGeometryAndHorizontalMetricsVerified':True,'emojiCmapCodepoints':len(em['sourceCoverage']),'bitmapGlyphs':em['bitmapGlyphs']})
            write(output/'provenance.json',report)
    write(output/'provenance.json',report)
    (output/'NOTICE.md').write_text('Owner-selected final font families. Derived from pinned Geist, Doto, Cubic 11, Nerd Fonts and Noto 3D originals. Doto HGHT 105/110/115/120%, default110%; horizontal metrics unchanged. U+EA00 aliases the pinned Nerd Twitter bird U+F099. Chinese unchanged after UPEM normalization. Noto full cmap/GSUB retained; PNGs Lanczos-resampled with alpha and a 256-color per-image palette at 28 PPEM. Original licenses accompany every redistribution.\n')
    print(json.dumps(report['assets'],indent=2),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'Final');args=p.parse_args();build(json.loads((ROOT/'final_fonts.json').read_text()),args.output)
if __name__=='__main__':main()
