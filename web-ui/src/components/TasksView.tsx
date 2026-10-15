// TasksView — the TaskBoard as its own tab, separated from the
// workspace (files). Agent tasks (bus events) and manual tasks live on
// the same board; the board renders its own header and add-task
// affordances — no workspace quick actions here.

import { motion } from 'framer-motion';
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
        <TaskBoard />
      </div>
    </motion.div>
  );
}
