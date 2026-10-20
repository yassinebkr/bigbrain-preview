// SessionsPanel — the History sidebar: REAL server-side conversations.
// Lists the sessions from data/sessions/ (title, time, message count),
// search by title, click opens the conversation, "New" starts a fresh
// server session. No more single-conversation message dump.

import { useState } from 'react';
import { motion } from 'framer-motion';
import { X, MessageSquare, Search, Plus, Clock, Pencil, Trash2, Check, Loader2 } from 'lucide-react';
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
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mutate = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); setEditing(null); setConfirmDelete(null); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };

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
        width: 'min(360px, 100vw)',
        backgroundColor: 'var(--bg-surface)',
        color: 'var(--text-primary)',
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
        {error && <p role="alert" className="mx-4 mb-3 text-xs" style={{ color: 'var(--warning)' }}>{error}</p>}
        {filtered.length === 0 ? (
          <p className="px-4 py-6 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {sessions.length === 0
              ? 'No conversations yet — your sessions will appear here.'
              : 'No conversation matches this search.'}
          </p>
        ) : (
          filtered.map((session) => (
            <div
              key={session.key}
              className="mx-2 mb-1 rounded-xl px-2 py-2 text-left relative group"
              style={{
                backgroundColor:
                  session.key === activeSessionKey
                    ? 'var(--bg-icon-hover)'
                    : 'transparent',
              }}
            >
              <div className="flex items-center gap-1">
              <button onClick={() => openSession(session.key)} disabled={busy} aria-label={session.title} className="flex items-center gap-2.5 flex-1 min-w-0 text-left p-1 rounded-lg" aria-current={session.key === activeSessionKey ? 'page' : undefined}>
              <MessageSquare className="shrink-0"
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
              <button disabled={busy} className="p-2 rounded-lg hover:bg-white/10" aria-label={`Renommer ${session.title}`} title="Renommer" onClick={() => { setEditing(session.key); setTitle(session.title); setConfirmDelete(null); setError(''); }}><Pencil size={14} /></button>
              <button disabled={busy} className="p-2 rounded-lg hover:bg-white/10" aria-label={`Supprimer ${session.title}`} title="Supprimer" onClick={() => { setConfirmDelete(session.key); setEditing(null); setError(''); }}><Trash2 size={14} /></button>
              </div>
              {editing === session.key && <form className="mt-2 flex gap-1" onSubmit={(e) => { e.preventDefault(); if (title.trim()) void mutate(() => useAppStore.getState().renameSession(session.key, title.trim())); }}>
                <input autoFocus aria-label="Titre de la conversation" value={title} maxLength={120} disabled={busy} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') setEditing(null); }} className="min-w-0 flex-1 rounded-lg p-2 text-sm" style={{ background: 'var(--bg-input)', color: 'var(--text-primary)' }} />
                <button type="submit" disabled={busy || !title.trim()} className="p-2" aria-label="Enregistrer le titre">{busy ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}</button>
                <button type="button" disabled={busy} className="p-2" aria-label="Annuler le renommage" onClick={() => setEditing(null)}><X size={16} /></button>
              </form>}
              {confirmDelete === session.key && <div className="mt-3 p-3 rounded-xl text-xs leading-relaxed" role="group" aria-label="Confirmer la suppression" style={{ background: 'var(--bg-input)' }}>
                <p>Supprimer cette conversation de l’historique et arrêter ses agents ? Les projets, fichiers, souvenirs partagés et journaux techniques seront conservés.</p>
                <div className="flex gap-2 mt-3"><button disabled={busy} className="work-secondary" onClick={() => setConfirmDelete(null)}>Annuler</button><button disabled={busy} className="work-primary" onClick={() => void mutate(() => useAppStore.getState().deleteSession(session.key))}>{busy ? 'Suppression…' : 'Supprimer définitivement'}</button></div>
              </div>}
            </div>
          ))
        )}
      </div>
    </motion.div>
  );
}
