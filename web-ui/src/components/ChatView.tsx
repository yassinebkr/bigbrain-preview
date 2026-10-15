import { useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { MessageBubble } from './MessageBubble';
import { StreamingMessage } from './StreamingMessage';
import { TypingIndicator } from './TypingIndicator';
import { ChatInput } from './ChatInput';
import { GenUICanvas } from './GenUICanvas';

export function ChatView() {
  const { messages, isStreaming } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, isStreaming]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-2 sm:px-3 md:px-4 py-3 sm:py-4 md:py-6 flex flex-col gap-3 sm:gap-4 md:gap-6"
      >
        {messages.map((message, index) => (
          <MessageBubble key={message.id} message={message} index={index} />
        ))}

        {/* Streaming message */}
        <AnimatePresence>
          {isStreaming && <StreamingMessage />}
        </AnimatePresence>

        {/* Typing indicator shown when streaming but no text yet */}
        <AnimatePresence>
          {isStreaming && (
            <TypingIndicator />
          )}
        </AnimatePresence>

        {/* Bottom anchor for auto-scroll */}
        <div ref={bottomRef} />
      </motion.div>

      {/* GenUI Canvas - between messages and input */}
      <GenUICanvas />

      {/* Chat Input - Fixed at bottom */}
      <div
        className="sticky bottom-0 pb-2 sm:pb-3 md:pb-4 pt-2 px-1 sm:px-0"
        style={{
          backgroundColor: 'var(--bg-primary)',
        }}
      >
        <ChatInput />
      </div>
    </div>
  );
}
