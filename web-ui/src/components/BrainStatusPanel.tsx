// BrainStatusPanel — live BigBrain brain states from the bus activity feed.
// Flat indicator dots (Aplot design: no glow). States come from the
// brain.status frames forwarded by the BigBrain adapter.

import { useAppStore } from '@/store/appStore';
import { Brain } from 'lucide-react';

const STATE_COLORS: Record<string, string> = {
  idle: 'var(--success, #34c759)',
  busy: 'var(--warning, #ff9500)',
  running: 'var(--warning, #ff9500)',
  error: 'var(--red, #ff3b30)',
  offline: 'var(--text-tertiary, #6e6e73)',
};

interface BrainEntry {
  name: string;
  state: string;
  ts: number;
}

export function BrainStatusPanel() {
  const activities = useAppStore((s) => s.agentActivities);

  // Latest brain.status activity per brain name.
  const brains: BrainEntry[] = [];
  const seen = new Set<string>();
  for (let i = activities.length - 1; i >= 0; i--) {
    const a = activities[i];
    if (a.type !== 'brain_status' || !a.name) continue;
    if (seen.has(a.name)) continue;
    seen.add(a.name);
    brains.push({
      name: a.name,
      state: String(a.detail?.state || 'offline'),
      ts: a.ts,
    });
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-2 px-4 py-3 border-b flex-shrink-0"
           style={{ borderColor: 'var(--border-subtle, #2a2a2e)' }}>
        <Brain size={14} style={{ color: 'var(--text-tertiary, #6e6e73)' }} />
        <span className="text-[11px] font-semibold uppercase tracking-wider"
              style={{ color: 'var(--text-tertiary, #6e6e73)' }}>
          Brains
        </span>
        <span className="ml-auto text-[11px]"
              style={{ color: 'var(--text-tertiary, #6e6e73)' }}>
          {brains.length}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-2">
        {brains.length === 0 ? (
          <p className="text-xs py-4 text-center"
             style={{ color: 'var(--text-tertiary, #6e6e73)' }}>
            Waiting for brain status events…
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {brains.map((brain) => (
              <li
                key={brain.name}
                className="flex items-center gap-2.5 px-3 py-2 rounded-lg"
                style={{
                  backgroundColor: 'var(--bg-surface, #161616)',
                  border: '1px solid var(--border-subtle, #2a2a2e)',
                }}
              >
                <span
                  aria-hidden
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: STATE_COLORS[brain.state] || STATE_COLORS.offline }}
                />
                <span className="text-[13px] font-medium truncate"
                      style={{ color: 'var(--text-primary, #f5f5f7)' }}>
                  {brain.name}
                </span>
                <span className="ml-auto text-[11px] capitalize"
                      style={{ color: 'var(--text-tertiary, #6e6e73)' }}>
                  {brain.state}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
