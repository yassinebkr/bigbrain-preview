/** Bind direct preview meshes to their native checkpoint and delivery state. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cadMeshSource, cadUpdate, cadWorkingMesh, type CadView } from './cad';

async function fixture() {
  const bytes = new TextEncoder().encode('synthetic STL transport bytes');
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hash = Array.from(digest).map(value => value.toString(16).padStart(2, '0')).join('');
  const native = { path: 'execution-checkpoints/head/part.sc', format: 'solidcraft' as const,
    sha256: 'b'.repeat(64), size_bytes: 100, source_sha256: null };
  const cad: CadView = { schema_version: '1.0', document_id: 'a'.repeat(32), title: 'Fixture',
    sequence: 1, status: 'modeling', elapsed_seconds: 1, snapshot: null, diagnostic: null,
    working: { checkpoint_id: 'c'.repeat(32), parent: null, contract_sha256: 'd'.repeat(64),
      engine_version: '0.28.0', engine_sha256: 'e'.repeat(64), accepted_steps: 1, native,
      mesh: { path: 'execution-checkpoints/head/part.stl', format: 'stl', sha256: hash,
        source_sha256: native.sha256, size_bytes: bytes.byteLength },
      design: { bodies: [{ name: 'Part' }], sketches: [], params: [], timeline: [] } } };
  return { cad, bytes };
}
afterEach(() => vi.unstubAllGlobals());

describe('direct CAD checkpoint meshes', () => {
  it('requests exactly the identified checkpoint mesh and verifies its bytes', async () => {
    const { cad, bytes } = await fixture();
    const fetch = vi.fn().mockResolvedValue(new Response(bytes));
    vi.stubGlobal('fetch', fetch);
    expect(new Uint8Array(await cadWorkingMesh(cad, 'session'))).toEqual(bytes);
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      documentId: cad.document_id, sessionId: 'session', checkpointId: cad.working!.checkpoint_id, kind: 'stl',
    });
  });

  it('rejects mismatched native sources before requesting bytes', async () => {
    const { cad } = await fixture();
    cad.working!.mesh!.source_sha256 = 'f'.repeat(64);
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(cadWorkingMesh(cad, 'session')).rejects.toThrow('point de reprise');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rejects changed bytes, a changed size and an obsolete checkpoint response', async () => {
    const { cad, bytes } = await fixture();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('changed')));
    await expect(cadWorkingMesh(cad, 'session')).rejects.toThrow('modifiée');
    cad.working!.mesh!.size_bytes++;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(bytes)));
    await expect(cadWorkingMesh(cad, 'session')).rejects.toThrow('modifiée');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: 'checkpoint changed' }, { status: 400 })));
    await expect(cadWorkingMesh(cad, 'session')).rejects.toThrow('checkpoint changed');
  });

  it('selects the published export after delivery and retains compatibility with older checkpoints', async () => {
    const { cad } = await fixture();
    expect(cadMeshSource(cad)).toBe('checkpoint');
    expect(cadMeshSource({ ...cad, status: 'ready' })).toBe('published');
    delete cad.working!.mesh;
    const retained = cadUpdate(cad)!;
    expect(retained.working?.checkpoint_id).toBe(cad.working!.checkpoint_id);
    expect(cadMeshSource(retained)).toBe('worker');
    expect(cadMeshSource({ ...retained, working: { ...retained.working!, design: { ...retained.working!.design, bodies: [] } } })).toBe('empty');
    expect(cadMeshSource({ ...cad, working: null })).toBe('published');
  });
});
