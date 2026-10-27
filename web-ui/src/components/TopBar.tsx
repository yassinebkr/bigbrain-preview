import type { ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, Sparkles } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { ConnectionStatus } from './ConnectionStatus';

// Per-role model lineup (BigBrain orchestrates models per role — the
// dropdown shows the orchestra, not a single model). Available models come
// from the registry filtered by the connected providers.

import { useCallback, useEffect, useState } from 'react';

interface RoleLine {
  key: string;
  model_id: string | null;
  display_name: string;
}
interface RegistryModel {
  key: string;
  display_name: string;
  provider: string;
  available: boolean;
}

const ROLE_LABELS: Record<string, string> = {
  front: 'Front Brain',
  planner: 'Planner',
  code: 'Code',
  web: 'Web App Brain',
  research: 'Web Search Brain',
  subagent: 'Sub-agents',
};

interface TopBarProps {
  children?: ReactNode;
}

export function TopBar({ children }: TopBarProps) {
  const { connectionStatus } = useAppStore();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [lineup, setLineup] = useState<Record<string, RoleLine> | null>(null);
  const [registry, setRegistry] = useState<RegistryModel[]>([]);
  const [roleMenu, setRoleMenu] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [rolesRes, modelsRes] = await Promise.all([
        fetch('/api/models/roles').then((r) => r.json()),
        fetch('/api/models').then((r) => r.json()),
      ]);
      setLineup(rolesRes.roles || null);
      setRegistry(modelsRes.models || []);
    } catch (e) {
      setLineup(null);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const assign = async (role: string, key: string) => {
    setRoleMenu(null);
    try {
      await fetch('/api/models/roles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, key }),
      });
      await refresh();
    } catch (e) { /* surfaced by the roles refresh */ }
  };

  const frontName = lineup?.front?.display_name || 'BigBrain';

  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.15, ease: [0, 0, 0.2, 1] }}
      className="sticky top-0 z-30 flex items-center justify-between px-2 sm:px-3 md:px-4 h-14 flex-shrink-0"
    >
      {/* Left Zone - Hamburger (mobile) + Model Selector */}
      <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
        {children}
        <div className="hidden sm:block flex-shrink-0">
          <ConnectionStatus status={connectionStatus} />
        </div>
        <div className="relative flex-shrink-0">
          <button
            onClick={() => {
              setDropdownOpen(!dropdownOpen);
              if (!dropdownOpen) refresh();
            }}
            className="flex items-center gap-1.5 h-9 sm:h-8 pl-1.5 sm:pl-2 pr-2 sm:pr-3 rounded-full transition-all duration-200 cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-button)';
              e.currentTarget.style.borderColor = 'var(--border-input)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
              e.currentTarget.style.borderColor = 'var(--border-subtle)';
            }}
          >
            <img
              src="/robot-icon.png"
              alt=""
              className="w-[18px] h-[18px] object-contain"
            />
            <span
              className="text-[13px] font-medium hidden sm:inline"
              style={{ color: 'var(--text-primary)' }}
            >
              {frontName}
            </span>
            <ChevronDown
              size={12}
              className="hidden sm:block"
              style={{
                color: 'var(--text-tertiary)',
                transform: dropdownOpen ? 'rotate(180deg)' : 'rotate(0)',
                transition: 'transform 0.2s ease',
              }}
            />
          </button>

          <AnimatePresence>
            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setDropdownOpen(false)}
                />
                <motion.div
                  initial={{ opacity: 0, y: -5, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -5, scale: 0.97 }}
                  transition={{ duration: 0.15 }}
                  className="absolute top-full left-0 mt-2 min-w-[200px] rounded-xl py-2 z-50"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    boxShadow: 'var(--shadow-lg)',
                  }}
                >
                  {/* Per-role lineup: each role picks among the models
                      AVAILABLE under the current connection mode. */}
                  {!lineup && (
                    <div className="px-4 py-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                      Lineup unavailable (server offline?)
                    </div>
                  )}
                  {lineup && Object.entries(ROLE_LABELS).map(([role, label]) => {
                    const current = lineup[role];
                    const open = roleMenu === role;
                    return (
                      <div key={role} className="relative">
                        <button
                          onClick={() => setRoleMenu(open ? null : role)}
                          className="flex items-center gap-2.5 w-full h-9 px-4 transition-colors duration-150 cursor-pointer"
                          style={{
                            backgroundColor: open ? 'var(--bg-button)' : 'transparent',
                          }}
                          onMouseEnter={(e) => {
                            if (!open) e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                          }}
                          onMouseLeave={(e) => {
                            if (!open) e.currentTarget.style.backgroundColor = 'transparent';
                          }}
                        >
                          <span
                            className="text-[11px] uppercase tracking-wide w-[74px] text-left flex-shrink-0"
                            style={{ color: 'var(--text-tertiary)' }}
                          >
                            {label}
                          </span>
                          <span
                            className="text-[12.5px] font-medium truncate"
                            style={{ color: 'var(--text-primary)' }}
                          >
                            {current?.display_name || '—'}
                          </span>
                          <ChevronDown
                            size={11}
                            className="ml-auto flex-shrink-0"
                            style={{ color: 'var(--text-tertiary)' }}
                          />
                        </button>
                        {open && (
                          <div
                            className="absolute left-2 right-2 top-full z-50 rounded-lg py-1 max-h-[240px] overflow-y-auto"
                            style={{
                              backgroundColor: 'var(--bg-surface)',
                              border: '1px solid var(--border-subtle)',
                              boxShadow: 'var(--shadow-lg)',
                            }}
                          >
                            {registry.filter((m) => m.available).length === 0 && (
                              <div className="px-3 py-2 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                                No model connected — add a key in Settings → Providers
                              </div>
                            )}
                            {registry.filter((m) => m.available).map((m) => (
                              <button
                                key={m.key}
                                onClick={() => assign(role, m.key)}
                                className="flex items-center gap-2 w-full px-3 h-8 text-left transition-colors duration-100 cursor-pointer"
                                style={{
                                  color: m.key === current?.key
                                    ? 'var(--accent-blue)'
                                    : 'var(--text-primary)',
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.backgroundColor = 'transparent';
                                }}
                              >
                                <span className="text-[12px] truncate">{m.display_name}</span>
                                {m.key === current?.key && (
                                  <span className="ml-auto text-[10px]">active</span>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}

                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Center Zone - App Title - hidden on very small screens */}
      <div
        className="absolute left-1/2 -translate-x-1/2 text-sm font-semibold pointer-events-none hidden xs:block"
        style={{
          color: 'var(--text-primary)',
          letterSpacing: '0.01em',
        }}
      >
        Aplot AI
      </div>

      {/* Right Zone - Upgrade Button */}
      <motion.button
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        className="flex items-center gap-1.5 h-9 sm:h-8 px-2 sm:px-3.5 rounded-full transition-colors duration-200 cursor-pointer flex-shrink-0"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--bg-button)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
        }}
      >
        <span
          className="text-[13px] font-semibold hidden sm:inline"
          style={{ color: 'var(--text-primary)' }}
        >
          Upgrade
        </span>
        <Sparkles size={14} style={{ color: 'var(--text-primary)' }} />
      </motion.button>
    </motion.header>
  );
}
