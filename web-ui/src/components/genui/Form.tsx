import { useState, useCallback } from 'react';

interface Field {
  name: string;
  type: 'text' | 'textarea' | 'select' | 'checkbox' | string;
  label: string;
  value?: string | boolean;
  placeholder?: string;
  options?: { label: string; value: string }[];
}

interface FormAction {
  label: string;
  action?: string;
}

interface FormData {
  title?: string;
  id?: string;
  fields: Field[];
  actions: FormAction[];
}

interface FormProps {
  data: FormData;
}

export default function Form({ data }: FormProps) {
  const { title, fields, actions } = data;

  const initialValues = fields.reduce<Record<string, string | boolean>>(
    (acc, field) => {
      acc[field.name] = field.value ?? (field.type === 'checkbox' ? false : '');
      return acc;
    },
    {}
  );

  const [values, setValues] = useState<Record<string, string | boolean>>(
    initialValues
  );

  const handleChange = useCallback(
    (name: string, value: string | boolean) => {
      setValues((prev) => ({ ...prev, [name]: value }));
    },
    []
  );

  const handleSubmit = useCallback(
    (formAction?: string) => {
      const json = JSON.stringify({ action: formAction, values });
      // eslint-disable-next-line no-console
      console.log('Form submit:', json);
      // In a real implementation, this would send the form data as a message
      // via the app store. For now, we dispatch a custom event that the
      // connection layer can listen for.
      window.dispatchEvent(
        new CustomEvent('genui-form-submit', { detail: json })
      );
    },
    [values]
  );

  return (
    <div
      className="rounded-[10px] p-[14px_16px]"
      style={{ backgroundColor: 'var(--bg-surface)' }}
    >
      {title && (
        <h3
          className="text-sm font-semibold mb-4"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h3>
      )}
      <div className="flex flex-col gap-3">
        {fields.map((field) => (
          <div key={field.name} className="flex flex-col gap-1.5">
            <label
              className="text-xs font-medium"
              style={{ color: 'var(--text-secondary)' }}
            >
              {field.label}
            </label>

            {field.type === 'textarea' && (
              <textarea
                value={(values[field.name] as string) || ''}
                onChange={(e) => handleChange(field.name, e.target.value)}
                placeholder={field.placeholder}
                rows={4}
                className="w-full rounded-lg px-3 py-2 text-sm resize-none outline-none"
                style={{
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-input)',
                  fontFamily: 'inherit',
                }}
              />
            )}

            {field.type === 'select' && (
              <select
                value={(values[field.name] as string) || ''}
                onChange={(e) => handleChange(field.name, e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none appearance-none cursor-pointer"
                style={{
                  backgroundColor: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-input)',
                }}
              >
                {field.placeholder && (
                  <option value="" disabled>
                    {field.placeholder}
                  </option>
                )}
                {field.options?.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}

            {field.type === 'checkbox' && (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!values[field.name]}
                  onChange={(e) =>
                    handleChange(field.name, e.target.checked)
                  }
                  className="w-4 h-4 rounded cursor-pointer"
                />
                <span
                  className="text-sm"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {field.label}
                </span>
              </label>
            )}

            {field.type !== 'textarea' &&
              field.type !== 'select' &&
              field.type !== 'checkbox' && (
                <input
                  type={field.type || 'text'}
                  value={(values[field.name] as string) || ''}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                  placeholder={field.placeholder}
                  className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                  style={{
                    backgroundColor: 'var(--bg-input)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border-input)',
                  }}
                />
              )}
          </div>
        ))}
      </div>

      {/* Actions */}
      {actions.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-4">
          {actions.map((action, index) => (
            <button
              key={index}
              onClick={() => handleSubmit(action.action || action.label)}
              className="px-4 py-2 rounded-full text-sm font-medium transition-colors cursor-pointer"
              style={{
                backgroundColor:
                  index === 0 ? 'var(--accent-blue)' : 'var(--bg-button)',
                color: index === 0 ? '#ffffff' : 'var(--text-primary)',
              }}
              onMouseEnter={(e) => {
                if (index === 0) {
                  e.currentTarget.style.backgroundColor =
                    'var(--accent-blue-hover)';
                } else {
                  e.currentTarget.style.backgroundColor = 'var(--bg-pill-hover)';
                }
              }}
              onMouseLeave={(e) => {
                if (index === 0) {
                  e.currentTarget.style.backgroundColor = 'var(--accent-blue)';
                } else {
                  e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                }
              }}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
