import type { LucideIcon } from 'lucide-react';

interface ActionPillProps {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
}

export function ActionPill({ icon: Icon, label, onClick }: ActionPillProps) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 h-9 px-3 rounded-full transition-all duration-200 cursor-pointer"
      style={{
        backgroundColor: 'transparent',
        border: '1px solid var(--border-subtle)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--bg-button)';
        e.currentTarget.style.borderColor = 'var(--border-input)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent';
        e.currentTarget.style.borderColor = 'var(--border-subtle)';
      }}
    >
      <Icon size={14} style={{ color: 'var(--text-tertiary)' }} />
      <span
        className="text-[13px] font-medium"
        style={{ color: 'var(--text-secondary)' }}
      >
        {label}
      </span>
    </button>
  );
}
