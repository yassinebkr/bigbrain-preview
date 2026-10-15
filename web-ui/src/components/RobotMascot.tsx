import { motion } from 'framer-motion';

const springEase = [0.34, 1.56, 0.64, 1] as [number, number, number, number];
const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function RobotMascot() {
  return (
    <div className="relative flex justify-center mb-6 sm:mb-8 px-4 w-full max-w-[320px] sm:max-w-none">
      {/* Robot Image */}
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{
          duration: 0.5,
          delay: 0.6,
          ease: springEase,
        }}
        className="relative w-[60px] h-[60px] sm:w-[85px] sm:h-[85px] md:w-[100px] md:h-[100px]"
      >
        <img
          src="/robot-mascot.png"
          alt="Aplot AI Robot"
          className="w-full h-full object-contain"
        />

        {/* Left Speech Bubble - hidden on very small screens, repositioned on mobile */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.9, ease: easeOut }}
          className="absolute hidden sm:flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 sm:py-2 rounded-2xl whitespace-nowrap"
          style={{
            right: '60%',
            top: '-10%',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <motion.div
            animate={{ y: [0, -4, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut', delay: 1.6 }}
            className="flex items-center gap-1.5"
          >
            <img
              src="/robot-icon.png"
              alt=""
              className="w-3 h-3 sm:w-3.5 sm:h-3.5 object-contain"
            />
            <span
              className="text-xs sm:text-[13px] font-medium"
              style={{ color: 'var(--text-primary)' }}
            >
              Hey there! Need a boost?
            </span>
          </motion.div>
        </motion.div>

        {/* Right Speech Bubble - hidden on very small screens */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 1.05, ease: easeOut }}
          className="absolute hidden sm:flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 sm:py-2 rounded-2xl whitespace-nowrap"
          style={{
            left: '55%',
            top: '-25%',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <motion.div
            animate={{ y: [0, -4, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut', delay: 1.8 }}
            className="flex items-center gap-1.5"
          >
            <img
              src="/robot-icon.png"
              alt=""
              className="w-3 h-3 sm:w-3.5 sm:h-3.5 object-contain"
            />
            <span
              className="text-xs sm:text-[13px] font-medium"
              style={{ color: 'var(--text-primary)' }}
            >
              Hey there! Need a boost?
            </span>
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  );
}
