interface TableData {
  title?: string;
  headers: string[];
  rows: (string | number | null | undefined)[][];
}

interface TableProps {
  data: TableData;
}

export default function Table({ data }: TableProps) {
  const { title, headers, rows } = data;

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
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr
              style={{
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              {headers.map((header, index) => (
                <th
                  key={index}
                  className="text-left py-2 px-3 font-semibold whitespace-nowrap"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                style={{
                  borderBottom:
                    rowIndex < rows.length - 1
                      ? '1px solid var(--border-subtle)'
                      : 'none',
                }}
              >
                {row.map((cell, cellIndex) => (
                  <td
                    key={cellIndex}
                    className="py-2 px-3 whitespace-nowrap"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {cell ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
