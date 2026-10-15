import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { X, MessageSquare, Search, Clock } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

interface HistoryMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export function SessionsPanel() {
  const { sessions, activeSessionKey, switchSession, setSidebarPanel, connection } = useAppStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  // Load history from connection when panel opens
  useEffect(() => {
    if (connection) {
      setIsLoadingHistory(true);
      connection.loadHistory((response) => {
        setIsLoadingHistory(false);
        if (response.ok && response.payload?.messages) {
          const loadedMessages = response.payload.messages.map((m: any) => ({
            id: m.id || `hist-${Date.now()}-${Math.random()}`,
            role: m.role || 'assistant',
            content: typeof m.content === 'string' ? m.content : 
              (m.content?.filter((c: any) => c.type === 'text').map((c: any) => c.text).join('') || ''),
            timestamp: m.timestamp || Date.now(),
          }));
          setHistory(loadedMessages);
        }
      });
    }
  }, [connection]);

  // Combine mock sessions with real history
  const historySessions = history.length > 0 ? [{
    key: 'current',
    title: history[0]?.content?.substring(0, 30) + '...' || 'Current Conversation',
    timestamp: history[0]?.timestamp || Date.now(),
    messageCount: history.length,
  }] : sessions;

  const filteredSessions = historySessions.filter((s) =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSwitchSession = (key: string) => {
    switchSession(key);
    setSidebarPanel(null);
  };

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
        <span
          className="text-base font-semibold"
          style={{ color: 'var(--text-primary)' }}
        >
          History
        </span>
        <button
          onClick={() => setSidebarPanel(null)}
          className="p-1.5 rounded-md transition-colors duration-150 cursor-pointer"
          style={{ backgroundColor: 'transparent' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-button)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
          aria-label="Close panel"
        >
          <X size={20} style={{ color: 'var(--text-tertiary)' }} />
        </button>
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

      {/* Session List */}
      <div className="flex-1 overflow-y-auto">
        {isLoadingHistory && (
          <div className="px-4 py-3">
            <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
              <Clock size={14} className="animate-spin" />
              Loading history...
            </div>
          </div>
        )}

        {/* Real History Messages */}
        {history.length > 0 && (
          <>
            <div className="px-4 py-2">
              <span
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: 'var(--text-tertiary)' }}
              >
                Current Conversation ({history.length} messages)
              </span>
            </div>
            {history.slice(-10).map((msg) => (
              <button
                key={msg.id}
                onClick={() => {
                  // Close panel and switch to chat view
                  setSidebarPanel(null);
                  useAppStore.getState().setView('chat');
                }}
                className="flex items-center gap-2.5 w-full px-4 py-2.5 text-left transition-colors duration-150 relative cursor-pointer"
                style={{ backgroundColor: 'transparent' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <MessageSquare size={16} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
                <div className="flex flex-col min-w-0">
                  <span
                    className="text-sm font-medium truncate"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {msg.content?.substring(0, 40) || '...'}
                    {msg.content?.length > 40 ? '...' : ''}
                  </span>
                  <span
                    className="text-xs"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    {msg.role === 'user' ? 'You' : 'AI'} • {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </button>
            ))}
          </>
        )}

        {/* Mock Sessions */}
        <div className="px-4 py-2 mt-2">
          <span
            className="text-xs font-medium uppercase tracking-wider"
            style={{ color: 'var(--text-tertiary)' }}
          >
            Saved Sessions
          </span>
        </div>
        {filteredSessions.map((session) => (
          <button
            key={session.key}
            onClick={() => handleSwitchSession(session.key)}
            className="flex items-center gap-2.5 w-full px-4 py-2.5 text-left transition-colors duration-150 relative cursor-pointer"
            style={{
              backgroundColor:
                session.key === activeSessionKey
                  ? 'var(--bg-button)'
                  : 'transparent',
            }}
            onMouseEnter={(e) => {
              if (session.key !== activeSessionKey) {
                e.currentTarget.style.backgroundColor = 'var(--bg-button)';
              }
            }}
            onMouseLeave={(e) => {
              if (session.key !== activeSessionKey) {
                e.currentTarget.style.backgroundColor = 'transparent';
              }
            }}
          >
            {session.key === activeSessionKey && (
              <div
                className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
                style={{ backgroundColor: 'var(--accent-blue)' }}
              />
            )}
            <MessageSquare size={16} style={{ color: 'var(--text-tertiary)' }} />
            <div className="flex flex-col min-w-0">
              <span
                className="text-sm font-medium truncate"
                style={{ color: 'var(--text-primary)' }}
              >
                {session.title}
              </span>
              <span
                className="text-xs"
                style={{ color: 'var(--text-tertiary)' }}
              >
                {new Date(session.timestamp).toLocaleDateString()} • {session.messageCount} messages
              </span>
            </div>
          </button>
        ))}

        {/* Empty state */}
        {filteredSessions.length === 0 && history.length === 0 && !isLoadingHistory && (
          <div className="px-4 py-8 text-center">
            <span className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
              No conversations yet
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
