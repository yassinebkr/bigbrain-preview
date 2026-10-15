import { motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function StreamingMessage() {
  const { streamingText } = useAppStore();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2, ease: easeOut }}
      className="flex justify-start w-full"
    >
      <div className="flex flex-row items-start gap-2 w-full max-w-[92%] sm:max-w-[85%] md:max-w-[82%] lg:max-w-[78%] xl:max-w-[75%]">
        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center mt-1"
          style={{ backgroundColor: '#0071e3' }}
        >
          <img
            src="/robot-icon.png"
            alt="AI"
            className="w-4 h-4 object-contain"
          />
        </div>

        <div className="flex flex-col items-start">
          {/* Bubble */}
          <div
            className="px-4 py-3 w-full min-h-[44px]"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid var(--border-subtle)',
              borderRadius: '18px 18px 18px 4px',
            }}
          >
            <p
              className="text-[15px] leading-relaxed"
              style={{
                color: 'var(--text-primary)',
                fontWeight: 400,
                lineHeight: 1.6,
              }}
            >
              {streamingText}
              <span
                className="inline-block w-[2px] h-[1.1em] ml-0.5 align-text-bottom animate-blink"
                style={{ backgroundColor: 'var(--accent-blue)' }}
              />
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
