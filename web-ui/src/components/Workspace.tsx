// Workspace — files only. The TaskBoard (own tab: TasksView) and the
// brain status events (own tab: BrainsView) used to live here; the
// workspace is now the project file explorer plus the research bar.

import { motion } from 'framer-motion';
import { useState } from 'react';
import { useAppStore } from '@/store/appStore';
import { ResearchBar } from './workspace/ResearchBar';
import { FileExplorer } from './workspace/FileExplorer';
import { LocalProjects } from './workspace/LocalProjects';

export function Workspace() {
  const [local, setLocal] = useState(false);
  const sessionId = useAppStore((state) => state.activeSessionKey);
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: [0, 0, 0.2, 1] }}
      className="flex flex-col h-full w-full"
      style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}
    >
      {/* Research Bar - top section */}
      <div
        className="flex-shrink-0 px-4 py-3 border-b"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-xl bg-white/5 p-1 text-sm" aria-label="Origine des projets">
            <button aria-pressed={!local} className={`rounded-lg px-3 py-2 ${!local ? 'bg-white/10' : ''}`} onClick={() => setLocal(false)}>Espace BigBrain</button>
            <button aria-pressed={local} className={`rounded-lg px-3 py-2 ${local ? 'bg-white/10' : ''}`} onClick={() => setLocal(true)}>Dossiers locaux</button>
          </div>
          {!local && <div className="flex-1"><ResearchBar /></div>}
        </div>
      </div>

      {/* File explorer — full width, files only */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {local ? <LocalProjects key={sessionId} /> : <FileExplorer />}
      </div>
    </motion.div>
  );
}
