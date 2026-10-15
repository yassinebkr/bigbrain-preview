import { motion } from 'framer-motion';
import { Code2, ChefHat, HeartPulse, MapPin, Wrench, BarChart3 } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

const categories = [
  { icon: Code2, label: 'Coding' },
  { icon: ChefHat, label: 'Cooking' },
  { icon: HeartPulse, label: 'Health' },
  { icon: MapPin, label: 'Trips' },
  { icon: Wrench, label: 'Troubleshoot' },
  { icon: BarChart3, label: 'Data' },
];

export function CategoryPills() {
  const { setInputText } = useAppStore();

  const handleClick = (label: string) => {
    setInputText(`Help me with ${label.toLowerCase()}: `);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 1.2, ease: easeOut }}
      className="flex items-center gap-2 mt-4 overflow-x-auto no-scrollbar w-full justify-start sm:justify-center pb-2 px-1"
    >
      {categories.map((cat, index) => {
        const Icon = cat.icon;
        return (
          <motion.button
            key={`${cat.label}-${index}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 1.25 + index * 0.05 }}
            whileHover={{ scale: 1.04, backgroundColor: 'var(--bg-pill-hover)' }}
            whileTap={{ scale: 0.96 }}
            onClick={() => handleClick(cat.label)}
            className="flex items-center gap-1.5 h-9 sm:h-9 px-3 sm:px-3.5 rounded-full transition-colors duration-200 cursor-pointer flex-shrink-0"
            style={{
              backgroundColor: 'var(--bg-pill)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <Icon size={14} style={{ color: 'var(--text-tertiary)' }} />
            <span
              className="text-xs sm:text-[13px] font-medium"
              style={{ color: 'var(--text-secondary)' }}
            >
              {cat.label}
            </span>
          </motion.button>
        );
      })}
    </motion.div>
  );
}
