"""Preserve sbix PNG pixels and outline text in Android's CBDT/CBLC container."""
import struct
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables import C_B_D_T_,E_B_L_C_,BitmapGlyphMetrics
from fontTools.misc import sstruct

def add_cbdt(font,keep_sbix=False):
 strike=next(iter(font['sbix'].strikes.values()));ppem=strike.ppem;glyphs={}
 for name,glyph in strike.glyphs.items():
  if glyph.graphicType!='png ':continue
  width,height=struct.unpack_from('>II',glyph.imageData,16)
  bitmap=C_B_D_T_.cbdt_bitmap_format_17(None,None);metric=BitmapGlyphMetrics.SmallGlyphMetrics()
  metric.width=width;metric.height=height;metric.BearingX=glyph.originOffsetX;metric.BearingY=glyph.originOffsetY+height;metric.Advance=round(font['hmtx'].metrics[name][0]*ppem/font['head'].unitsPerEm)
  bitmap.metrics=metric;bitmap.imageData=glyph.imageData;glyphs[name]=bitmap
 cbdt=newTable('CBDT');cbdt.version=3.0;cbdt.strikeData=[glyphs];font['CBDT']=cbdt
 cblc=newTable('CBLC');cblc.version=3.0
 table=E_B_L_C_.Strike();size=E_B_L_C_.BitmapSizeTable();table.bitmapSizeTable=size
 size.colorRef=0;size.ppemX=size.ppemY=ppem;size.bitDepth=32;size.flags=1
 for direction in ['hori','vert']:
  metrics=E_B_L_C_.SbitLineMetrics()
  for field in sstruct.getformat(E_B_L_C_.sbitLineMetricsFormat)[1]:setattr(metrics,field,0)
  metrics.ascender=ppem;metrics.descender=-round(ppem*.25);metrics.widthMax=max(g.metrics.width for g in glyphs.values());metrics.caretSlopeNumerator=1
  setattr(size,direction,metrics)
 index=E_B_L_C_.eblc_index_sub_table_1(None,None);index.indexFormat=1;index.imageFormat=17;index.imageDataOffset=4;index.names=sorted(glyphs,key=font.getGlyphID);table.indexSubTables=[index];cblc.strikes=[table];font['CBLC']=cblc
 if not keep_sbix:del font['sbix']
 return font
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination');p.add_argument('--keep-sbix',action='store_true');a=p.parse_args();font=TTFont(a.source,recalcTimestamp=False);add_cbdt(font,a.keep_sbix);font.save(a.destination)
