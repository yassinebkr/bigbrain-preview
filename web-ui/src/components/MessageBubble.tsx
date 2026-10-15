import { motion } from 'framer-motion';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Copy, ThumbsUp, ThumbsDown } from 'lucide-react';
import { useState } from 'react';
import type { Message } from '@/types';

interface MessageBubbleProps {
  message: Message;
  index: number;
}

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [showActions, setShowActions] = useState(false);

  return (
    <motion.div
      initial={{
        opacity: 0,
        x: isUser ? 30 : -20,
        scale: isUser ? 0.95 : 1,
      }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: easeOut }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} w-full`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className={`flex ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start gap-2 w-full max-w-[92%] sm:max-w-[85%] md:max-w-[82%] lg:max-w-[78%] xl:max-w-[75%]`}>
        {/* Avatar (AI only) */}
        {!isUser && (
          <div
            className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center mt-1"
            style={{ backgroundColor: '#0071e3' }}
          >
            <img
              src="/robot-icon.png"
              alt="AI"
              className="w-4 h-4 object-contain"
            />
          </div>
        )}

        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          {/* Bubble */}
          <div
            className="px-4 py-3"
            style={{
              backgroundColor: isUser ? '#0071e3' : 'transparent',
              border: isUser ? 'none' : '1px solid var(--border-subtle)',
              borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
              boxShadow: isUser ? 'var(--shadow-sm)' : 'none',
              maxWidth: '100%',
            }}
          >
            <p
              className="text-[15px] leading-relaxed"
              style={{
                color: isUser ? '#ffffff' : 'var(--text-primary)',
                fontWeight: 400,
                lineHeight: 1.6,
              }}
            >
              {isUser ? (
                <span className="whitespace-pre-wrap">{message.content}</span>
              ) : (
                // Real markdown for assistant replies — raw `**bold**`
                // markers and unparsed lists are unreadable.
                <Markdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    p: ({ children }) => (
                      <p className="whitespace-pre-wrap m-0">{children}</p>
                    ),
                    ul: ({ children }) => (
                      <ul className="list-disc pl-5 my-1.5 space-y-1">{children}</ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="list-decimal pl-5 my-1.5 space-y-1">{children}</ol>
                    ),
                    strong: ({ children }) => (
                      <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{children}</strong>
                    ),
                    code: ({ children, className }) =>
                      className?.includes('language-') ? (
                        <code
                          className="block overflow-x-auto rounded-lg px-3 py-2.5 my-2 text-[13px]"
                          style={{
                            backgroundColor: 'var(--bg-input, #111)',
                            border: '1px solid var(--border-subtle)',
                            fontFamily: 'var(--font-mono, monospace)',
                            whiteSpace: 'pre',
                          }}
                        >
                          {children}
                        </code>
                      ) : (
                        <code
                          className="px-1.5 py-0.5 rounded-md text-[13.5px]"
                          style={{
                            backgroundColor: 'var(--bg-button, #1a1a1a)',
                            fontFamily: 'var(--font-mono, monospace)',
                          }}
                        >
                          {children}
                        </code>
                      ),
                    pre: ({ children }) => <>{children}</>,
                    a: ({ href, children }) => (
                      <a href={href} target="_blank" rel="noreferrer"
                         style={{ color: 'var(--accent-blue)' }}>{children}</a>
                    ),
                  }}
                >
                  {message.content}
                </Markdown>
              )}
            </p>

            {/* Attachments */}
            {message.attachments && message.attachments.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {message.attachments.map((att) => (
                  <div
                    key={att.id}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs"
                    style={{
                      backgroundColor: isUser ? 'rgba(255,255,255,0.2)' : 'var(--bg-button)',
                      color: isUser ? '#ffffff' : 'var(--text-primary)',
                    }}
                  >
                    {att.name}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Timestamp */}
          <span
            className="text-[11px] mt-1 px-1"
            style={{
              color: isUser ? 'rgba(255,255,255,0.6)' : 'var(--text-tertiary)',
              letterSpacing: '0.02em',
            }}
          >
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>

          {/* Action Buttons (AI messages only) */}
          {!isUser && showActions && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
              className="flex items-center gap-1 mt-1"
            >
              <button
                className="p-2 rounded-md transition-colors duration-150 cursor-pointer min-w-[36px] min-h-[36px] flex items-center justify-center"
                style={{ backgroundColor: 'transparent' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
                onClick={() => navigator.clipboard.writeText(message.content)}
                aria-label="Copy message"
              >
                <Copy size={15} style={{ color: 'var(--text-tertiary)' }} />
              </button>
              <button
                className="p-2 rounded-md transition-colors duration-150 cursor-pointer min-w-[36px] min-h-[36px] flex items-center justify-center"
                style={{ backgroundColor: 'transparent' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
                aria-label="Thumbs up"
              >
                <ThumbsUp size={15} style={{ color: 'var(--text-tertiary)' }} />
              </button>
              <button
                className="p-2 rounded-md transition-colors duration-150 cursor-pointer min-w-[36px] min-h-[36px] flex items-center justify-center"
                style={{ backgroundColor: 'transparent' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-button)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
                aria-label="Thumbs down"
              >
                <ThumbsDown size={15} style={{ color: 'var(--text-tertiary)' }} />
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
