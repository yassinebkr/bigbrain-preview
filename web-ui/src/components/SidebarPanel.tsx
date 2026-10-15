import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { SessionsPanel } from './SessionsPanel';
import { SettingsPanel } from './SettingsPanel';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function SidebarPanel() {
  const { sidebarPanel, setSidebarPanel } = useAppStore();
  const isOpen = sidebarPanel !== null;

  const handleClose = () => setSidebarPanel(null);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop overlay - full screen on mobile, starts at 52px on desktop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-[35] bg-black/30 md:left-[52px] left-0"
            onClick={handleClose}
          />

          {/* Panel - starts at left edge on mobile, at 52px on desktop */}
          <motion.div
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ duration: 0.3, ease: easeOut }}
            className="fixed z-[36] flex left-0 md:left-[52px] top-0 bottom-0"
          >
            {sidebarPanel === 'sessions' && <SessionsPanel />}
            {sidebarPanel === 'settings' && <SettingsPanel />}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
