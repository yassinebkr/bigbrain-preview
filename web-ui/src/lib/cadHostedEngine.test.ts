import { describe, expect, it, vi } from 'vitest';
import { CadHostedEngine } from './cadHostedEngine';

describe('interactive SolidCraft session', () => {
  it('routes manual ownership and saving to the editor session', async () => {
    const saved = new Uint8Array([1, 2, 3]);
    const viewer = {
      camera: vi.fn(), presentCached: vi.fn(), setLocked: vi.fn(),
      capabilities: vi.fn().mockResolvedValue({ ownership: 'exclusive' }),
      save: vi.fn().mockResolvedValue(saved), execute: vi.fn().mockResolvedValue({ output: 'ok' }),
    };
    const engine = new CadHostedEngine(viewer, '/worker', 'build', true);
    expect(engine.hosted).toBe(false);
    const onManualInput = vi.fn();
    engine.onManualInput = onManualInput;
    expect((viewer as {onManualInput?: () => void}).onManualInput).toBe(onManualInput);
    engine.setLocked(false);
    expect(viewer.setLocked).toHaveBeenLastCalledWith(false);
    expect(await engine.save()).toBe(saved);
    expect(await engine.execute('sketch.edit', { sketch: 1 })).toEqual({ output: 'ok' });
    expect(await engine.capabilities()).toEqual({ ownership: 'exclusive' });
    engine.setLocked(true);
    expect(viewer.setLocked).toHaveBeenLastCalledWith(true);
  });

  it('keeps observation sessions locked while forwarding camera commands', async () => {
    const viewer = { camera: vi.fn(), presentCached: vi.fn(), setLocked: vi.fn() };
    const engine = new CadHostedEngine(viewer, '/worker', 'build');
    engine.setLocked(false);
    expect(viewer.setLocked).toHaveBeenLastCalledWith(true);
    await engine.camera('fit');
    expect(viewer.camera).toHaveBeenCalledWith('fit');
  });
});
