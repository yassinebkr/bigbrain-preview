import { useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Paperclip, Mic, Send, Square } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { ActionPill } from './ActionPill';
import { AttachmentChip } from './AttachmentChip';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

const actionPills = [
  { icon: Paperclip, label: 'Attach File' },
];

interface ChatInputProps {
  onSend?: () => void;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const {
    inputText,
    setInputText,
    attachments,
    addAttachment,
    removeAttachment,
    sendMessage,
    isRecording,
    setRecording,
    isStreaming,
    stopGeneration,
    activeRun,
    activeSessionKey,
  } = useAppStore();

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  const hasContent = inputText.trim().length > 0 || attachments.length > 0;

  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 48), 160);
    textarea.style.height = `${newHeight}px`;
  }, []);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
    requestAnimationFrame(adjustTextareaHeight);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (hasContent && !isStreaming) {
        handleSend();
      }
    }
  };

  const handleSend = () => {
    if (!hasContent) return;
    sendMessage();
    if (textareaRef.current) {
      textareaRef.current.style.height = '48px';
    }
    onSend?.();
  };

  const handleAttachFile = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach((file) => {
      addAttachment({
        id: `file-${Date.now()}-${file.name}`,
        name: file.name,
        type: file.type,
        size: file.size,
        file,
      });
    });
    e.target.value = '';
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    Array.from(items).forEach((item) => {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) {
          addAttachment({
            id: `paste-${Date.now()}-${file.name}`,
            name: file.name,
            type: file.type,
            size: file.size,
            file,
          });
        }
      }
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 1.1, ease: easeOut }}
      className="w-full rounded-2xl p-2.5 sm:p-4 pb-2.5 sm:pb-3 flex flex-col gap-2"
      style={{
        backgroundColor: 'var(--bg-input)',
        border: isFocused ? '1px solid rgba(0,113,227,0.5)' : '1px solid var(--border-subtle)',
        boxShadow: isFocused ? 'var(--shadow-input-focus)' : 'none',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
    >
      {/* Attachment Chips */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-1">
          {attachments.map((att) => (
            <AttachmentChip
              key={att.id}
              attachment={att}
              onRemove={removeAttachment}
            />
          ))}
        </div>
      )}

      {/* Input Row */}
      <div className="flex items-start gap-2">
        <img
          src="/robot-icon.png"
          alt=""
          className="w-5 h-5 mt-1 object-contain flex-shrink-0"
          style={{ opacity: 0.5 }}
        />
        <textarea
          ref={textareaRef}
          value={inputText}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onPaste={handlePaste}
          placeholder="Initiate a query or send a command to the AI..."
          className="flex-1 bg-transparent border-none outline-none resize-none placeholder:opacity-100 min-h-[48px] max-h-[160px]"
          style={{
            fontSize: '15px',
            fontWeight: 400,
            lineHeight: 1.5,
            color: 'var(--text-primary)',
          }}
        />
      </div>

      {/* Action Row */}
      <div className="flex items-center justify-between mt-1 gap-2">
        {/* Left - Action Pills - scrollable on mobile */}
        <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar flex-1 min-w-0">
          {actionPills.map((pill, index) => (
            <motion.div
              key={pill.label}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 1.2 + index * 0.05 }}
              className="flex-shrink-0"
            >
              <ActionPill
                icon={pill.icon}
                label={pill.label}
                onClick={pill.label === 'Attach File' ? handleAttachFile : undefined}
              />
            </motion.div>
          ))}
        </div>

        {/* Right - Mic + Send */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
          <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={() => setRecording(!isRecording)}
            className="flex items-center justify-center w-10 h-10 sm:w-9 sm:h-9 rounded-full transition-all duration-300 cursor-pointer"
            style={{
              backgroundColor: isRecording ? 'var(--accent-blue)' : 'var(--bg-button)',
              border: isRecording ? 'none' : '1px solid transparent',
            }}
            onMouseEnter={(e) => {
              if (!isRecording) {
                e.currentTarget.style.borderColor = 'var(--border-subtle)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isRecording) {
                e.currentTarget.style.borderColor = 'transparent';
              }
            }}
            aria-label="Voice input"
          >
            <Mic
              size={16}
              className="sm:w-4 sm:h-4"
              style={{ color: isRecording ? '#ffffff' : 'var(--text-tertiary)' }}
            />
          </motion.button>

          {(isStreaming || (activeRun?.status === 'running' && activeRun.sessionId === activeSessionKey)) ? (
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={stopGeneration}
              className="flex items-center justify-center w-10 h-10 sm:w-9 sm:h-9 rounded-full transition-all duration-200 cursor-pointer"
              style={{ backgroundColor: 'var(--accent-blue)' }}
              aria-label="Stop generation"
              title="Stop"
            >
              <Square size={13} className="fill-current" style={{ color: '#ffffff' }} />
            </motion.button>
          ) : (
            <motion.button
              whileTap={{ scale: 0.9 }}
              onClick={handleSend}
              disabled={!hasContent}
              className="flex items-center justify-center w-10 h-10 sm:w-9 sm:h-9 rounded-full transition-all duration-200 cursor-pointer"
              style={{
                backgroundColor: hasContent ? 'var(--accent-blue)' : 'var(--bg-button)',
              }}
              aria-label="Send message"
            >
              <Send
                size={16}
                className="sm:w-4 sm:h-4"
                style={{ color: hasContent ? '#ffffff' : 'var(--text-tertiary)' }}
              />
            </motion.button>
          )}
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />
    </motion.div>
  );
}
