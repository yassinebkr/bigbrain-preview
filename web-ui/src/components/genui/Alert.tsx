import {
  Info,
  AlertTriangle,
  CircleX,
  CircleCheck,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface AlertData {
  title: string;
  message: string;
  severity: 'info' | 'warning' | 'error' | 'success';
}

interface AlertProps {
  data: AlertData;
}

const SEVERITY_CONFIG: Record<
  string,
  { color: string; Icon: LucideIcon }
> = {
  info: { color: '#3b82f6', Icon: Info },
  warning: { color: '#f59e0b', Icon: AlertTriangle },
  error: { color: '#ef4444', Icon: CircleX },
  success: { color: '#10b981', Icon: CircleCheck },
};

export default function Alert({ data }: AlertProps) {
  const { title, message, severity } = data;
  const config = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;
  const { color, Icon } = config;

  return (
    <div
      className="rounded-[10px] p-[14px_16px] flex items-start gap-3"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderLeft: `4px solid ${color}`,
      }}
    >
      <Icon size={18} color={color} className="flex-shrink-0 mt-0.5" />
      <div className="flex flex-col gap-0.5 min-w-0">
        <h4
          className="text-sm font-semibold"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h4>
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--text-secondary)' }}
        >
          {message}
        </p>
      </div>
    </div>
  );
}
