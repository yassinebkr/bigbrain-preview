import { motion } from 'framer-motion';
import { useState } from 'react';
import { Folder, CheckSquare, Search } from 'lucide-react';
import { ResearchBar } from './workspace/ResearchBar';
import { FileExplorer } from './workspace/FileExplorer';
import { QuickActions } from './workspace/QuickActions';
import { TaskBoard } from './workspace/TaskBoard';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

type WorkspaceTab = 'files' | 'tasks' | 'research';

export function Workspace() {
  const [mobileTab, setMobileTab] = useState<WorkspaceTab>('files');

  const tabs: { id: WorkspaceTab; label: string; icon: React.ReactNode }[] = [
    { id: 'files', label: 'Files', icon: <Folder size={16} /> },
    { id: 'tasks', label: 'Tasks', icon: <CheckSquare size={16} /> },
    { id: 'research', label: 'Research', icon: <Search size={16} /> },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: easeOut }}
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

      {/* Mobile Tab Navigation */}
      <div className="lg:hidden flex items-center border-b flex-shrink-0 overflow-x-auto no-scrollbar" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex-1 flex min-w-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setMobileTab(tab.id)}
              className="flex-1 flex items-center justify-center gap-1.5 px-2 sm:px-3 py-3 text-xs font-medium transition-colors duration-150 cursor-pointer min-w-[80px]"
              style={{
                color: mobileTab === tab.id ? 'var(--accent-blue)' : 'var(--text-secondary)',
                borderBottom: mobileTab === tab.id ? '2px solid var(--accent-blue)' : '2px solid transparent',
                backgroundColor: mobileTab === tab.id ? 'rgba(0,113,227,0.06)' : 'transparent',
              }}
            >
              {tab.icon}
              <span className="truncate">{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Main workspace area - Desktop: side-by-side, Mobile: tab-based */}
      <div className="flex flex-1 overflow-hidden">
        {/* Desktop: File Explorer - left panel */}
        <div
          className="hidden lg:flex w-[280px] xl:w-[320px] 2xl:w-[360px] flex-shrink-0 border-r flex-col"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <FileExplorer />
        </div>

        {/* Desktop: Right panel - QuickActions + TaskBoard */}
        <div className="hidden lg:flex flex-1 flex-col overflow-hidden min-w-0">
          <QuickActions />
          <TaskBoard />
        </div>

        {/* Mobile: Tab-based content */}
        <div className="lg:hidden flex-1 flex flex-col overflow-hidden min-w-0">
          {mobileTab === 'files' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <FileExplorer />
            </div>
          )}
          {mobileTab === 'tasks' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <QuickActions />
              <TaskBoard />
            </div>
          )}
          {mobileTab === 'research' && (
            <div className="flex-1 flex items-center justify-center text-sm" style={{ color: 'var(--text-tertiary)' }}>
              <div className="text-center">
                <Search size={32} strokeWidth={1} className="mx-auto mb-2 opacity-30" />
                <p>Use the research bar above to start searching</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
