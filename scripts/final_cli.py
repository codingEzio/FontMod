#!/usr/bin/env python3
"""The final font catalog, verification and portable bundle entry point."""
import argparse, hashlib, json, shutil, subprocess, sys, zipfile
from pathlib import Path
from fontTools.ttLib import TTFont
import final_fonts
ROOT=final_fonts.ROOT

def read():return json.loads((ROOT/'Final/provenance.json').read_text())
def entries():
    report=read();out=[]
    for a in report['assets']:
        out.append({'family':a['family'],'file':'Final/'+a['woff2'],'expectedSha256':a['woff2Sha256'],'bundleAdapter':'final','sourceLabel':'Pinned Geist/Doto + Nerd + Cubic11 + Noto3D full repertoire','bundleName':a['family']})
    dep=ROOT/'Final'
    for name in ['DeparturePixelZh-Regular','DeparturePixelZhCompact-Regular']:
        p=dep/(name+'.woff2');f=TTFont(p);family=f['name'].getDebugName(16)or f['name'].getDebugName(1)
        out.append({'family':family,'file':str(p),'expectedSha256':final_fonts.sha(p),'bundleAdapter':'departure','bundleName':family,'sourceLabel':'Departure Mono + Cubic11 + Nerd'})
    return out

def check():
    r=read();assert r['recipe']==json.loads((ROOT/'final_fonts.json').read_text()),'Recipe changed'
    assert len(r['assets'])==5
    for a in r['assets']:
        for ext in ['ttf','woff2']:
            p=ROOT/'Final'/a[ext];assert final_fonts.sha(p)==a[ext+'Sha256'],p
            f=TTFont(p);assert f['name'].getDebugName(1)==a['family']
            expected=[('wght',100,400,900)] if a['variableWeight'] else [('HGHT',105,110,120)] if a.get('heightAxis') else []
            assert [(x.axisTag,x.minValue,x.defaultValue,x.maxValue)for x in f['fvar'].axes]==expected if expected else 'fvar'not in f
            assert f.getBestCmap()[0xEA00]==f.getBestCmap()[0xF099]
            assert set(f['sbix'].strikes)=={r['recipe']['emoji']['targetPpem']}
    print(json.dumps({'fonts':len(entries()),'mixed':len(r['assets']),'hashes':'pass','variableWeight':'100–900','emoji':r['emoji']},ensure_ascii=False))

def native_manifest():
    result=[]
    for a in read()['assets']:
        f=TTFont(ROOT/'Final'/a['ttf']);result.append({'name':f['name'].getDebugName(6),'family':a['family'],'file':str(ROOT/'Final'/a['ttf']),'sha256':a['ttfSha256'],'sample':{'latin':'ABC xyz 0123456789 — !?','mixed':'ABC xyz 0123 中文简体 繁體 ㄅㄆㄇ 𠊎','requireMixedCoverage':True},'probes':[{'text':'\uf120'},{'text':'\uea00','glyphCount':1},{'text':'😀','glyphCount':1},{'text':'👩🏽‍💻','glyphCount':1},{'text':'🇹🇼','glyphCount':1},{'text':'1️⃣','glyphCount':1}]})
    for filename in ['DeparturePixelZh-Regular.ttf','DeparturePixelZhCompact-Regular.ttf']:
        file=ROOT/'Final'/filename;f=TTFont(file);result.append({'name':f['name'].getDebugName(6),'family':f['name'].getDebugName(16)or f['name'].getDebugName(1),'file':str(file),'sha256':final_fonts.sha(file),'sample':{'latin':'ABC xyz 0123','mixed':'中文简体 繁體','requireMixedCoverage':True},'probes':[{'text':'\uea00','glyphCount':1}]})
    p=ROOT/'Final/native-manifest.json';final_fonts.write(p,result);return p

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['build','check','catalog','bundle','rename-candidate','release-export','install','installed']);p.add_argument('--departure-build',type=Path);p.add_argument('--no-open',action='store_true');p.add_argument('--no-serve',action='store_true');p.add_argument('--include-archived',action='store_true',help='Compatibility flag: retired fonts are no longer in this catalog');p.add_argument('--preview-port',type=int,default=56134);p.add_argument('--font');p.add_argument('--variants');p.add_argument('--target',choices=['web','extension','both'],default='both');p.add_argument('--match',action='append',default=[]);p.add_argument('--output',type=Path);p.add_argument('--zip',action='store_true');p.add_argument('--list-fonts',action='store_true');p.add_argument('--source-revision');p.add_argument('--from-final',type=Path);p.add_argument('--departure-source',type=Path,default=ROOT/'dependencies/font-preset');p.add_argument('--departure-builder-source',type=Path,default=ROOT/'dependencies/font-builder');a=p.parse_args()
    if a.command=='rename-candidate':
        if a.from_final is None or a.output is None:p.error('rename-candidate requires --from-final and a new --output directory')
        import release
        print(json.dumps(release.rename_candidate(ROOT,a.from_final,a.output)));return
    if a.departure_build is not None and a.command != 'build':p.error('--departure-build belongs to build')
    if a.command=='build':
        from departure_input import resolve
        resolve(a.departure_build)
        final_fonts.build(json.loads((ROOT/'final_fonts.json').read_text()),ROOT/'Final')
        import platform_fonts,font_pack
        platform_fonts.build(a.departure_build);font_pack.build();return
    check()
    if a.command=='check':return
    if a.command=='release-export':
        if a.output is None:p.error('release-export requires a new --output directory')
        import release
        print(json.dumps(release.export(ROOT,a.output,a.source_revision,[a.departure_source,a.departure_builder_source])));return
    extras=entries()
    if a.command=='catalog':
        import font_preview
        for e in extras:e['file']=str(ROOT/e['file'])if not Path(e['file']).is_absolute()else e['file']
        result=font_preview.prepare_local(ROOT,[],extras)if a.no_serve else font_preview.open_catalog(ROOT,[],extras,port=a.preview_port,open_browser=not a.no_open)
        print(json.dumps(result));return
    if a.command in ['install','installed']:
        manifest=native_manifest();subprocess.run(['swift','-module-cache-path',str(ROOT/'.cache'/('swift-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:10])),str(ROOT/'scripts/native.swift'),a.command,str(manifest)],check=True);return
    import font_bundle
    catalog=font_bundle.catalog(ROOT)
    if a.list_fonts:print('\n'.join(x['family']for x in catalog));return
    if not a.font:
        for i,e in enumerate(catalog,1):print(f"{i}. {e['family']}")
        a.font=catalog[int(input('Font number: '))-1]['family']
    entry=next((e for e in catalog if e['family']==a.font),None)
    if not entry:raise ValueError('Unknown final font: '+a.font)
    styles=font_bundle.select_styles(entry,a.variants.split(',')if a.variants else [])
    dest=a.output or ROOT/'Deliveries/CustomBundles'/a.font
    print(json.dumps(font_bundle.export(ROOT,entry,styles,dest,target=a.target,matches=a.match,archive=a.zip)))
if __name__=='__main__':main()
