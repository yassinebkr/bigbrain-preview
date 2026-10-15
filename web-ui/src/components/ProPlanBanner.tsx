import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function ProPlanBanner() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 1.0, ease: easeOut }}
      className="w-full rounded-xl px-3 sm:px-4 py-3 mb-4 sm:mb-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 sm:gap-0"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        height: 'auto',
        minHeight: '52px',
      }}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <Sparkles size={16} style={{ color: 'var(--text-tertiary)' }} />
        <span
          className="text-sm font-medium truncate"
          style={{ color: 'var(--text-primary)' }}
        >
          Unlock more with Pro Plan
        </span>
      </div>

      <motion.button
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        className="h-9 sm:h-8 px-4 rounded-lg text-[13px] font-semibold transition-colors duration-200 cursor-pointer whitespace-nowrap flex-shrink-0"
        style={{
          backgroundColor: 'var(--accent-blue)',
          color: '#ffffff',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--accent-blue-hover)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--accent-blue)';
        }}
      >
        Upgrade Now
      </motion.button>
    </motion.div>
  );
}
