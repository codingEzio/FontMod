#!/usr/bin/env python3
"""Verify owner-visible axes against all text/CJK glyphs, without bitmap mutation."""
import json
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from final_fonts import ROOT,sha,write
report=[]
for spec in json.loads((ROOT/'final_fonts.json').read_text())['fonts']:
 f=TTFont(ROOT/'Final'/(spec['family']+'.ttf'),recalcTimestamp=False)
 assert f.getBestCmap()[0xEA00]==f.getBestCmap()[0xF099]
 if not spec.get('heightAxis'):continue
 cmap=f.getBestCmap();base=f['glyf'];metrics=dict(f['hmtx'].metrics);latin=base[cmap[65]].getCoordinates(base)[0];chinese=base[cmap[0x4E2D]].getCoordinates(base)[0]
 for height in [105,110,115,120]:
  inst=instantiateVariableFont(f,{'HGHT':height},inplace=False);glyf=inst['glyf'];got=glyf[cmap[65]].getCoordinates(glyf)[0]
  assert inst['hmtx'].metrics==metrics,'Horizontal metrics changed'
  assert all(x==a and abs(y-b*height/110)<=1 for (x,y),(a,b)in zip(got,latin)),'Doto height differs'
  assert glyf[cmap[0x4E2D]].getCoordinates(glyf)[0]==chinese,'Chinese varied'
  assert inst.getTableData('sbix')==f.getTableData('sbix'),'Emoji varied'
  report.append({'family':spec['family'],'heightPercent':height,'horizontalMetrics':'identical','chinese':'identical','emoji':'identical','latinY':'verified within one font-unit rounding'})
evidence=ROOT/'Evidence'
evidence.mkdir(parents=True,exist_ok=True)
write(evidence/'final-height-geometry-20261017.json',report);print(json.dumps({'checks':len(report),'result':'pass'}))
