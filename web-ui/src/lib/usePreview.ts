import { useEffect, useState } from 'react';

// Never restore a port from a run result: only project identity survives restart.
export function usePreview(path: string | undefined, enabled: boolean) {
  const [state, setState] = useState<{ url?: string; error?: string }>({});
  useEffect(() => {
    setState({});
    if (!path || !enabled) return;
    let disposed = false;
    let lease: string | undefined;
    let busy = false;
    const post = (body: object) => fetch('/api/fs/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body), keepalive: true,
    });
    const release = () => {
      const token = lease;
      lease = undefined;
      if (token) void post({ leaseId: token, action: 'release' }).catch(() => {});
    };
    const refresh = async () => {
      if (busy || disposed || document.hidden) return;
      busy = true;
      try {
        if (lease) {
          const response = await post({ leaseId: lease });
          if (response.ok) return;
          lease = undefined;
        }
        const response = await post({ path });
        if (!response.ok) throw new Error(await response.text());
        const body = await response.json();
        lease = body.leaseId;
        if (disposed || document.hidden) release();
        else setState({ url: body.previewUrl });
      } catch (error) {
        if (!disposed) setState({ error: String(error) });
      } finally { busy = false; }
    };
    const visibility = () => {
      if (document.hidden) { release(); setState({}); }
      else void refresh();
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', release);
    return () => {
      disposed = true;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', release);
      release();
    };
  }, [path, enabled]);
  return state;
}
