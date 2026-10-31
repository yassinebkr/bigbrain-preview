import { describe, expect, it } from 'vitest';
import { inspectStl } from './cadMesh';

describe('bounded STL inspection', () => {
  it('accepts binary STL including a solid-prefixed header', () => {
    const buffer = new ArrayBuffer(134);
    new Uint8Array(buffer).set(new TextEncoder().encode('solid binary'));
    new DataView(buffer).setUint32(80, 1, true);
    expect(inspectStl(buffer)).toBe(1);
  });
  it('accepts a complete ASCII triangle', () => {
    const text = 'solid piece\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid piece';
    expect(inspectStl(new TextEncoder().encode(text).buffer)).toBe(1);
  });
  it('rejects empty, truncated, over-budget and malformed input', () => {
    for (const buffer of [new ArrayBuffer(0), new ArrayBuffer(84), new ArrayBuffer(32 * 1024 * 1024 + 1),
      new TextEncoder().encode('solid empty\nendsolid').buffer]) expect(() => inspectStl(buffer)).toThrow();
    const oversized = new ArrayBuffer(84 + 250001 * 50);
    new DataView(oversized).setUint32(80, 250001, true);
    expect(() => inspectStl(oversized)).toThrow();
  });
});
