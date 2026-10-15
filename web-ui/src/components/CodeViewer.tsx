// CodeViewer — modal presentation of the shared CodeSurface, opened
// from the run panel's file list (chat context). The same surface is
// embedded inline in the workspace's file explorer — one code UI, two
// presentations.

import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { CodeSurface } from './CodeSurface';

export function CodeViewer() {
  const path = useAppStore((s) => s.viewerFilePath);
  const closeFileViewer = useAppStore((s) => s.closeFileViewer);
  const setView = useAppStore((s) => s.setView);
  const setPendingOpenFile = useAppStore((s) => s.setPendingOpenFile);

  const openInWorkspace = () => {
    if (!path) return;
    setPendingOpenFile(path);
    setView('workspace');
    closeFileViewer();
  };

  return (
    <AnimatePresence>
      {path && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ backgroundColor: 'rgba(0, 0, 0, 0.55)' }}
          onClick={closeFileViewer}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0, 0, 0.2, 1] }}
            className="w-full max-w-[860px] max-h-[80vh] flex flex-col rounded-xl overflow-hidden"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <CodeSurface path={path} onClose={closeFileViewer} onOpenInWorkspace={openInWorkspace} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
