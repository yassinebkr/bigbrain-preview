import { useRef, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { MessageBubble } from './MessageBubble';
import { StreamingMessage } from './StreamingMessage';
import { TypingIndicator } from './TypingIndicator';
import { ChatInput } from './ChatInput';
import { GenUICanvas } from './GenUICanvas';
import { RunPanel } from './RunPanel';

export function ChatView() {
  const { messages, isStreaming } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const streamingText = useAppStore((s) => s.streamingText);

  // Auto-scroll: instant while the streamed text grows (following the
  // cursor without flicker), smooth for whole new messages.
  useEffect(() => {
    const hasStreamText = !!streamingText.trim();
    bottomRef.current?.scrollIntoView({ behavior: hasStreamText ? 'auto' : 'smooth' });
  }, [messages.length, isStreaming, streamingText]);

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-2 sm:px-3 md:px-6 lg:px-10 py-3 sm:py-4 md:py-6 flex flex-col gap-3 sm:gap-4 md:gap-5"
      >
        <div className="w-full max-w-[1200px] mx-auto flex flex-col gap-3 sm:gap-4 md:gap-5">
        {messages.map((message, index) => (
          <MessageBubble key={message.id} message={message} index={index} />
        ))}

        {/* Streaming message — only once text exists (the typing
            indicator covers the empty phase; showing BOTH stacked and
            made the view jump at the first delta). */}
        <AnimatePresence>
          {isStreaming && !!streamingText.trim() && <StreamingMessage />}
        </AnimatePresence>

        {/* Typing indicator: streaming with no text yet */}
        <AnimatePresence>
          {isStreaming && !streamingText.trim() && <TypingIndicator />}
        </AnimatePresence>

        </div>

        {/* Bottom anchor for auto-scroll */}
        <div ref={bottomRef} />
      </motion.div>

      {/* Live agent activity — what is happening, which brain works */}
      <RunPanel />

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
