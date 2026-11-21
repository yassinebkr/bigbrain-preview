import { describe, expect, it, vi } from 'vitest';
// @ts-expect-error The backend serves this ES module without TypeScript declarations.
import { CadBrowserExecutor, cadRecoveryKey } from '../../../bigbrain/web/static/cad-browser-bridge.mjs';

function fixture(accept: () => Promise<unknown> = async () => ({ revision: 2, status: 'accepted' })) {
  const bytes = Uint8Array.of(1, 2, 3);
  const state = { generation: 'test', owner: 'agent' };
  const engine = { setLocked: vi.fn(), execute: vi.fn(async () => ({})),
    save: vi.fn(async () => bytes), presentAccepted: vi.fn() };
  const call = vi.fn(async (action: string) => {
    if (action === 'claim') return { id: 'operation', generation: 'test' };
    if (action === 'accept') return accept();
    return state;
  });
  const executor = new CadBrowserExecutor({ call }, engine);
  Object.assign(executor, { ready: true, state });
  return { bytes, engine, call, executor };
}

describe('CAD checkpoint handoff', () => {
  it('passes the exact accepted bytes and revision to the viewer', async () => {
    const { bytes, engine, executor } = fixture();
    const receipt = await executor.step();
    expect(engine.presentAccepted).toHaveBeenCalledWith(bytes, receipt);
  });

  it('keeps a rejected checkpoint out of the viewer', async () => {
    const { engine, executor } = fixture(async () => { throw new Error('lease lost'); });
    await expect(executor.step()).rejects.toThrow('lease lost');
    expect(engine.presentAccepted).not.toHaveBeenCalled();
  });

  it('requires reconnect after a viewer error without reporting the committed operation as failed', async () => {
    const { call, engine, executor } = fixture();
    engine.presentAccepted.mockRejectedValue(new Error('viewer unavailable'));
    await expect(executor.step()).rejects.toThrow('viewer unavailable');
    expect(call.mock.calls.map(([action]) => action)).toEqual(['claim', 'accept']);
    expect(executor.ready).toBe(false);
  });

  it('revokes the lease before interrupting an active worker and reconnecting', async () => {
    const { call, engine, executor } = fixture();
    let rejectOperation: (error: Error) => void = () => {};
    let executing: () => void = () => {};
    const started = new Promise<void>(resolve => { executing = resolve; });
    engine.execute.mockImplementation(() => new Promise((_, reject) => { rejectOperation = reject; executing(); }));
    const interrupt = vi.fn(() => {
      expect(call.mock.calls.map(([action]) => action)).toEqual(['claim', 'stop']);
      rejectOperation(new Error('terminated'));
    });
    Object.assign(engine, { interrupt });
    const reconnect = vi.spyOn(executor, 'connect').mockResolvedValue({ owner: 'user' });
    const active = executor.step();
    await started;
    await expect(executor.control('stop')).resolves.toEqual({ owner: 'user' });
    await expect(active).resolves.toBeNull();
    expect(interrupt).toHaveBeenCalledOnce();
    expect(reconnect).toHaveBeenCalledOnce();
    expect(engine.presentAccepted).not.toHaveBeenCalled();
  });
});

describe('manual CAD saves', () => {
  function manualSave() {
    const { bytes, engine, executor, call } = fixture();
    const state = { generation: 'test', owner: 'user', revision: 1, hash: 'original' };
    Object.assign(executor, { state, dirty: true });
    return { bytes, engine, executor, call, state };
  }

  it('recovers a committed save when its response is lost', async () => {
    const { bytes, executor, call, state } = manualSave();
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    const hash = Array.from(digest, value => value.toString(16).padStart(2, '0')).join('');
    const committed = { ...state, revision: 2, hash };
    call.mockImplementation(async action => {
      if (action === 'save') throw new Error('Response lost');
      return committed;
    });

    await executor.saveManual();
    expect(executor.state).toEqual(committed);
    expect(executor.dirty).toBe(false);
    expect(call.mock.calls.map(([action]) => action)).toEqual(['save', 'state']);
  });

  it('keeps the unsaved canvas available when the server did not commit', async () => {
    const { engine, executor, call, state } = manualSave();
    call.mockImplementation(async action => {
      if (action === 'save') throw new Error('Save unavailable');
      return state;
    });

    await expect(executor.saveManual()).rejects.toThrow('Save unavailable');
    expect(executor.state).toEqual(state);
    expect(executor.dirty).toBe(true);
    expect(engine.setLocked).toHaveBeenLastCalledWith(false);
  });
});


it('scopes native recovery to the conversation, document and accepted bytes', async () => {
  const scope = { sessionId: 'session', documentId: 'document' };
  const key = await cadRecoveryKey(scope, 'base');
  expect(key).toMatch(/^[a-f0-9]{64}$/);
  expect(await cadRecoveryKey({ ...scope }, 'base')).toBe(key);
  expect(await cadRecoveryKey({ ...scope, sessionId: 'other' }, 'base')).not.toBe(key);
  expect(await cadRecoveryKey({ ...scope, documentId: 'other' }, 'base')).not.toBe(key);
  expect(await cadRecoveryKey(scope, 'next')).not.toBe(key);
});
