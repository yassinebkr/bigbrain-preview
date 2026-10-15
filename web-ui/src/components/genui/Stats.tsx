interface StatItem {
  label: string;
  value: string | number;
  color?: string;
  trend?: 'up' | 'down' | string;
}

interface StatsData {
  title?: string;
  items: StatItem[];
}

interface StatsProps {
  data: StatsData;
}

export default function Stats({ data }: StatsProps) {
  const { title, items } = data;

  return (
    <div
      className="rounded-[10px] p-[14px_16px]"
      style={{
        backgroundColor: 'var(--bg-surface)',
      }}
    >
      {title && (
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h3>
      )}
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))' }}
      >
        {items.map((item, index) => (
          <div key={index} className="flex flex-col gap-1">
            <span
              className="text-xs"
              style={{ color: 'var(--text-secondary)' }}
            >
              {item.label}
            </span>
            <div className="flex items-center gap-1.5">
              <span
                className="text-xl font-bold"
                style={{ color: item.color || 'var(--text-primary)' }}
              >
                {item.value}
              </span>
              {item.trend && (
                <span
                  className="text-xs font-medium"
                  style={{
                    color:
                      item.trend === 'up'
                        ? 'var(--success)'
                        : item.trend === 'down'
                          ? 'var(--warning)'
                          : 'var(--text-tertiary)',
                  }}
                >
                  {item.trend === 'up' ? '↑' : item.trend === 'down' ? '↓' : item.trend}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
