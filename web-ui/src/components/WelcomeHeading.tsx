import { motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function WelcomeHeading() {
  const user = useAppStore((s) => s.user);
  const lines = [
    { text: `Hi ${user?.name || 'there'}`, weight: 500 },
    { text: 'Ready to', weight: 600 },
    { text: 'Achieve Great Things?', weight: 600 },
  ];

  return (
    <motion.div
      className="text-center mb-6 sm:mb-8 mt-4 sm:mt-8 px-2 w-full"
      style={{ maxWidth: 'min(500px, 90vw)' }}
    >
      {lines.map((line, index) => (
        <motion.div
          key={index}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.6,
            delay: 0.4 + index * 0.1,
            ease: easeOut,
          }}
          className="text-xl sm:text-[28px] md:text-[32px] leading-tight px-2"
          style={{
            fontWeight: line.weight,
            color: 'var(--text-primary)',
            letterSpacing: '-0.02em',
            lineHeight: 1.2,
          }}
        >
          {line.text}
        </motion.div>
      ))}
    </motion.div>
  );
}
