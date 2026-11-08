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
    # The experimental local profile is intentionally absent from the separate
    # public source export; the existing final catalog remains independent.
    local_profile=True
    commands=['build','check','catalog','bundle','rename-candidate','release-export','install','installed']+(['verify-native','compact','derive-trials'] if local_profile else [])
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=commands)
    p.add_argument('--profile',choices=['final','rysamix'] if local_profile else ['final'],default='final')
    if local_profile:
        p.add_argument('--deep',action='store_true')
        p.add_argument('--misans-source',type=Path)
        p.add_argument('--replace-from',type=Path)
        p.add_argument('--source-build',type=Path)
        p.add_argument('--emoji-cache',type=Path)
    else:
        p.set_defaults(deep=False,misans_source=None,replace_from=None,source_build=None,emoji_cache=None)
    p.add_argument('--departure-build',type=Path);p.add_argument('--no-open',action='store_true');p.add_argument('--no-serve',action='store_true');p.add_argument('--include-archived',action='store_true',help='Compatibility flag: retired fonts are no longer in this catalog');p.add_argument('--preview-port',type=int,default=56134);p.add_argument('--font');p.add_argument('--variants');p.add_argument('--target',choices=['web','extension','both'],default='both');p.add_argument('--match',action='append',default=[]);p.add_argument('--output',type=Path);p.add_argument('--zip',action='store_true');p.add_argument('--list-fonts',action='store_true');p.add_argument('--source-revision');p.add_argument('--from-final',type=Path);p.add_argument('--departure-source',type=Path,default=ROOT/'dependencies/font-preset');p.add_argument('--departure-builder-source',type=Path,default=ROOT/'dependencies/font-builder');a=p.parse_args()
    if a.profile=='rysamix':
        if final_fonts.INPUT_ROOT.is_relative_to(ROOT):p.error('RysaMix requires FONTMOD_INPUT_ROOT outside the source checkout')
        if a.command not in ['build','compact','derive-trials','bundle','check','verify-native','install','installed']:p.error('This local profile supports build, compact, derive-trials, bundle, check, verify-native, install and installed')
        if a.output is None:p.error('RysaMix requires an explicit --output directory')
        if a.output.expanduser().resolve().is_relative_to(ROOT):p.error('RysaMix output must be outside the source checkout')
        if a.misans_source is not None and a.command!='build':p.error('--misans-source belongs to RysaMix build')
        if a.replace_from is not None and a.command!='install':p.error('--replace-from belongs to RysaMix install')
        if a.departure_build is not None:p.error('--departure-build is not used by RysaMix')
        if a.deep and a.command!='check':p.error('--deep belongs to RysaMix check')
        if a.command=='compact' and (a.source_build is None or a.emoji_cache is None):p.error('RysaMix compact requires --source-build and --emoji-cache')
        if a.command=='derive-trials' and a.source_build is None:p.error('RysaMix derive-trials requires --source-build')
        if a.command=='bundle' and a.source_build is None:p.error('RysaMix bundle requires --source-build')
        if a.command not in ['compact','derive-trials','bundle'] and a.source_build is not None:p.error('--source-build belongs to RysaMix compact, derive-trials or bundle')
        if a.command!='compact' and a.emoji_cache is not None:p.error('--emoji-cache belongs to RysaMix compact')
        import rysa_mono
        if a.command=='derive-trials':rysa_mono.derive_trials(a.source_build,a.output);return
        if a.command=='compact':rysa_mono.compact(a.source_build,a.emoji_cache,a.output);return
        if a.command=='bundle':
            if a.target!='web':p.error('RysaMix currently exports --target web only')
            if a.match or a.font or a.variants or a.list_fonts:p.error('RysaMix web bundle includes both families and styles')
            import rysa_web_bundle
            rysa_web_bundle.export(a.source_build,a.output,archive=a.zip);return
        if a.command=='build':rysa_mono.build(a.output,a.misans_source);return
        report=rysa_mono.check(a.output)
        if a.deep:rysa_mono.deep_check(a.output,report)
        if a.command!='check':rysa_mono.native('bundled' if a.command=='verify-native' else a.command,a.output,report,a.replace_from)
        return
    if a.deep:p.error('--deep belongs to the RysaMix profile')
    if a.misans_source is not None:p.error('--misans-source belongs to the RysaMix profile')
    if a.replace_from is not None:p.error('--replace-from belongs to the RysaMix profile')
    if a.source_build is not None or a.emoji_cache is not None:p.error('--source-build and --emoji-cache belong to the RysaMix profile')
    if a.command=='verify-native':p.error('verify-native requires --profile rysamix')
    if a.command in ['compact','derive-trials']:p.error('This command requires --profile rysamix')
    if a.command=='rename-candidate':
        if a.from_final is None or a.output is None:p.error('rename-candidate requires --from-final and a new --output directory')
        import release
        print(json.dumps(release.rename_candidate(ROOT,a.from_final,a.output)));return
    if a.departure_build is not None and a.command != 'build':p.error('--departure-build belongs to build')
    if a.command=='build':
        if (ROOT/'Final').resolve().is_relative_to(ROOT):p.error('Final must point to a directory outside the source checkout')
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
    dest=a.output or ROOT/'Final/Bundles'/a.font
    if dest.expanduser().resolve().is_relative_to(ROOT):p.error('Bundle output must be outside the source checkout')
    print(json.dumps(font_bundle.export(ROOT,entry,styles,dest,target=a.target,matches=a.match,archive=a.zip)))
if __name__=='__main__':main()
