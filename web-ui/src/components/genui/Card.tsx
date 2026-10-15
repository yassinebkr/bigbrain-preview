import * as LucideIcons from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface CardData {
  title?: string;
  text?: string;
  icon?: string;
}

interface CardProps {
  data: CardData;
}

export default function Card({ data }: CardProps) {
  const { title, text, icon } = data;

  const IconComponent = icon
    ? (LucideIcons[icon as keyof typeof LucideIcons] as LucideIcon | undefined)
    : null;

  return (
    <div
      className="rounded-[10px] p-[14px_16px]"
      style={{
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      {title && (
        <div className="flex items-center gap-2 mb-2">
          {IconComponent && (
            <IconComponent size={18} color="var(--text-secondary)" />
          )}
          <h3
            className="text-sm font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            {title}
          </h3>
        </div>
      )}
      {!title && IconComponent && (
        <div className="mb-2">
          <IconComponent size={18} color="var(--text-secondary)" />
        </div>
      )}
      {text && (
        <div
          className="text-sm leading-relaxed whitespace-pre-wrap"
          style={{ color: 'var(--text-secondary)' }}
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: text }}
        />
      )}
    </div>
  );
}
