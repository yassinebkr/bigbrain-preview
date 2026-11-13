/** Serial presentation preparation coalesces intermediate states during construction. */
export class CadPreviewQueue<T, Prepared = Uint8Array> {
  private desired?: { version: number; value: T };
  private version = 0;
  private running = false;
  private closed = false;
  private readonly prepare: (value: T) => Promise<Prepared>;
  private readonly present: (bytes: Prepared, value: T) => Promise<void>;
  private readonly status: (error?: Error) => void;

  constructor(
    prepare: (value: T) => Promise<Prepared>,
    present: (bytes: Prepared, value: T) => Promise<void>,
    status: (error?: Error) => void,
  ) {
    this.prepare = prepare;
    this.present = present;
    this.status = status;
  }

  update(value: T) {
    if (this.closed) return;
    this.desired = { version: ++this.version, value };
    void this.run();
  }

  close() { this.closed = true; this.desired = undefined; }

  private async run() {
    if (this.running) return;
    this.running = true;
    try {
      while (this.desired && !this.closed) {
        const next = this.desired;
        this.desired = undefined;
        try {
          const bytes = await this.prepare(next.value);
          // A newer accepted checkpoint can arrive while geometry is prepared.
          // Present only the latest requested state and retain the visible frame.
          if (this.closed || next.version !== this.version) continue;
          await this.present(bytes, next.value);
          if (!this.closed) this.status();
        } catch (error) {
          if (!this.closed && next.version === this.version)
            this.status(error instanceof Error ? error : new Error(String(error)));
        }
      }
    } finally { this.running = false; }
  }
}
