import { motion } from 'framer-motion';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';
import { useState } from 'react';
import type { Message } from '@/types';
import { AttachmentPreview } from './AttachmentPreview';

interface MessageBubbleProps {
  message: Message;
  index: number;
}

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [showActions, setShowActions] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard may be unavailable */ }
  };


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
      <div className={`chat-message-row flex ${isUser ? 'flex-row-reverse' : 'flex-row'} items-start gap-2 w-full max-w-[92%] sm:max-w-[85%] md:max-w-[82%] lg:max-w-[78%] xl:max-w-[75%]`}>
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

        <div className={`relative flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
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
                    <AttachmentPreview attachment={att} />
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
          {!isUser && (
            <motion.div
              initial={false}
              animate={{ opacity: showActions || copied ? 1 : 0, y: showActions || copied ? 0 : -2 }}
              transition={{ duration: 0.2 }}
              className="absolute left-2 top-full z-10 flex items-center mt-1"
              style={{ pointerEvents: showActions || copied ? 'auto' : 'none' }}
            >
              <button
                className="h-7 px-2 rounded-md transition-colors duration-150 cursor-pointer flex items-center gap-1.5"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  color: copied ? 'var(--success, #34c759)' : 'var(--text-tertiary)',
                }}
                onClick={copyMessage}
                aria-label="Copy message"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                <span className="text-[11px]">{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
