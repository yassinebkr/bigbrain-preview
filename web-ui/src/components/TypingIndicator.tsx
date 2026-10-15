import { motion } from 'framer-motion';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, ease: easeOut }}
      className="flex justify-start w-full"
    >
      <div className="flex items-center gap-2">
        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center"
          style={{ backgroundColor: '#0071e3' }}
        >
          <img
            src="/robot-icon.png"
            alt="AI"
            className="w-4 h-4 object-contain"
          />
        </div>

        {/* Typing Dots */}
        <div
          className="flex items-center justify-center h-9 px-4 rounded-[18px] gap-1"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: 'var(--text-tertiary)' }}
              animate={{
                scale: [1, 1.4, 1],
              }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                delay: i * 0.15,
                ease: 'easeInOut',
              }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  );
}
