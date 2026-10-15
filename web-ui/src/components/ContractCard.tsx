// ContractCard — Phase B pre-implementation approval (pattern
// shopifast-local). Before the agent writes code, it proposes checkable
// contracts; the run is PAUSED until the user approves or rejects them.
// The verdict is traced on the evidence DesignSpec (revision stamped by
// the orchestrator).

import { motion, AnimatePresence } from 'framer-motion';
import { ScrollText, Check, X, Loader2 } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

export function ContractCard() {
  const proposal = useAppStore((s) => s.contractProposal);
  const sending = useAppStore((s) => s.contractSending);
  const sendContractDecision = useAppStore((s) => s.sendContractDecision);

  return (
    <AnimatePresence>
      {proposal && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.25 }}
          className="w-full max-w-[720px] mx-auto rounded-xl p-4"
          style={{
            backgroundColor: 'var(--bg-secondary, #1a1a2e)',
            border: '1px solid var(--border-subtle, #2a2a3e)',
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <ScrollText size={15} className="flex-shrink-0" style={{ color: 'var(--accent, #7c6ff0)' }} />
            <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary, #fff)' }}>
              Proposed contracts
            </span>
            <span
              className="text-[11px] px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: 'var(--bg-tertiary, #23233a)',
                color: 'var(--text-tertiary, #888)',
              }}
            >
                execution paused
            </span>
          </div>

          {proposal.request && (
            <p className="text-[12px] mb-2" style={{ color: 'var(--text-tertiary, #999)' }}>
              “{proposal.request.slice(0, 160)}{proposal.request.length > 160 ? '…' : ''}”
            </p>
          )}

          <ul className="flex flex-col gap-1.5 mb-3">
            {proposal.contracts.map((contract, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px]" style={{ color: 'var(--text-secondary, #ccc)' }}>
                <Check size={13} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--success, #34c759)' }} />
                <span>{contract}</span>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-2">
            <button
              onClick={() => sendContractDecision(true)}
              disabled={sending}
              className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-1.5 rounded-lg transition-opacity"
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
              className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-1.5 rounded-lg transition-opacity"
              style={{
                border: '1px solid var(--border-subtle, #2a2a3e)',
                color: 'var(--text-secondary, #ccc)',
                opacity: sending ? 0.6 : 1,
              }}
            >
              <X size={12} />
              Reject
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
