// RobotMascot — the welcome screen mascot.
// Simple and centered: the robot image, then the two suggestion pills in a
// row below it — all in normal flow (the previous absolutely-positioned
// bubbles were never optically centered inside their pills).

import { motion } from 'framer-motion';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

function Bubble({ text, delay }: { text: string; delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: easeOut }}
      className="flex items-center px-3.5 py-2 rounded-2xl"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <img
        src="/robot-icon.png"
        alt=""
        className="w-3.5 h-3.5 object-contain flex-shrink-0"
      />
      <span
        className="ml-2 text-[13px] font-medium leading-none"
        style={{ color: 'var(--text-primary)' }}
      >
        {text}
      </span>
    </motion.div>
  );
}

export function RobotMascot() {
  return (
    <div className="flex flex-col items-center gap-3 mb-6 sm:mb-8 px-4 w-full">
      <motion.img
        src="/robot-mascot.png"
        alt="Aplot AI Robot"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.45, delay: 0.5, ease: easeOut }}
        className="w-[64px] h-[64px] sm:w-[85px] sm:h-[85px] md:w-[100px] md:h-[100px] object-contain"
      />
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        <Bubble text="Hey there! Need a boost?" delay={0.8} />
        <Bubble text="What are we building today?" delay={0.95} />
      </div>
    </div>
  );
}
