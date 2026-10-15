// TasksView — the TaskBoard as its own tab, separated from the
// workspace (files). Agent tasks (bus events) and manual tasks live on
// the same board; QuickActions stays with it.

import { motion } from 'framer-motion';
import { QuickActions } from './workspace/QuickActions';
import { TaskBoard } from './workspace/TaskBoard';

export function TasksView() {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: [0, 0, 0.2, 1] }}
      className="flex flex-col h-full w-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="flex-1 flex flex-col overflow-hidden max-w-[1400px] w-full mx-auto px-2 sm:px-4 py-3 sm:py-4">
        <QuickActions />
        <div className="flex-1 min-h-0 mt-3">
          <TaskBoard />
        </div>
      </div>
    </motion.div>
  );
}
