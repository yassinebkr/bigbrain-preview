import { useState } from 'react';
import type { ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, Sparkles } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { ConnectionStatus } from './ConnectionStatus';

const models = [
  { id: 'aplot-3.5-pro', name: 'Aplot AI 3.5 Pro', active: true },
  { id: 'aplot-4', name: 'Aplot AI 4', active: false },
  { id: 'aplot-4-vision', name: 'Aplot AI 4 Vision', active: false },
];

interface TopBarProps {
  children?: ReactNode;
}

export function TopBar({ children }: TopBarProps) {
  const { connectionStatus } = useAppStore();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState(models[0]);

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
            onClick={() => setDropdownOpen(!dropdownOpen)}
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
              {selectedModel.name}
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
                  {models.map((model) => (
                    <button
                      key={model.id}
                      onClick={() => {
                        setSelectedModel(model);
                        setDropdownOpen(false);
                      }}
                      className="flex items-center gap-3 w-full h-10 px-4 transition-colors duration-150 cursor-pointer relative"
                      style={{
                        backgroundColor: model.active ? 'var(--bg-button)' : 'transparent',
                      }}
                      onMouseEnter={(e) => {
                        if (!model.active) {
                          e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!model.active) {
                          e.currentTarget.style.backgroundColor = 'transparent';
                        }
                      }}
                    >
                      {model.active && (
                        <div
                          className="w-0.5 h-4 rounded-full absolute left-0"
                          style={{ backgroundColor: 'var(--accent-blue)' }}
                        />
                      )}
                      <img
                        src="/robot-icon.png"
                        alt=""
                        className="w-4 h-4 object-contain"
                      />
                      <span
                        className="text-sm font-medium"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {model.name}
                      </span>
                    </button>
                  ))}
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
