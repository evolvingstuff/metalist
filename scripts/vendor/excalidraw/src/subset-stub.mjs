// MetaList replacement for Excalidraw's font-subsetting chunks.
// Subsetting compiles WebAssembly, which MetaList's Content-Security-Policy does not allow.
// Exports therefore embed each needed font file whole (a few KB to 25 KB per file).
export const Commands = { Subset: 'SUBSET' };

export function toBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(offset, offset + 0x8000));
  }
  return `data:font/woff2;base64,${btoa(binary)}`;
}

export async function subsetToBase64(arrayBuffer) {
  return toBase64(arrayBuffer);
}

export async function subsetToBinary(arrayBuffer) {
  return arrayBuffer;
}

export const WorkerUrl = undefined;
