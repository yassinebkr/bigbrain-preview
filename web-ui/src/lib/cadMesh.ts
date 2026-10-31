/** Reject oversized or malformed STL input before allocating GPU resources. */
export function inspectStl(buffer: ArrayBuffer): number {
  if (!buffer.byteLength || buffer.byteLength > 32 * 1024 * 1024) throw new Error('Maillage vide ou trop volumineux');
  if (buffer.byteLength >= 84) {
    const count = new DataView(buffer).getUint32(80, true);
    if (84 + count * 50 === buffer.byteLength) {
      if (!count || count > 250000) throw new Error('Limite de 250 000 triangles dépassée');
      return count;
    }
  }
  const text = new TextDecoder().decode(buffer);
  const facets = text.match(/\bfacet\s+normal\b/g)?.length || 0;
  const vertices = text.match(/\bvertex\s+/g)?.length || 0;
  if (!text.trimStart().startsWith('solid') || !text.trimEnd().endsWith('endsolid') && !/endsolid[^\n]*\s*$/.test(text)
    || !facets || facets > 250000 || vertices !== facets * 3) throw new Error('Maillage STL invalide ou trop complexe');
  return facets;
}
