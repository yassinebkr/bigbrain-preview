// Workspace — files only. The TaskBoard (own tab: TasksView) and the
// brain status events (own tab: BrainsView) used to live here; the
// workspace is now the project file explorer plus the research bar.

import { motion } from 'framer-motion';
import { ResearchBar } from './workspace/ResearchBar';
import { FileExplorer } from './workspace/FileExplorer';

export function Workspace() {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: [0, 0, 0.2, 1] }}
      className="flex flex-col h-full w-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      {/* Research Bar - top section */}
      <div
        className="flex-shrink-0 px-4 py-3 border-b"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="max-w-2xl mx-auto">
          <ResearchBar />
        </div>
      </div>

      {/* File explorer — full width, files only */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <FileExplorer />
      </div>
    </motion.div>
  );
}
