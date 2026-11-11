import { expect, it, vi } from 'vitest';
import { CadPreviewQueue } from './cadPreviewQueue';

it('coalesces superseded checkpoints and preserves serial preparation', async () => {
  const releases: Array<(bytes: Uint8Array) => void> = [];
  const prepare = vi.fn(() => new Promise<Uint8Array>(resolve => releases.push(resolve)));
  const present = vi.fn(async () => {});
  const queue = new CadPreviewQueue<number>(prepare, present, vi.fn());
  queue.update(1);
  queue.update(2);
  queue.update(3);
  expect(prepare).toHaveBeenCalledTimes(1);
  releases[0](new Uint8Array([1]));
  await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
  expect(prepare.mock.calls[1]).toEqual([3]);
  expect(present).not.toHaveBeenCalled();
  releases[1](new Uint8Array([3]));
  await vi.waitFor(() => expect(present).toHaveBeenCalledWith(new Uint8Array([3]), 3));
});

it('closing during preparation prevents late presentation and callbacks', async () => {
  let release!: (bytes: Uint8Array) => void;
  const prepare = () => new Promise<Uint8Array>(resolve => { release = resolve; });
  const present = vi.fn(async () => {});
  const status = vi.fn();
  const queue = new CadPreviewQueue(prepare, present, status);
  queue.update('checkpoint');
  queue.close();
  release(new Uint8Array([1]));
  await Promise.resolve();
  expect(present).not.toHaveBeenCalled();
  expect(status).not.toHaveBeenCalled();
});

it('retains a usable queue after a preparation failure', async () => {
  const prepare = vi.fn().mockRejectedValueOnce(new Error('unavailable'))
    .mockResolvedValueOnce(new Uint8Array([2]));
  const present = vi.fn(async () => {});
  const status = vi.fn();
  const queue = new CadPreviewQueue(prepare, present, status);
  queue.update(1);
  await vi.waitFor(() => expect(status).toHaveBeenCalledWith(expect.any(Error)));
  queue.update(2);
  await vi.waitFor(() => expect(present).toHaveBeenCalledWith(new Uint8Array([2]), 2));
});
