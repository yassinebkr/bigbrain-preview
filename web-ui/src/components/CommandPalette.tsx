import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Search, MessageSquare, Command, Clock } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

interface SearchResult {
  id: string;
  title: string;
  subtitle: string;
  icon: 'session' | 'command' | 'recent';
  action: () => void;
}

export function CommandPalette() {
  const { setCommandPaletteOpen, sessions, switchSession, setSidebarPanel, toggleTheme, setView } = useAppStore();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleClose = () => {
    setCommandPaletteOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleClose();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
      return;
    }
    if (e.key === 'Enter' && results[selectedIndex]) {
      results[selectedIndex].action();
      handleClose();
    }
  };

  const commands: SearchResult[] = [
    {
      id: 'cmd-new-chat',
      title: 'New Chat',
      subtitle: 'Start a new conversation',
      icon: 'command',
      action: () => setView('welcome'),
    },
    {
      id: 'cmd-toggle-theme',
      title: 'Toggle Theme',
      subtitle: 'Switch between dark and light mode',
      icon: 'command',
      action: () => toggleTheme(),
    },
    {
      id: 'cmd-open-settings',
      title: 'Open Settings',
      subtitle: 'Configure app preferences',
      icon: 'command',
      action: () => setSidebarPanel('settings'),
    },
    {
      id: 'cmd-open-history',
      title: 'Open History',
      subtitle: 'View past conversations',
      icon: 'command',
      action: () => setSidebarPanel('sessions'),
    },
  ];

  const sessionResults: SearchResult[] = sessions.map((s) => ({
    id: `session-${s.key}`,
    title: s.title,
    subtitle: 'Conversation',
    icon: 'session',
    action: () => switchSession(s.key),
  }));

  const results: SearchResult[] = [...commands, ...sessionResults].filter(
    (r) =>
      r.title.toLowerCase().includes(query.toLowerCase()) ||
      r.subtitle.toLowerCase().includes(query.toLowerCase())
  );

  const getIcon = (icon: SearchResult['icon']) => {
    switch (icon) {
      case 'session':
        return <MessageSquare size={16} style={{ color: 'var(--text-tertiary)' }} />;
      case 'command':
        return <Command size={16} style={{ color: 'var(--text-tertiary)' }} />;
      case 'recent':
        return <Clock size={16} style={{ color: 'var(--text-tertiary)' }} />;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[20vh]"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={handleClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ duration: 0.2, ease: easeOut }}
        className="w-full max-w-[560px] rounded-2xl overflow-hidden"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          boxShadow: 'var(--shadow-lg)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input */}
        <div
          className="flex items-center gap-3 h-14 px-5"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <Search size={20} style={{ color: 'var(--text-tertiary)' }} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search conversations, settings, commands..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent border-none outline-none text-base"
            style={{ color: 'var(--text-primary)' }}
          />
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto py-2">
          {results.length === 0 ? (
            <div className="flex items-center justify-center h-20">
              <span
                className="text-sm"
                style={{ color: 'var(--text-tertiary)' }}
              >
                No results found
              </span>
            </div>
          ) : (
            results.map((result, index) => (
              <button
                key={result.id}
                onClick={() => {
                  result.action();
                  handleClose();
                }}
                className="flex items-center gap-3 w-full px-5 py-2.5 text-left transition-colors duration-100 cursor-pointer"
                style={{
                  backgroundColor:
                    index === selectedIndex ? 'var(--bg-button)' : 'transparent',
                  borderLeft:
                    index === selectedIndex
                      ? '3px solid var(--accent-blue)'
                      : '3px solid transparent',
                }}
                onMouseEnter={() => setSelectedIndex(index)}
              >
                {getIcon(result.icon)}
                <div className="flex flex-col min-w-0">
                  <span
                    className="text-sm font-medium"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {result.title}
                  </span>
                  <span
                    className="text-xs"
                    style={{ color: 'var(--text-tertiary)' }}
                  >
                    {result.subtitle}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
