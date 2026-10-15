import { motion } from 'framer-motion';
import type { ConnectionStatus as Status } from '@/types';

interface ConnectionStatusProps {
  status: Status;
}

export function ConnectionStatus({ status }: ConnectionStatusProps) {
  const colors = {
    connected: 'var(--success)',
    connecting: 'var(--warning)',
    disconnected: '#ff3b30',
  };

  return (
    <motion.div
      className="w-2 h-2 rounded-full"
      style={{ backgroundColor: colors[status] }}
      animate={status === 'connecting' ? {
        scale: [1, 1.3, 1],
      } : {}}
      transition={status === 'connecting' ? {
        duration: 1,
        repeat: Infinity,
        ease: 'easeInOut',
      } : {}}
    />
  );
}
