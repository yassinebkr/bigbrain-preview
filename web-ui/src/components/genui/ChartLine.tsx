interface Dataset {
  label: string;
  data: number[];
  color: string;
}

interface ChartLineData {
  title?: string;
  labels: string[];
  datasets: Dataset[];
}

interface ChartLineProps {
  data: ChartLineData;
}

export default function ChartLine({ data }: ChartLineProps) {
  const { title, labels, datasets } = data;

  const allValues = datasets.flatMap((d) => d.data);
  const maxValue = allValues.length > 0 ? Math.max(...allValues) : 0;
  const minValue = allValues.length > 0 ? Math.min(...allValues) : 0;
  const yMax = maxValue === 0 ? 1 : Math.ceil(maxValue * 1.1);
  const yMin = Math.max(0, Math.floor(minValue * 0.9));
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
    paddingTop + plotHeight - ((val - yMin) / (yMax - yMin || 1)) * plotHeight;
  const xScale = (index: number) =>
    paddingLeft + (index / (labels.length - 1 || 1)) * plotWidth;

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
          const value = yMin + ((yMax - yMin) / yTicks) * i;
          const y = yScale(value);
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
                {Math.round(value)}
              </text>
            </g>
          );
        })}

        {/* Lines and fills */}
        {datasets.map((dataset, datasetIndex) => {
          const points = dataset.data.map((value, i) => ({
            x: xScale(i),
            y: yScale(value),
          }));

          const pathD = points.reduce((acc, point, i) => {
            if (i === 0) return `M ${point.x} ${point.y}`;
            return `${acc} L ${point.x} ${point.y}`;
          }, '');

          const fillD = `${pathD} L ${points[points.length - 1]?.x ?? 0} ${yScale(yMin)} L ${points[0]?.x ?? 0} ${yScale(yMin)} Z`;

          return (
            <g key={datasetIndex}>
              {/* Fill under line */}
              <path
                d={fillD}
                fill={dataset.color}
                opacity={0.15}
              />
              {/* Line */}
              <path
                d={pathD}
                fill="none"
                stroke={dataset.color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {/* Dots at data points */}
              {points.map((point, i) => (
                <circle
                  key={i}
                  cx={point.x}
                  cy={point.y}
                  r={3}
                  fill={dataset.color}
                  stroke="var(--bg-surface)"
                  strokeWidth={1.5}
                />
              ))}
            </g>
          );
        })}

        {/* X-axis labels */}
        {labels.map((label, i) => (
          <text
            key={i}
            x={xScale(i)}
            y={chartHeight - paddingBottom + 20}
            textAnchor="middle"
            fontSize={10}
            fill="var(--text-tertiary)"
          >
            {label}
          </text>
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
