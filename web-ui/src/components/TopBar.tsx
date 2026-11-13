/** Primary navigation and front-model selection for the current conversation. */
import { useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, Check, ChevronDown, SlidersHorizontal, Sparkles } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { useModelSelection } from '@/lib/useModelSelection';
import { ConnectionStatus } from './ConnectionStatus';

export function TopBar({ children }: { children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { connectionStatus, sidebarPanel, setSidebarPanel, setSettingsSection, goBack, view, navigationHistory } = useAppStore();
  const { roles, models, error, pending, modelsLoading, assign } = useModelSelection(open, sidebarPanel);
  const front = roles.front;
  const mismatch = front?.runtime?.some(holder => holder.registry_key !== front.key);

  const openModelSettings = () => {
    setOpen(false);
    setSidebarPanel('settings');
    setSettingsSection('models');
  };

  return <motion.header initial={{opacity:0, y:-10}} animate={{opacity:1, y:0}}
    className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between px-2 sm:px-3 md:px-4">
    <div className="flex items-center gap-2 min-w-0">
      {children}
      <button aria-label="Retour" title="Retour" onClick={goBack}
        disabled={view === 'welcome' && !sidebarPanel && !navigationHistory.length}
        className="grid size-8 shrink-0 place-items-center rounded-full transition-colors hover:bg-white/10 disabled:opacity-30"
        style={{color:'var(--text-primary)'}}><ArrowLeft size={17} /></button>
      <div className="hidden sm:block"><ConnectionStatus status={connectionStatus} /></div>
      <div className="relative min-w-0">
        <button aria-label={`Modèle du Front Brain, ${front?.display_name || 'chargement'}`} aria-expanded={open}
          onClick={() => setOpen(value => !value)}
          className="flex h-8 max-w-[240px] items-center gap-2 rounded-full border px-2.5 text-[12px]"
          style={{background:'var(--bg-surface)', color:'var(--text-primary)', borderColor:'var(--border-subtle)'}}>
          <img src="/robot-icon.png" alt="" className="size-4" />
          <span className="truncate">{front?.display_name || 'BigBrain'}</span>
          <ChevronDown size={12} className="shrink-0" />
        </button>
        <AnimatePresence>{open && <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <motion.div initial={{opacity:0, y:-5}} animate={{opacity:1, y:0}} exit={{opacity:0, y:-5}}
            className="absolute left-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-2xl border shadow-xl"
            style={{background:'var(--bg-surface)', color:'var(--text-primary)', borderColor:'var(--border-subtle)'}}>
            <p className="px-4 pt-3 pb-2 text-[11px]" style={{color:'var(--text-tertiary)'}}>Modèle du Front Brain</p>
            <div className="max-h-64 overflow-y-auto px-1.5 pb-1.5">
              {models.filter(model => model.available || model.key === front?.key).map(model =>
                <button key={model.key} disabled={!!pending || !model.available}
                  onClick={async () => { if (await assign('front', model.key)) setOpen(false); }}
                  className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-[12px] hover:bg-white/10 disabled:opacity-40"
                  aria-pressed={model.key === front?.key}>
                  <span className="flex-1">{model.display_name}</span>{model.key === front?.key && <Check size={14} />}
                </button>)}
              {!models.length && <p className="px-2.5 py-2 text-[12px]" style={{color:'var(--text-secondary)'}}>{modelsLoading ? 'Chargement des modèles…' : 'Aucun modèle disponible.'}</p>}
            </div>
            {(error || mismatch) && <p role="alert" className="px-4 pb-3 text-[11px]" style={{color:'var(--warning)'}}>{error || 'Le fournisseur actif doit être vérifié.'}</p>}
            <button onClick={openModelSettings} className="flex w-full items-center gap-2 border-t px-4 py-3 text-left text-[12px] hover:bg-white/5"
              style={{borderColor:'var(--border-subtle)', color:'var(--text-secondary)'}}>
              <SlidersHorizontal size={15} />Modèles des spécialistes
            </button>
          </motion.div>
        </>}</AnimatePresence>
      </div>
    </div>
    <span className="pointer-events-none absolute left-1/2 hidden -translate-x-1/2 text-sm font-semibold lg:block" style={{color:'var(--text-primary)'}}>Aplot AI</span>
    <button className="flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-[12px]"
      style={{background:'var(--bg-surface)', color:'var(--text-primary)', borderColor:'var(--border-subtle)'}}>
      <span className="hidden sm:inline">Upgrade</span><Sparkles size={14} />
    </button>
  </motion.header>;
}
