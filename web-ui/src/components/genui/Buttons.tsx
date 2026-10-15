import { useAppStore } from '@/store/appStore';

interface ButtonItem {
  label: string;
  action: string;
  style?: 'primary' | 'secondary' | 'outline' | string;
}

interface ButtonsData {
  title?: string;
  buttons: ButtonItem[];
}

interface ButtonsProps {
  data: ButtonsData;
}

export default function Buttons({ data }: ButtonsProps) {
  const { title, buttons } = data;
  const setInputText = useAppStore((s) => s.setInputText);
  const sendMessage = useAppStore((s) => s.sendMessage);

  const handleClick = (action: string) => {
    setInputText(action);
    sendMessage();
  };

  const getStyleClasses = (style?: string) => {
    switch (style) {
      case 'primary':
        return {
          backgroundColor: 'var(--accent-blue)',
          color: '#ffffff',
          border: 'none',
        };
      case 'secondary':
        return {
          backgroundColor: 'var(--bg-button)',
          color: 'var(--text-primary)',
          border: 'none',
        };
      case 'outline':
        return {
          backgroundColor: 'transparent',
          color: 'var(--accent-blue)',
          border: '1px solid var(--accent-blue)',
        };
      default:
        return {
          backgroundColor: 'var(--bg-pill)',
          color: 'var(--text-primary)',
          border: 'none',
        };
    }
  };

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
      <div className="flex flex-wrap gap-2">
        {buttons.map((button, index) => {
          const styles = getStyleClasses(button.style);
          return (
            <button
              key={index}
              onClick={() => handleClick(button.action)}
              className="px-4 py-2 rounded-full text-sm font-medium transition-colors cursor-pointer"
              style={styles}
              onMouseEnter={(e) => {
                if (button.style === 'primary') {
                  e.currentTarget.style.backgroundColor = 'var(--accent-blue-hover)';
                } else {
                  e.currentTarget.style.backgroundColor = 'var(--bg-pill-hover)';
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = styles.backgroundColor;
              }}
            >
              {button.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
