import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function TypingIndicator() {
  const activities = useAppStore((s) => s.agentActivities);
  const session = useAppStore((s) => s.activeSessionKey);
  const messages = useAppStore((s) => s.messages);
  const latestUser = [...messages].reverse().find((m) => m.role === 'user')?.timestamp ?? 0;
  const started = [...activities].reverse().find((a) => a.type === 'front.decision_started' &&
    a.detail?.session_id === session && (a.ts ?? 0) >= latestUser);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = started ? Math.max(0, Math.floor((now - (started.ts ?? now)) / 1000)) : 0;
  const limit = started?.detail?.timeout_seconds;
  const exceeded = typeof limit === 'number' && seconds >= limit;
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, ease: easeOut }}
      className="flex justify-start w-full"
    >
      <div className="flex items-center gap-2">
        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center"
          style={{ backgroundColor: '#0071e3' }}
        >
          <img
            src="/robot-icon.png"
            alt="AI"
            className="w-4 h-4 object-contain"
          />
        </div>

        <div className="text-[12px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          <p role="status">{started ? exceeded ? 'Délai atteint · clôture en attente' : 'Décision du front brain en cours' : 'Préparation de la réponse'}</p>
          {started && <p className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
            {started.detail?.model}{started.detail?.effort ? ` · ${started.detail.effort}` : ''}
            <span aria-hidden="true"> · {seconds} s{typeof limit === 'number' ? ` / ${limit} s` : ''}</span>
          </p>}
        </div>

        {/* Typing Dots */}
        <div
          className="flex items-center justify-center h-9 px-4 rounded-[18px] gap-1"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: 'var(--text-tertiary)' }}
              animate={{
                scale: [1, 1.4, 1],
              }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                delay: i * 0.15,
                ease: 'easeInOut',
              }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
