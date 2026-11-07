// BEGIN FINAL FONT PACK
// Exact producer TTF bytes, deduplicated for VIA's bounded native importer.
(() => {
  const id="__FONT_PACK_ID__";
  if(globalThis.ExtensionFinalFonts?.id===id)return;
  const encoded="__FONT_PACK_BASE64__";
  let pending;
  async function unpack(){
    if(!pending)pending=(async()=>{
      if(typeof DecompressionStream!=="function")throw Error("Offline font decoding is unavailable");
      const compressed=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
      const data=new Uint8Array(await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer());
      const size=new DataView(data.buffer).getUint32(0),metadata=JSON.parse(new TextDecoder().decode(data.subarray(4,4+size)));
      const offsets=[];let offset=4+size;
      for(const length of metadata.lengths){offsets.push(offset);offset+=length;}
      if(offset!==data.length)throw Error("Offline font payload length differs");
      return {data,metadata,offsets};
    })();
    return pending;
  }
  async function bytes(family){
    const {data,metadata,offsets}=await unpack(),font=metadata.fonts[family];
    if(!font)throw Error("Unknown final font: "+family);
    const result=new Uint8Array(font.bytes);let offset=0;
    for(const index of font.segments){const length=metadata.lengths[index];result.set(data.subarray(offsets[index],offsets[index]+length),offset);offset+=length;}
    if(offset!==font.bytes)throw Error("Final font reconstruction length differs");
    if(globalThis.crypto?.subtle){const digest=[...new Uint8Array(await crypto.subtle.digest("SHA-256",result))].map(n=>n.toString(16).padStart(2,"0")).join("");if(digest!==font.sha256)throw Error("Final font reconstruction hash differs");}
    return result;
  }
  globalThis.ExtensionFinalFonts=Object.freeze({id,bytes});
})();
// END FINAL FONT PACK
