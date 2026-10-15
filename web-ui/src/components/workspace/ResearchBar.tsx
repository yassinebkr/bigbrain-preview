import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Sparkles,
  FileText,
  Command,
  FilePlus,
  ArrowRight as ArrowRightIcon,
  X,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';

type SuggestionType = 'file' | 'command' | 'action';

interface Suggestion {
  id: string;
  type: SuggestionType;
  label: string;
  description?: string;
  icon: React.ReactNode;
  action: () => void;
}

interface SearchHit {
  path: string;
  name: string;
  type: string;
}

// A query without an extension becomes a markdown note at the root.
function createFileName(query: string): string {
  const q = query.trim();
  return /\.[a-z0-9]+$/i.test(q) ? q : `${q}.md`;
}

export function ResearchBar() {
  const { setView, setInputText, sendMessage, setPendingOpenFile } = useAppStore();
  const [query, setQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Real file search: debounced query against /api/fs/search.
  useEffect(() => {
    const q = query.trim();
    if (!q || q.startsWith('/')) {
      setHits([]);
      return;
      }
    const timer = setTimeout(() => {
      fetch(`/api/fs/search?q=${encodeURIComponent(q)}`)
        .then((r) => (r.ok ? r.json() : { results: [] }))
        .then((data) => setHits(data.results || []))
        .catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  // Parse command prefix
  const isCommand = query.startsWith('/');
  const commandPrefix = isCommand ? query.split(' ')[0].toLowerCase() : '';

  const suggestions: Suggestion[] = React.useMemo(() => {
    const items: Suggestion[] = [];

    if (!isCommand && query.trim().length > 0) {
      // Real file search results
      hits.slice(0, 4).forEach((hit) => {
        items.push({
          id: `file-${hit.path}`,
          type: 'file',
          label: hit.name,
          description: hit.path,
          icon: <FileText size={16} strokeWidth={1.5} style={{ color: '#5ac8fa' }} />,
          action: () => {
            setPendingOpenFile(hit.path);
            setQuery('');
            setIsFocused(false);
          },
        });
      });

      // AI Ask action
      items.push({
        id: 'ask-ai',
        type: 'action',
        label: `Ask AI about "${query}"`,
        icon: <Sparkles size={16} strokeWidth={1.5} style={{ color: '#0071e3' }} />,
        action: () => {
          setInputText(query);
          setView('chat');
          setQuery('');
          setIsFocused(false);
          setTimeout(() => sendMessage(), 100);
        },
      });

      // New file action — REAL creation through the FS API
      items.push({
        id: 'new-file',
        type: 'action',
        label: `Create "${createFileName(query)}"`,
        icon: <FilePlus size={16} strokeWidth={1.5} style={{ color: '#34c759' }} />,
        action: async () => {
          try {
            await fetch('/api/fs/file', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ path: createFileName(query), content: '' }),
            });
            // Refresh the results — the new file must show up for real.
            const r = await fetch(`/api/fs/search?q=${encodeURIComponent(query)}`);
            const data = await r.json();
            setHits(data.results || []);
          } catch { /* keep stale results on failure */ }
          setIsFocused(false);
        },
      });
    }

    if (isCommand || query.trim().length > 0) {
      // Command suggestions (only the ones that actually do something:
      // both funnel the query into the AI chat)
      const commands = [
        {
          id: 'cmd-search',
          prefix: '/search',
          label: '/search',
          desc: 'Send a search request to the AI',
          icon: <Search size={16} strokeWidth={1.5} style={{ color: '#ff9500' }} />,
        },
        {
          id: 'cmd-ask',
          prefix: '/ask',
          label: '/ask',
          desc: 'Ask the AI assistant',
          icon: <Sparkles size={16} strokeWidth={1.5} style={{ color: '#0071e3' }} />,
        },
      ];

      commands.forEach((cmd) => {
        if (isCommand ? cmd.prefix.startsWith(commandPrefix) : true) {
          items.push({
            id: cmd.id,
            type: 'command',
            label: cmd.label,
            description: cmd.desc,
            icon: cmd.icon,
            action: () => {
              if (!isCommand) setQuery(`${cmd.prefix} `);
              inputRef.current?.focus();
            },
          });
        }
      });
    }

    return items;
  }, [query, hits, isCommand, commandPrefix, setView, setInputText, sendMessage, setPendingOpenFile]);

  // Reset selection when suggestions change
  useEffect(() => {
    setSelectedIndex(0);
  }, [suggestions.length]);

  // Global / shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '/' && !isFocused) {
        const target = e.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === 'Escape' && isFocused) {
        setIsFocused(false);
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFocused]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % suggestions.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + suggestions.length) % suggestions.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (suggestions[selectedIndex]) {
          suggestions[selectedIndex].action();
        }
      }
    },
    [suggestions, selectedIndex]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (suggestions[selectedIndex]) {
      suggestions[selectedIndex].action();
    } else if (query.trim()) {
      // Default: search or ask
      setInputText(query);
      setView('chat');
      setQuery('');
      setIsFocused(false);
      setTimeout(() => sendMessage(), 100);
    }
  };

  const clearQuery = () => {
    setQuery('');
    inputRef.current?.focus();
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full"
      style={{ zIndex: isFocused ? 30 : 10 }}
    >
      {/* Main input */}
      <form onSubmit={handleSubmit} className="w-full">
        <motion.div
          animate={{
            boxShadow: isFocused
              ? '0 0 0 2px rgba(0,113,227,0.25), 0 8px 32px rgba(0,0,0,0.3)'
              : '0 2px 8px rgba(0,0,0,0.15)',
          }}
          transition={{ duration: 0.2 }}
          className="flex items-center w-full rounded-xl border transition-colors duration-200"
          style={{
            backgroundColor: isFocused ? 'var(--bg-surface)' : 'var(--bg-input)',
            borderColor: isFocused ? 'rgba(0,113,227,0.35)' : 'var(--border-subtle)',
          }}
        >
          <div className="flex items-center justify-center pl-4">
            {isCommand ? (
              <Command
                size={18}
                strokeWidth={1.5}
                style={{ color: '#ff9500' }}
              />
            ) : (
              <Search
                size={18}
                strokeWidth={1.5}
                style={{ color: 'var(--text-tertiary)' }}
              />
            )}
          </div>

          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onKeyDown={handleKeyDown}
            placeholder="Search files, run AI queries, or type a command..."
            className="flex-1 bg-transparent px-3 py-3 text-sm outline-none"
            style={{ color: 'var(--text-primary)' }}
          />

          <div className="flex items-center gap-1 pr-3">
            {query && (
              <button
                type="button"
                onClick={clearQuery}
                className="p-1 rounded-md transition-colors duration-100 cursor-pointer"
                style={{ color: 'var(--text-tertiary)' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <X size={14} />
              </button>
            )}

            {!isFocused && (
              <span
                className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium"
                style={{
                  backgroundColor: 'var(--bg-pill)',
                  color: 'var(--text-tertiary)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                /
              </span>
            )}

            <Sparkles
              size={16}
              strokeWidth={1.5}
              style={{ color: 'var(--text-tertiary)', opacity: 0.5 }}
              className="ml-1"
            />
          </div>
        </motion.div>
      </form>

      {/* Suggestions dropdown */}
      <AnimatePresence>
        {isFocused && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute left-0 right-0 mt-1.5 rounded-xl border overflow-hidden shadow-xl"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
              maxHeight: '360px',
              overflowY: 'auto',
            }}
          >
            {suggestions.length === 0 ? (
              <div
                className="px-4 py-6 text-sm text-center"
                style={{ color: 'var(--text-tertiary)' }}
              >
                No results found
              </div>
            ) : (
              <div className="py-1.5">
                {/* Group by type */}
                {(['file', 'command', 'action'] as const).map((groupType) => {
                  const groupItems = suggestions.filter((s) => s.type === groupType);
                  if (groupItems.length === 0) return null;

                  return (
                    <div key={groupType}>
                      <div
                        className="px-3 py-1 text-[10px] uppercase tracking-wider font-semibold"
                        style={{ color: 'var(--text-tertiary)' }}
                      >
                        {groupType === 'file' && 'Files'}
                        {groupType === 'command' && 'Commands'}
                        {groupType === 'action' && 'Actions'}
                      </div>
                      {groupItems.map((suggestion) => {
                        const globalIdx = suggestions.indexOf(suggestion);
                        return (
                          <motion.button
                            key={suggestion.id}
                            type="button"
                            onClick={() => suggestion.action()}
                            className="flex items-center w-full px-3 py-2 text-sm gap-3 transition-colors duration-75 cursor-pointer"
                            style={{
                              backgroundColor:
                                globalIdx === selectedIndex
                                  ? 'var(--bg-icon-hover)'
                                  : 'transparent',
                              color: 'var(--text-primary)',
                            }}
                            onMouseEnter={() => setSelectedIndex(globalIdx)}
                          >
                            <span className="flex-shrink-0">{suggestion.icon}</span>
                            <div className="flex flex-col items-start flex-1 min-w-0">
                              <span className="truncate font-medium">{suggestion.label}</span>
                              {suggestion.description && (
                                <span
                                  className="text-[11px] truncate"
                                  style={{ color: 'var(--text-tertiary)' }}
                                >
                                  {suggestion.description}
                                </span>
                              )}
                            </div>
                            {globalIdx === selectedIndex && (
                              <ArrowRightIcon
                                size={12}
                                strokeWidth={1.5}
                                style={{ color: 'var(--text-tertiary)' }}
                                className="flex-shrink-0"
                              />
                            )}
                          </motion.button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Footer hint */}
            <div
              className="flex items-center justify-between px-3 py-1.5 border-t text-[10px]"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-tertiary)',
              }}
            >
              <div className="flex gap-2">
                <span className="flex items-center gap-0.5">
                  <kbd
                    className="px-1 py-0.5 rounded text-[9px]"
                    style={{ backgroundColor: 'var(--bg-pill)', border: '1px solid var(--border-subtle)' }}
                  >
                    ↑↓
                  </kbd>
                  <span>navigate</span>
                </span>
                <span className="flex items-center gap-0.5">
                  <kbd
                    className="px-1 py-0.5 rounded text-[9px]"
                    style={{ backgroundColor: 'var(--bg-pill)', border: '1px solid var(--border-subtle)' }}
                  >
                    ↵
                  </kbd>
                  <span>select</span>
                </span>
              </div>
              <span className="flex items-center gap-0.5">
                <kbd
                  className="px-1 py-0.5 rounded text-[9px]"
                  style={{ backgroundColor: 'var(--bg-pill)', border: '1px solid var(--border-subtle)' }}
                >
                  esc
                </kbd>
                <span>close</span>
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
