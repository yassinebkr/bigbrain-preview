interface Dataset {
  label: string;
  data: number[];
  color: string;
}

interface ChartBarData {
  title?: string;
  labels: string[];
  datasets: Dataset[];
}

interface ChartBarProps {
  data: ChartBarData;
}

export default function ChartBar({ data }: ChartBarProps) {
  const { title, labels, datasets } = data;

  const allValues = datasets.flatMap((d) => d.data);
  const maxValue = allValues.length > 0 ? Math.max(...allValues) : 0;
  const yMax = maxValue === 0 ? 1 : Math.ceil(maxValue * 1.1);
  const yTicks = 5;

  const chartHeight = 200;
  const chartWidth = 500;
  const paddingLeft = 40;
  const paddingRight = 16;
  const paddingTop = 16;
  const paddingBottom = 40;
  const plotWidth = chartWidth - paddingLeft - paddingRight;
  const plotHeight = chartHeight - paddingTop - paddingBottom;

  const yScale = (val: number) =>
    paddingTop + plotHeight - (val / yMax) * plotHeight;

  const barGroupWidth = plotWidth / labels.length;
  const barPadding = barGroupWidth * 0.2;
  const barWidth =
    datasets.length > 0
      ? (barGroupWidth - barPadding) / datasets.length
      : 0;

  return (
    <div
      className="rounded-[10px] p-[14px_16px]"
      style={{ backgroundColor: 'var(--bg-surface)' }}
    >
      {title && (
        <h3
          className="text-sm font-semibold mb-3"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h3>
      )}
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        className="overflow-visible"
      >
        {/* Grid lines */}
        {Array.from({ length: yTicks + 1 }).map((_, i) => {
          const y = yScale((yMax / yTicks) * i);
          return (
            <g key={`grid-${i}`}>
              <line
                x1={paddingLeft}
                y1={y}
                x2={chartWidth - paddingRight}
                y2={y}
                stroke="var(--border-subtle)"
                strokeWidth={0.5}
                strokeDasharray="2,2"
              />
              <text
                x={paddingLeft - 8}
                y={y + 4}
                textAnchor="end"
                fontSize={10}
                fill="var(--text-tertiary)"
              >
                {Math.round((yMax / yTicks) * i)}
              </text>
            </g>
          );
        })}

        {/* Bars */}
        {labels.map((label, labelIndex) => (
          <g key={label}>
            {datasets.map((dataset, datasetIndex) => {
              const value = dataset.data[labelIndex] ?? 0;
              const x =
                paddingLeft +
                labelIndex * barGroupWidth +
                barPadding / 2 +
                datasetIndex * barWidth;
              const y = yScale(value);
              const height = yScale(0) - y;

              return (
                <rect
                  key={`${label}-${datasetIndex}`}
                  x={x}
                  y={y}
                  width={Math.max(barWidth - 2, 1)}
                  height={height}
                  fill={dataset.color}
                  rx={2}
                />
              );
            })}

            {/* X-axis label */}
            <text
              x={
                paddingLeft +
                labelIndex * barGroupWidth +
                barGroupWidth / 2
              }
              y={chartHeight - paddingBottom + 20}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-tertiary)"
            >
              {label}
            </text>
          </g>
        ))}
      </svg>

      {/* Legend */}
      {datasets.length > 0 && (
        <div className="flex flex-wrap gap-3 mt-2">
          {datasets.map((dataset, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: dataset.color }}
              />
              <span
                className="text-xs"
                style={{ color: 'var(--text-secondary)' }}
              >
                {dataset.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
