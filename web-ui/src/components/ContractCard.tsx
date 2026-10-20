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
import { useWorkspaceStore } from '@/store/workspaceStore';

export function ContractCriteria({ contracts }: { contracts: string[] }) {
  return <ol className="contract-criteria">{contracts.filter((item) => !item.startsWith('[Stack]')).map((item, i) =>
    <li key={i}><span className="contract-number">{i + 1}</span>{item.length > 190
      ? <details className="min-w-0 flex-1"><summary><span>{item.slice(0, 180)}…</span><span className="work-link block mt-2 text-[11px]">Lire le critère intégral</span></summary><p className="mt-3 work-muted">{item}</p></details>
      : <p>{item}</p>}</li>)}</ol>;
}

export function StackSummary({ value }: { value: string }) {
  const fields = value.replace(/^\[Stack\]\s*/, '').split(' · ');
  const read = (prefix: string) => fields.find((field) => field.startsWith(prefix))?.slice(prefix.length).trim() || '';
  const deliverable = read('livrable ');
  const interaction = read('interaction ');
  const entryPoint = read('point d’entrée ');
  const technologies = read('technologies ');
  const validation = read('validation ');
  const deliverableLabel = deliverable === 'web_app' ? 'Application web' : deliverable.replaceAll('_', ' ');
  const interactionLabel = interaction === 'browser' ? 'Navigateur' : interaction;

  return (
    <div className="rounded-xl px-3.5 py-3 my-3" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>Plan technique</span>
        {deliverableLabel && <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ color: 'var(--accent-blue-light)', backgroundColor: 'rgba(0, 113, 227, 0.12)' }}>{deliverableLabel}</span>}
        {interactionLabel && <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>{interactionLabel}</span>}
      </div>
      {entryPoint && <div className="flex items-baseline gap-2 mb-3 text-[12px]"><span className="shrink-0" style={{ color: 'var(--text-tertiary)' }}>Point d’entrée</span><code className="rounded px-1.5 py-0.5" style={{ color: 'var(--text-primary)', backgroundColor: 'var(--bg-primary)' }}>{entryPoint}</code></div>}
      {technologies && <details className="mb-3"><summary className="work-link text-[12px]">Choix techniques</summary><p className="mt-2 text-[12px] leading-relaxed work-muted">{technologies}</p></details>}
      {validation && <details><summary className="work-link text-[12px]">Méthode de vérification</summary><p className="mt-2 text-[12px] leading-relaxed work-muted">{validation}</p></details>}
    </div>
  );
}

export function ContractCard({ compact = false }: { compact?: boolean }) {
  const proposal = useAppStore((s) => s.contractProposal);
  const sending = useAppStore((s) => s.contractSending);
  const error = useAppStore((s) => s.contractError);
  const sendContractDecision = useAppStore((s) => s.sendContractDecision);
  const sessionId = useAppStore((s) => s.activeSessionKey);
  const selectedId = useWorkspaceStore((s) => s.sessions[sessionId]?.selectedId);
  if (proposal && compact && selectedId?.startsWith(`${encodeURIComponent(sessionId)}/${encodeURIComponent(proposal.planId)}/`)) {
    return <div className="self-start max-w-sm rounded-2xl px-4 py-3 text-[13px] work-muted" style={{ border: '1px solid var(--border-subtle)' }} role="status">Contrat prêt à examiner dans l’Atelier → <span className="block mt-1 text-[11px]">Le travail attend ton accord.</span></div>;
  }

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
                Voici le contrat proposé
              </p>

              {proposal.target && (
                <div className="flex flex-wrap items-center gap-2 my-3 text-[12px]">
                  <span style={{ color: 'var(--text-tertiary)' }}>
                    {proposal.target.mode === 'new' ? 'Nouveau projet' : 'Projet à modifier / exécuter'}
                  </span>
                  <code className="rounded px-2 py-1 break-all" style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)' }}>
                    {proposal.target.path}
                  </code>
                </div>
              )}
              {proposal.contracts.some((contract) => contract.startsWith('[Stack]')) && (
                <StackSummary value={proposal.contracts.find((contract) => contract.startsWith('[Stack]'))!} />
              )}
              <ContractCriteria contracts={proposal.contracts} />

              <p className="text-[12px] mt-1 mb-2 m-0" style={{ color: 'var(--text-tertiary)' }}>
                Le travail attend ton accord.
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
              {error && <p role="alert" className="text-[12px] mt-2" style={{ color: 'var(--warning, #ff9500)' }}>{error}</p>}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
