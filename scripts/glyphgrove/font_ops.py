import copy, hashlib, io, json
from pathlib import Path
from fontTools.ttLib import TTFont
from PIL import Image
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def checked(p,h):
    if sha(p)!=h:raise ValueError('Source digest mismatch: '+str(p))
    return p

def png_resize(raw, factor, colors=256):
    """Keep alpha and 3D appearance with a bounded palette per small glyph."""
    from PIL import Image
    image=Image.open(io.BytesIO(raw)).convert("RGBA")
    image=image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.LANCZOS)
    image=image.quantize(colors=colors,method=Image.Quantize.FASTOCTREE,dither=Image.Dither.NONE)
    buffer=io.BytesIO();image.save(buffer,format="PNG",optimize=True,compress_level=9)
    return buffer.getvalue()

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
