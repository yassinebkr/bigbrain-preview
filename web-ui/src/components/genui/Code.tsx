import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

interface CodeData {
  language?: string;
  code: string;
}

interface CodeProps {
  data: CodeData;
}

function syntaxHighlight(code: string, language?: string): string {
  if (!language) return code;

  let highlighted = code;

  // Keywords: blue (#5ac8fa)
  const keywords = [
    'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for',
    'while', 'import', 'export', 'from', 'default', 'class', 'extends',
    'new', 'this', 'try', 'catch', 'async', 'await', 'type', 'interface',
    'boolean', 'number', 'string', 'void', 'any', 'null', 'undefined',
    'true', 'false', 'switch', 'case', 'break', 'continue', 'throw',
    'yield', 'typeof', 'instanceof', 'in', 'of', 'as', 'is',
  ];

  // Strings: green (#34c759)
  highlighted = highlighted.replace(
    /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g,
    '<span style="color:#34c759">$1</span>'
  );

  // Comments: gray
  highlighted = highlighted.replace(
    /(\/\/.*$|\/\*[\s\S]*?\*\/|#.*$)/gm,
    '<span style="color:#6e6e73">$1</span>'
  );

  // Keywords: blue - must come after strings/comments
  const keywordRegex = new RegExp(
    `\\b(${keywords.join('|')})\\b`,
    'g'
  );
  highlighted = highlighted.replace(
    keywordRegex,
    '<span style="color:#5ac8fa">$1</span>'
  );

  return highlighted;
}

export default function Code({ data }: CodeProps) {
  const { language, code } = data;
  const [copied, setCopied] = useState(false);

  const lines = code.split('\n');
  const lineNumbers = lines.map((_, i) => i + 1);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div
      className="rounded-[10px] overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {/* Header bar */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{
          backgroundColor: 'var(--bg-input)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: 'var(--text-tertiary)' }}
        >
          {language || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors"
          style={{
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-button)',
          }}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = 'var(--bg-pill-hover)')
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = 'var(--bg-button)')
          }
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      {/* Code content */}
      <div className="flex overflow-x-auto p-4">
        {/* Line numbers */}
        <pre
          className="flex-shrink-0 text-right pr-4 select-none"
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
            lineHeight: '1.6',
            color: 'var(--text-tertiary)',
          }}
        >
          {lineNumbers.map((num) => (
            <div key={num}>{num}</div>
          ))}
        </pre>

        {/* Code */}
        <pre
          className="flex-1"
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
            lineHeight: '1.6',
            color: 'var(--text-primary)',
          }}
        >
          <code
            dangerouslySetInnerHTML={{
              __html: syntaxHighlight(code, language),
            }}
          />
        </pre>
      </div>
    </div>
  );
}
