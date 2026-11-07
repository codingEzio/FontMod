#!/usr/bin/env python3
"""Exact platform adapters: outline text plus a shared full Emoji3D fallback.

Android treats an sbix/CBDT face as bitmap-only on the tested device. Separate
text and emoji providers avoid blank outlines, while retaining all original
emoji sequences. macOS-installed families remain fully merged sbix fonts.
"""
from pathlib import Path
import hashlib,json
from fontTools.ttLib import TTFont
from final_fonts import ROOT,sha,write,symbol_aliases
from color_cbdt import add_cbdt

def build(departure_build=None):
 from departure_input import resolve, retain
 departure, departure_report = resolve(departure_build)
 out=ROOT/'Final/web';out.mkdir(exist_ok=True)
 recipe=json.loads((ROOT/'final_fonts.json').read_text());mixed=json.loads((ROOT/'Final/provenance.json').read_text())
 emoji=TTFont(ROOT/'Final/Emoji3D-Production.ttf',recalcTimestamp=False);emoji_points=set(emoji.getBestCmap())-set(range(128))
 records=[]
 source=[ROOT/'Final'/r['ttf'] for r in mixed['assets']]+[departure/n for n in ['DeparturePixelZh-Regular.ttf','DeparturePixelZhCompact-Regular.ttf']]
 prior_path=out/'provenance.json'
 if prior_path.exists():
  prior=json.loads(prior_path.read_text());assets=prior.get('assets',[])
  if (prior.get('recipe')==recipe and len(assets)==9
      and all(any(a.get('sourceSha256')==sha(path) and a.get('ttf')==path.name for a in assets) for path in source)
      and next((a['ttfSha256'] for a in assets if a['family']=='Emoji3D'),None)==sha(ROOT/'Final/Emoji3D-Production.ttf')
      and all((ROOT/'Final'/a[k]).is_file() and sha(ROOT/'Final'/a[k])==a[k+'Sha256'] for a in assets if a['family'].startswith('DeparturePixelZh') for k in ['ttf','woff2'])
      and all((out/a[k]).exists() and sha(out/a[k])==a[k+'Sha256'] for a in assets for k in ['ttf','woff2'])):
   retain(departure, departure_report)
   print('Verified unchanged platform adapters: seven text families + full shared emoji');return
 for path in source:
  font=TTFont(path,recalcTimestamp=False);family=font['name'].getDebugName(16)or font['name'].getDebugName(1)
  symbol_aliases(font,recipe['symbolAliases'])
  # Retain the merged departure family, with the owner's requested bird alias,
  # as the desktop install/bundle source too. No source recipe is modified.
  if path.parent==departure:
   font.flavor=None;font.save(ROOT/'Final'/path.name);font.flavor='woff2';font.save(ROOT/'Final'/path.with_suffix('.woff2').name)
  font.flavor=None
  for tag in ['sbix','CBDT','CBLC','COLR','CPAL']:
   if tag in font:del font[tag]
  if 'sbix'in TTFont(path):
   for table in font['cmap'].tables:
    if table.format==14:table.uvsDict={}
    elif table.isUnicode():table.cmap={cp:g for cp,g in table.cmap.items() if cp not in emoji_points}
  ttf=out/path.name;font.save(ttf);font.flavor='woff2';woff=ttf.with_suffix('.woff2');font.save(woff)
  reread=TTFont(ttf);assert reread.getBestCmap()[0xEA00]==reread.getBestCmap()[0xF099]
  assert not any(tag in reread for tag in ['sbix','CBDT','CBLC'])
  records.append({'family':family,'ttf':ttf.name,'woff2':woff.name,'sourceSha256':sha(path),'ttfSha256':sha(ttf),'woff2Sha256':sha(woff),'ttfBytes':ttf.stat().st_size,'woff2Bytes':woff.stat().st_size})
 retain(departure, departure_report)
 # Keep one source-repertoire emoji face. The ASCII points are required by the
 # keycap GSUB rules, so it is used only by explicit emoji spans/native fallback.
 for android in [False,True]:
  font=TTFont(ROOT/'Final/Emoji3D-Production.ttf',recalcTimestamp=False)
  if android:add_cbdt(font)
  stem='Emoji3D-Android'if android else'Emoji3D';ttf=out/(stem+'.ttf');font.flavor=None;font.save(ttf);font.flavor='woff2';woff=out/(stem+'.woff2');font.save(woff)
  records.append({'family':stem,'ttf':ttf.name,'woff2':woff.name,'ttfSha256':sha(ttf),'woff2Sha256':sha(woff),'ttfBytes':ttf.stat().st_size,'woff2Bytes':woff.stat().st_size,'fullEmojiRepertoire':True})
 write(out/'provenance.json',{'schemaVersion':1,'recipe':recipe,'policy':'outline text plus full shared sbix / Android CBDT Emoji3D fallback','assets':records});print(json.dumps(records,indent=2))
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--departure-build',type=Path)
 build(parser.parse_args().departure_build)
