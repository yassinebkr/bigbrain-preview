/** Serial channel for a worker-owned CAD session. Each client owns one worker lifetime. */
export class CadWorkerChannel {
  private sequence = 0;
  private closed = false;
  private pending?: { id: number; resolve: (value: unknown) => void; reject: (error: Error) => void };

  private readonly worker: Pick<Worker, 'postMessage' | 'terminate' | 'addEventListener'>;

  constructor(worker: Pick<Worker, 'postMessage' | 'terminate' | 'addEventListener'>) {
    this.worker = worker;
    worker.addEventListener('message', (event: MessageEvent) => {
      const reply = event.data;
      if (!reply || this.closed || !this.pending || reply.id !== this.pending.id) return;
      const request = this.pending;
      this.pending = undefined;
      if (typeof reply.error === 'string') request.reject(new Error(reply.error));
      else request.resolve(reply.result);
    });
    worker.addEventListener('error', () => this.stop('CAD worker failed'));
    worker.addEventListener('messageerror', () => this.stop('CAD worker response could not be decoded'));
  }

  request(action: 'open' | 'execute' | 'save', data: Record<string, unknown> = {}): Promise<unknown> {
    if (this.closed) return Promise.reject(new Error('CAD worker is closed'));
    if (this.pending) return Promise.reject(new Error('CAD worker already has an operation in flight'));
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      this.pending = { id, resolve, reject };
      try { this.worker.postMessage({ ...data, id, action }); }
      catch (error) { this.pending = undefined; reject(error); }
    });
  }

  stop(reason = 'CAD worker stopped'): void {
    if (this.closed) return;
    this.closed = true;
    const request = this.pending;
    this.pending = undefined;
    this.worker.terminate();
    request?.reject(new Error(reason));
  }
}
