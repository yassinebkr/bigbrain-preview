// SessionsPanel — the History sidebar: REAL server-side conversations.
// Lists the sessions from data/sessions/ (title, time, message count),
// search by title, click opens the conversation, "New" starts a fresh
// server session. No more single-conversation message dump.

import { useState } from 'react';
import { motion } from 'framer-motion';
import { X, MessageSquare, Search, Plus, Clock } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

function timeAgo(timestamp: number): string {
  if (!timestamp) return '';
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function SessionsPanel() {
  const { setSidebarPanel, sessions, activeSessionKey, openSession, startNewSession } = useAppStore();
  const [searchQuery, setSearchQuery] = useState('');

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <motion.div
      initial={{ x: '-100%' }}
      animate={{ x: 0 }}
      exit={{ x: '-100%' }}
      transition={{ duration: 0.3, ease: easeOut }}
      className="h-full flex flex-col"
      style={{
        width: '300px',
        backgroundColor: 'var(--bg-surface)',
        borderRight: '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between h-14 px-4 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-subtle)' }}
      >
        <span className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          History
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={startNewSession}
            title="New conversation"
            className="p-1.5 rounded-md cursor-pointer"
            style={{ color: 'var(--accent-blue)' }}
          >
            <Plus size={18} />
          </button>
          <button
            onClick={() => setSidebarPanel(null)}
            className="p-1.5 rounded-md cursor-pointer"
            style={{ color: 'var(--text-tertiary)' }}
            aria-label="Close panel"
          >
            <X size={20} />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-4 py-3 flex-shrink-0">
        <div
          className="flex items-center gap-2 h-10 px-3 rounded-[10px]"
          style={{
            backgroundColor: 'var(--bg-input)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <Search size={16} style={{ color: 'var(--text-tertiary)' }} />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 bg-transparent border-none outline-none text-sm"
            style={{ color: 'var(--text-primary)' }}
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="px-4 py-6 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {sessions.length === 0
              ? 'No conversations yet — your sessions will appear here.'
              : 'No conversation matches this search.'}
          </p>
        ) : (
          filtered.map((session) => (
            <button
              key={session.key}
              onClick={() => openSession(session.key)}
              className="flex items-center gap-2.5 w-full px-4 py-2.5 text-left cursor-pointer relative group"
              style={{
                backgroundColor:
                  session.key === activeSessionKey
                    ? 'var(--bg-icon-hover)'
                    : 'transparent',
              }}
            >
              {session.key === activeSessionKey && (
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 rounded-r-full"
                  style={{ backgroundColor: 'var(--accent-blue)' }}
                />
              )}
              <MessageSquare
                size={16}
                style={{
                  color: session.key === activeSessionKey
                    ? 'var(--accent-blue)'
                    : 'var(--text-tertiary)',
                }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] truncate" style={{ color: 'var(--text-primary)' }}>
                  {session.title}
                </div>
                <div
                  className="text-[11px] flex items-center gap-1"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  <Clock size={10} />
                  {timeAgo(session.timestamp)}
                  {session.messageCount > 0 && ` · ${session.messageCount} msg`}
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </motion.div>
  );
}
