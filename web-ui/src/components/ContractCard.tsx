// ContractCard — Phase B pre-implementation approval (pattern
// shopifast-local). Before the agent writes code, it proposes checkable
// contracts; the run is PAUSED until the user approves or rejects them.
// The verdict is traced on the evidence DesignSpec (revision stamped by
// the orchestrator).
//
// Rendered INSIDE the message flow with the assistant bubble style (same
// shape/border as MessageBubble): it reads as the agent asking something,
// not as a floating system popup.

import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, Loader2 } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

function StackSummary({ value }: { value: string }) {
  const fields = value.replace(/^\[Stack\]\s*/, '').split(' · ');
  return (
    <div className="rounded-xl px-3 py-2.5 mb-3" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
      <div className="text-[10px] uppercase tracking-[0.12em] mb-2" style={{ color: 'var(--text-tertiary)' }}>Architecture retenue</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
        {fields.map((field, i) => {
          const split = field.indexOf(' ');
          const label = split > 0 ? field.slice(0, split) : 'détail';
          const text = split > 0 ? field.slice(split + 1) : field;
          return <div key={i} className="text-[12px] leading-snug"><span style={{ color: 'var(--text-tertiary)' }}>{label} </span><span style={{ color: 'var(--text-primary)' }}>{text}</span></div>;
        })}
      </div>
    </div>
  );
}

export function ContractCard() {
  const proposal = useAppStore((s) => s.contractProposal);
  const sending = useAppStore((s) => s.contractSending);
  const sendContractDecision = useAppStore((s) => s.sendContractDecision);

  return (
    <AnimatePresence>
      {proposal && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, ease: [0, 0, 0.2, 1] }}
          className="flex justify-start w-full"
        >
          <div className="flex flex-row items-start gap-2 w-full max-w-[92%] sm:max-w-[85%] md:max-w-[82%] lg:max-w-[78%] xl:max-w-[75%]">
            {/* Avatar — same as assistant messages */}
            <div
              className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center mt-1"
              style={{ backgroundColor: '#0071e3' }}
            >
              <img src="/robot-icon.png" alt="AI" className="w-4 h-4 object-contain" />
            </div>

            {/* Bubble — assistant styling: transparent, subtle border */}
            <div
              className="px-4 py-3 flex flex-col"
              style={{
                backgroundColor: 'transparent',
                border: '1px solid var(--border-subtle)',
                borderRadius: '18px 18px 18px 4px',
                maxWidth: '100%',
              }}
            >
              <p className="text-[15px] leading-relaxed m-0" style={{ color: 'var(--text-primary)' }}>
                Before I write code — approve these contracts:
              </p>

              {proposal.contracts.some((contract) => contract.startsWith('[Stack]')) && (
                <StackSummary value={proposal.contracts.find((contract) => contract.startsWith('[Stack]'))!} />
              )}
              <ul className="list-disc pl-5 my-1.5 space-y-1">
                {proposal.contracts.filter((contract) => !contract.startsWith('[Stack]')).map((contract, i) => (
                  <li
                    key={i}
                    className="text-[13.5px] leading-relaxed"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {contract}
                  </li>
                ))}
              </ul>

              <p className="text-[12px] mt-1 mb-2 m-0" style={{ color: 'var(--text-tertiary)' }}>
                Execution is paused until you decide.
              </p>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => sendContractDecision(true)}
                  disabled={sending}
                  className="flex items-center gap-1.5 text-[12.5px] font-medium px-3 py-1.5 rounded-lg transition-opacity"
                  style={{
                    backgroundColor: 'var(--success, #34c759)',
                    color: '#0a0a14',
                    opacity: sending ? 0.6 : 1,
                  }}
                >
                  {sending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                  Approve &amp; run
                </button>
                <button
                  onClick={() => sendContractDecision(false)}
                  disabled={sending}
                  className="flex items-center gap-1.5 text-[12.5px] font-medium px-3 py-1.5 rounded-lg transition-opacity"
                  style={{
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    opacity: sending ? 0.6 : 1,
                  }}
                >
                  <X size={12} />
                  Reject
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
