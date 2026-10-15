import { Mic, Square } from 'lucide-react';
import { motion } from 'framer-motion';

interface VoiceRecorderProps {
  isRecording: boolean;
  onStop: () => void;
}

export function VoiceRecorder({ isRecording, onStop }: VoiceRecorderProps) {
  if (!isRecording) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      className="flex items-center gap-3 px-4 py-2 rounded-full mb-2"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {/* Pulse ring animation */}
      <div className="relative">
        <div
          className="absolute inset-0 rounded-full animate-pulse-ring"
          style={{ backgroundColor: 'var(--accent-blue)' }}
        />
        <div
          className="relative w-8 h-8 rounded-full flex items-center justify-center"
          style={{ backgroundColor: 'var(--accent-blue)' }}
        >
          <Mic size={16} color="#ffffff" />
        </div>
      </div>

      <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        Recording...
      </span>

      {/* Waveform bars */}
      <div className="flex items-center gap-0.5 h-6">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="w-1 rounded-full"
            style={{ backgroundColor: 'var(--accent-blue)' }}
            animate={{
              height: [8, 20, 8],
            }}
            transition={{
              duration: 0.8,
              repeat: Infinity,
              delay: i * 0.15,
              ease: 'easeInOut',
            }}
          />
        ))}
      </div>

      <button
        onClick={onStop}
        className="ml-2 p-1.5 rounded-full hover:opacity-70 transition-opacity"
        style={{ backgroundColor: 'var(--bg-button)' }}
        aria-label="Stop recording"
      >
        <Square size={14} style={{ color: 'var(--text-primary)' }} />
      </button>
    </motion.div>
  );
}
