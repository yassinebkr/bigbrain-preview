import { useRef, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import { MessageBubble } from './MessageBubble';
import { StreamingMessage } from './StreamingMessage';
import { TypingIndicator } from './TypingIndicator';
import { ChatInput } from './ChatInput';
import { GenUICanvas } from './GenUICanvas';
import { RunPanel } from './RunPanel';
import { ContractCard } from './ContractCard';
import { NudgeBar } from './NudgeBar';
import { RunTimelineCard } from './RunTimelineCard';
import { ArrowDown } from 'lucide-react';
import { ContextWorkspace } from './ContextWorkspace';

export function ChatView() {
  return <ContextWorkspace>{(ownsActivity) => <Conversation contextOwnsActivity={ownsActivity} />}</ContextWorkspace>;
}

function Conversation({ contextOwnsActivity }: { contextOwnsActivity: boolean }) {
  const { messages, isStreaming, historyError } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [followLatest, setFollowLatest] = useState(true);

  const streamingText = useAppStore((s) => s.streamingText);
  const completedRuns = useAppStore((s) => s.completedRuns);
  const activeSessionKey = useAppStore((s) => s.activeSessionKey);
  const timeline = [
    ...messages.map((message) => ({
      kind: 'message' as const, ts: message.timestamp, message,
    })),
    ...completedRuns
      .filter((run) => !!activeSessionKey && run.sessionId === activeSessionKey && run.finishedAt)
      .map((run) => ({
        kind: 'run' as const, ts: run.finishedAt!, run,
      })),
  ].sort((a, b) => a.ts - b.ts);

  // Auto-scroll: instant while the streamed text grows (following the
  // cursor without flicker), smooth for whole new messages.
  useEffect(() => {
    if (!followLatest) return;
    const hasStreamText = !!streamingText.trim();
    bottomRef.current?.scrollIntoView({ behavior: hasStreamText ? 'auto' : 'smooth' });
  }, [messages.length, completedRuns.length, isStreaming, streamingText, followLatest]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setFollowLatest(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const jumpToLatest = () => {
    setFollowLatest(true);
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-2 sm:px-3 md:px-6 lg:px-10 py-3 sm:py-4 md:py-6 flex flex-col gap-3 sm:gap-4 md:gap-5"
      >
        <div className="w-full max-w-[1200px] mx-auto flex flex-col gap-3 sm:gap-4 md:gap-5">
        {historyError && <div role="alert" className="rounded-lg p-3 text-[12px]"
          style={{ border: '1px solid var(--warning)', color: 'var(--warning)' }}>{historyError}</div>}
        {timeline.map((item, index) => (
          item.kind === 'message'
            ? <MessageBubble key={item.message.id} message={item.message} index={index} />
            : <RunTimelineCard key={`run-${item.run.id}`} run={item.run} />
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

        {/* Contract approval card — the run is paused until the user
            decides. Shown in the message flow: it answers the last ask. */}
        <ContractCard />

        </div>

        {/* Bottom anchor for auto-scroll */}
        <div ref={bottomRef} />

        {!followLatest && (
          <button
            onClick={jumpToLatest}
            className="sticky bottom-3 ml-auto mr-2 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] shadow-lg cursor-pointer"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}
            aria-label="Jump to latest message"
          >
            <ArrowDown size={12} /> Latest
          </button>
        )}
      </motion.div>

      {/* Live agent activity — what is happening, which brain works */}
      {!contextOwnsActivity && <RunPanel />}

      {/* GenUI Canvas - between messages and input */}
      <GenUICanvas />

      {/* Chat Input - Fixed at bottom. Kept at the original compact width
          (720px) even on wide screens — the messages column widened, but
          the input reads better narrow. */}
      <div
        className="sticky bottom-0 pb-2 sm:pb-3 md:pb-4 pt-2 px-1 sm:px-0"
        style={{
          backgroundColor: 'var(--bg-primary)',
        }}
      >
        <div className="max-w-[720px] mx-auto w-full">
          <NudgeBar />
          <ChatInput />
        </div>
      </div>
    </div>
  );
}
