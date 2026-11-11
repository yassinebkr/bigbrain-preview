import { describe, expect, it, vi } from 'vitest';
import { CadWorkerChannel } from './cadWorker';

function fixture() {
  const worker = Object.assign(new EventTarget(), { postMessage: vi.fn(), terminate: vi.fn() });
  const channel = new CadWorkerChannel(worker);
  const reply = (data: unknown) => worker.dispatchEvent(new MessageEvent('message', { data }));
  return { worker, channel, reply };
}

describe('CAD worker channel', () => {
  it('accepts the matching reply and serializes requests', async () => {
    const { channel, worker, reply } = fixture();
    const open = channel.request('open', { id: 99, action: 'save' });
    expect(worker.postMessage).toHaveBeenCalledWith({ id: 1, action: 'open' });
    await expect(channel.request('save')).rejects.toThrow('in flight');
    reply({ id: 99, result: 'stale' });
    reply({ id: 1, result: 'opened' });
    await expect(open).resolves.toBe('opened');
    const save = channel.request('save');
    reply({ id: 2, result: new Uint8Array([1]) });
    await expect(save).resolves.toEqual(new Uint8Array([1]));
  });

  it('terminates once and rejects an interrupted request even if its result arrives late', async () => {
    const { channel, worker, reply } = fixture();
    const save = channel.request('save');
    channel.stop();
    reply({ id: 1, result: new Uint8Array([1]) });
    channel.stop();
    await expect(save).rejects.toThrow('stopped');
    await expect(channel.request('open')).rejects.toThrow('closed');
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });

  it('closes on worker errors and releases the pending command', async () => {
    const { channel, worker } = fixture();
    const command = channel.request('execute');
    worker.dispatchEvent(new Event('error'));
    await expect(command).rejects.toThrow('failed');
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });
});
