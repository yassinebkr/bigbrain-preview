import * as LucideIcons from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface HeroData {
  title: string;
  subtitle?: string;
  icon?: string;
  badge?: string;
  gradient?: string;
}

interface HeroProps {
  data: HeroData;
}

export default function Hero({ data }: HeroProps) {
  const { title, subtitle, icon, badge, gradient } = data;

  const IconComponent = icon
    ? (LucideIcons[icon as keyof typeof LucideIcons] as LucideIcon | undefined)
    : null;

  const bgGradient = gradient || 'linear-gradient(135deg, #7c3aed, #3b82f6)';

  return (
    <div
      className="w-full rounded-[10px] p-6 flex flex-col items-start gap-3"
      style={{ background: bgGradient }}
    >
      <div className="flex items-center gap-3">
        {IconComponent && (
          <div className="p-2 rounded-lg bg-white/20 backdrop-blur-sm">
            <IconComponent size={24} color="#ffffff" />
          </div>
        )}
        {badge && (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-white/20 text-white backdrop-blur-sm">
            {badge}
          </span>
        )}
      </div>
      <h2 className="text-xl font-bold text-white">{title}</h2>
      {subtitle && (
        <p className="text-sm text-white/80 leading-relaxed">{subtitle}</p>
      )}
    </div>
  );
}
