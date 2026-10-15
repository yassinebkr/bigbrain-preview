import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  Search,
  Home,
  Briefcase,
  History,
  Settings,
  LayoutGrid,
  Menu,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { Tooltip } from './Tooltip';

const sidebarItems: { id: string; icon: React.ComponentType<{ size?: number; strokeWidth?: number; style?: React.CSSProperties }> | null; tooltip?: string; isAvatar?: boolean; isSpacer?: boolean }[] = [
  { id: 'avatar', icon: null, tooltip: 'New Chat', isAvatar: true },
  { id: 'newchat', icon: Plus, tooltip: 'New conversation' },
  { id: 'search', icon: Search, tooltip: 'Search (Ctrl+K)' },
  { id: 'home', icon: Home, tooltip: 'Home' },
  { id: 'briefcase', icon: Briefcase, tooltip: 'Workspace' },
  { id: 'history', icon: History, tooltip: 'History' },
  { id: 'settings', icon: Settings, tooltip: 'Settings' },
  { id: 'spacer', icon: null, isSpacer: true },
  { id: 'apps', icon: LayoutGrid, tooltip: 'Apps' },
];

const springEase = [0.34, 1.56, 0.64, 1] as [number, number, number, number];
const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

function SidebarContent({ onItemClick }: { onItemClick?: () => void }) {
  const {
    toggleSidebarPanel,
    sidebarPanel,
    setCommandPaletteOpen,
    setView,
    isStreaming,
  } = useAppStore();

  const handleClick = (id: string) => {
    onItemClick?.();
    switch (id) {
      case 'avatar':
      case 'newchat':
        // A new conversation — clear the transcript (the server keeps its
        // own history; sessions restore it later).
        useAppStore.getState().clearMessages();
        setView('welcome');
        break;
      case 'search':
        setCommandPaletteOpen(true);
        break;
      case 'home':
        setView('welcome');
        break;
      case 'briefcase':
        setView('workspace');
        break;
      case 'apps':
        setView('discover');
        break;
      case 'history':
        toggleSidebarPanel('sessions');
        break;
      case 'settings':
        toggleSidebarPanel('settings');
        break;
      default:
        break;
    }
  };

  return (
    <div className="flex flex-col items-center py-3 px-1.5 h-full" style={{ gap: '4px' }}>
      {sidebarItems.map((item, index) => {
        if (item.isSpacer) {
          return <div key={item.id} className="flex-grow min-h-0" />;
        }

        if (item.isAvatar) {
          return (
            <motion.button
              key={item.id}
              initial={{ opacity: 0, scale: 0.5, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{
                duration: 0.4,
                delay: 0.1 + index * 0.06,
                ease: springEase,
              }}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.92 }}
              onClick={() => handleClick(item.id)}
              className="relative flex items-center justify-center w-9 h-9 rounded-full mb-1 cursor-pointer"
              style={{ backgroundColor: '#0071e3' }}
              aria-label={item.tooltip}
            >
              <img
                src="/robot-icon.png"
                alt="Aplot AI"
                className="w-5 h-5 object-contain"
              />
              {isStreaming && (
                <motion.div
                  className="absolute inset-0 rounded-full"
                  style={{ boxShadow: '0 0 20px rgba(0,113,227,0.3)' }}
                  animate={{
                    boxShadow: [
                      '0 0 10px rgba(0,113,227,0.2)',
                      '0 0 25px rgba(0,113,227,0.5)',
                      '0 0 10px rgba(0,113,227,0.2)',
                    ],
                  }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
              )}
            </motion.button>
          );
        }

        const Icon = item.icon as React.ComponentType<{ size?: number; strokeWidth?: number; style?: React.CSSProperties }>;
        const isActive =
          (item.id === 'history' && sidebarPanel === 'sessions') ||
          (item.id === 'settings' && sidebarPanel === 'settings');

        return (
          <motion.button
            key={item.id}
            initial={{ opacity: 0, scale: 0.5, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{
              duration: 0.35,
              delay: 0.1 + index * 0.06,
              ease: springEase,
            }}
            whileHover={{ scale: 1.12 }}
            whileTap={{ scale: 0.92 }}
            onClick={() => handleClick(item.id)}
            className="relative flex items-center justify-center w-10 h-10 rounded-[10px] transition-colors duration-200 cursor-pointer"
            style={{
              backgroundColor: isActive ? 'var(--bg-icon-hover)' : 'transparent',
              border: isActive ? '1px solid var(--border-subtle)' : '1px solid transparent',
            }}
            onMouseEnter={(e) => {
              if (!isActive) {
                e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isActive) {
                e.currentTarget.style.backgroundColor = 'transparent';
              }
            }}
            aria-label={item.tooltip}
          >
            {/* Active indicator - left border */}
            {isActive && (
              <motion.div
                initial={{ scaleY: 0 }}
                animate={{ scaleY: 1 }}
                transition={{ duration: 0.2, ease: easeOut }}
                className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-5 rounded-r-full"
                style={{ backgroundColor: 'var(--accent-blue)' }}
              />
            )}
            <Tooltip content={item.tooltip}>
              <Icon
                size={20}
                strokeWidth={1.5}
                style={{
                  color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  transition: 'color 0.2s ease',
                }}
              />
            </Tooltip>
          </motion.button>
        );
      })}
    </div>
  );
}

// Desktop sidebar - always visible
function DesktopSidebar() {
  return (
    <motion.aside
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, ease: easeOut }}
      className="fixed left-0 top-0 h-screen flex flex-col items-center z-40 hidden md:flex"
      style={{
        width: '52px',
        backgroundColor: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border-subtle)',
      }}
    >
      <SidebarContent />
    </motion.aside>
  );
}

// Mobile sidebar - drawer that slides in
function MobileSidebar({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 bg-black/50 md:hidden"
            onClick={onClose}
          />
          {/* Drawer */}
          <motion.aside
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ duration: 0.3, ease: easeOut }}
            className="fixed left-0 top-0 h-screen z-50 md:hidden flex flex-col"
            style={{
              width: '72px',
              backgroundColor: 'var(--bg-sidebar)',
              borderRight: '1px solid var(--border-subtle)',
            }}
          >
            <SidebarContent onItemClick={onClose} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

export function Sidebar() {
  const { mobileSidebarOpen, setMobileSidebarOpen } = useAppStore();
  return (
    <>
      <DesktopSidebar />
      <MobileSidebar
        isOpen={mobileSidebarOpen}
        onClose={() => setMobileSidebarOpen(false)}
      />
    </>
  );
}

// Hamburger button for mobile
export function MobileMenuButton() {
  const { setMobileSidebarOpen } = useAppStore();
  return (
    <motion.button
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      whileHover={{ scale: 1.08 }}
      whileTap={{ scale: 0.92 }}
      onClick={() => setMobileSidebarOpen(true)}
      className="md:hidden flex items-center justify-center w-10 h-10 rounded-[10px] cursor-pointer transition-colors duration-200"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
      }}
      aria-label="Open menu"
    >
      <Menu size={20} strokeWidth={1.5} style={{ color: 'var(--text-primary)' }} />
    </motion.button>
  );
}
