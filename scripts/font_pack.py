#!/usr/bin/env python3
"""Lossless offline VIA transport. Share identical glyph/PNG blocks; reconstruct exact producer TTF bytes."""
import argparse,base64,gzip,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def build(final=None):
 directory=Path(final) if final is not None else ROOT/'Final'
 platform=json.loads((directory/'web/provenance.json').read_text())
 manifest={'fonts':[{'family':a['family'],'file':a['woff2']}for a in platform['assets'] if not a['family'].startswith('Emoji3D')]}
 blocks=[];ids={};fonts={}
 for f in [*manifest['fonts'],{'family':'Extension Emoji3D','file':'Emoji3D-Android.woff2'}]:
  p=directory/'web'/f['file'].replace('.woff2','.ttf')
  b=p.read_bytes();tables={}
  for i in range(struct.unpack_from('>H',b,4)[0]):
   tag,_,off,size=struct.unpack_from('>4sIII',b,12+i*16);tables[tag]=(off,size)
  points={0,len(b)}
  for off,size in tables.values():points.update([off,off+size])
  nglyph=struct.unpack_from('>H',b,tables[b'maxp'][0]+4)[0]
  if b'glyf'in tables:
   long=struct.unpack_from('>h',b,tables[b'head'][0]+50)[0];lo=tables[b'loca'][0];go=tables[b'glyf'][0]
   for i in range(nglyph+1):points.add(go+struct.unpack_from('>I'if long else'>H',b,lo+i*(4 if long else 2))[0]*(1 if long else 2))
  if b'sbix'in tables:
   off,_=tables[b'sbix']
   for i in range(struct.unpack_from('>I',b,off+4)[0]):
    strike=off+struct.unpack_from('>I',b,off+8+4*i)[0];points.add(strike)
    for j in range(nglyph+1):points.add(strike+struct.unpack_from('>I',b,strike+4+4*j)[0])
  points=sorted(points);segments=[]
  for a,z in zip(points,points[1:]):
   chunk=b[a:z];h=sha(chunk)
   if h not in ids:ids[h]=len(blocks);blocks.append(chunk)
   segments.append(ids[h])
  rebuilt=b''.join(blocks[i]for i in segments)
  if rebuilt!=b:raise ValueError('Font block readback differs')
  fonts[f['family']]={'segments':segments,'sha256':sha(b),'bytes':len(b)}
 metadata=json.dumps({'lengths':[len(b)for b in blocks],'fonts':fonts},separators=(',',':')).encode();payload=struct.pack('>I',len(metadata))+metadata+b''.join(blocks);compressed=gzip.compress(payload,compresslevel=9,mtime=0)
 js=(ROOT/'scripts/font_pack_runtime.js').read_text().replace('__FONT_PACK_BASE64__',base64.b64encode(compressed).decode()).replace('__FONT_PACK_ID__',sha(compressed))
 out=directory/'via-font-pack.js';out.write_text(js)
 report={'schemaVersion':1,'encoding':'gzip of content-addressed original sfnt blocks','fonts':{k:{a:v[a]for a in ['sha256','bytes']}for k,v in fonts.items()},'uniqueBlocks':len(blocks),'rawBytes':len(payload),'gzipBytes':len(compressed),'scriptBytes':out.stat().st_size,'sha256':sha(out.read_bytes()),'exactByteReconstructionVerified':True}
 (directory/'via-font-pack.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in ['uniqueBlocks','gzipBytes','scriptBytes','exactByteReconstructionVerified']}))
if __name__=='__main__':build()
