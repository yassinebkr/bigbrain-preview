import { motion } from 'framer-motion';
import { X, LogOut, Moon, Sun } from 'lucide-react';
import { BigBrainProviders } from './BigBrainProviders';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function SettingsPanel() {
  const {
    theme,
    toggleTheme,
    settings,
    toggleSetting,
    setSidebarPanel,
    user,
    logout,
  } = useAppStore();

  return (
    <motion.div
      initial={{ x: '-100%' }}
      animate={{ x: 0 }}
      exit={{ x: '-100%' }}
      transition={{ duration: 0.3, ease: easeOut }}
      className="h-full flex flex-col"
      style={{
        width: '340px',
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
          Settings
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

      {/* Settings Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {/* Theme Toggle */}
        <div className="space-y-3">
          <span
            className="text-sm font-medium block"
            style={{ color: 'var(--text-primary)' }}
          >
            Theme
          </span>
          <div
            className="flex rounded-lg overflow-hidden"
            style={{
              backgroundColor: 'var(--bg-button)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <button
              onClick={() => theme !== 'dark' && toggleTheme()}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors duration-200 cursor-pointer"
              style={{
                backgroundColor: theme === 'dark' ? 'var(--accent-blue)' : 'transparent',
                color: theme === 'dark' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              <Moon size={16} />
              Dark
            </button>
            <button
              onClick={() => theme !== 'light' && toggleTheme()}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors duration-200 cursor-pointer"
              style={{
                backgroundColor: theme === 'light' ? 'var(--accent-blue)' : 'transparent',
                color: theme === 'light' ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              <Sun size={16} />
              Light
            </button>
          </div>
        </div>

        {/* GenUI Toggle */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span
                className="text-sm font-medium block"
                style={{ color: 'var(--text-primary)' }}
              >
                Generative UI
              </span>
              <span
                className="text-xs"
                style={{ color: 'var(--text-tertiary)' }}
              >
                Enable AI-generated interactive components
              </span>
            </div>
            <button
              onClick={() => toggleSetting('genui')}
              className="relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer"
              style={{
                backgroundColor: settings.genui ? 'var(--accent-blue)' : 'var(--bg-button)',
              }}
            >
              <div
                className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform duration-200"
                style={{
                  transform: settings.genui ? 'translateX(22px)' : 'translateX(2px)',
                }}
              />
            </button>
          </div>
        </div>

        {/* Auto Speech Toggle */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span
                className="text-sm font-medium block"
                style={{ color: 'var(--text-primary)' }}
              >
                Auto Speech
              </span>
              <span
                className="text-xs"
                style={{ color: 'var(--text-tertiary)' }}
              >
                Automatically read AI responses aloud
              </span>
            </div>
            <button
              onClick={() => toggleSetting('autoSpeech')}
              className="relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer"
              style={{
                backgroundColor: settings.autoSpeech ? 'var(--accent-blue)' : 'var(--bg-button)',
              }}
            >
              <div
                className="absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform duration-200"
                style={{
                  transform: settings.autoSpeech ? 'translateX(22px)' : 'translateX(2px)',
                }}
              />
            </button>
          </div>
        </div>

        {/* Account Section */}
        <div className="space-y-3 pt-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <span
            className="text-sm font-semibold block"
            style={{ color: 'var(--text-primary)' }}
          >
            Account
          </span>
          <div
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg"
            style={{
              backgroundColor: 'var(--bg-button)',
            }}
          >
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold"
              style={{
                backgroundColor: '#0071e3',
                color: '#ffffff',
              }}
            >
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <div className="flex flex-col">
              <span
                className="text-sm font-medium"
                style={{ color: 'var(--text-primary)' }}
              >
                {user?.name || 'User'}
              </span>
              <span
                className="text-xs"
                style={{ color: 'var(--text-tertiary)' }}
              >
                {user?.email || 'No email'}
              </span>
            </div>
          </div>
          <button
            onClick={logout}
            className="flex items-center justify-center gap-2 w-full h-10 rounded-lg text-sm font-medium transition-colors duration-200 cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-button)',
              color: 'var(--text-primary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255,59,48,0.1)';
              e.currentTarget.style.color = '#ff3b30';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-button)';
              e.currentTarget.style.color = 'var(--text-primary)';
            }}
          >
            <LogOut size={16} />
            Log Out
          </button>
        </div>
      </div>

      {/* BigBrain providers: model registry + subscription connections */}
      <div
        className="border-t"
        style={{ borderBottom: 'none', borderColor: 'var(--border-subtle)' }}
      >
        <BigBrainProviders />
      </div>
    </motion.div>
  );
}
