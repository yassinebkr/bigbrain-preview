/** Specialist choices share the same assignment API as the front model. */
import { useAppStore } from '@/store/appStore';
import { useModelSelection } from '@/lib/useModelSelection';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

const specialistRoles = [
  ['planner', 'Planification'], ['code', 'Développement Python'],
  ['web', 'Applications web'], ['research', 'Recherche web'],
  ['subagent', 'CAO, voix et revue'],
] as const;

export function ModelSettings() {
  const { roles, models, error, pending, assign } = useModelSelection(true);
  const theme = useAppStore(state => state.theme);
  return <div className="space-y-5" aria-label="Modèles des spécialistes">
    {specialistRoles.map(([role, label]) => {
      const current = roles[role];
      const mismatch = current?.runtime?.some(holder => holder.registry_key !== current.key);
      return <div key={role} className="space-y-2">
        <label id={`model-${role}`} className="text-[12px] font-medium" style={{color:'var(--text-primary)'}}>{label}</label>
        <Select value={current?.key || ''} onValueChange={key => void assign(role, key)} disabled={!!pending || !current}>
          <SelectTrigger aria-labelledby={`model-${role}`} className="w-full rounded-xl" style={{background:'var(--bg-button)', color:'var(--text-primary)', borderColor:'var(--border-subtle)'}}>
            <SelectValue placeholder="Chargement…">{current?.display_name}</SelectValue>
          </SelectTrigger>
          <SelectContent data-theme={theme} position="popper" className="z-[80] rounded-xl" style={{background:'var(--bg-surface)', color:'var(--text-primary)', borderColor:'var(--border-subtle)'}}>
            {models.filter(model => model.available || model.key === current?.key).map(model =>
              <SelectItem key={model.key} value={model.key} disabled={!model.available}>{model.display_name}</SelectItem>)}
          </SelectContent>
        </Select>
        {mismatch && <p role="alert" className="text-[11px]" style={{color:'var(--warning)'}}>Le fournisseur actif doit être vérifié.</p>}
      </div>;
    })}
    {error && <p role="alert" className="text-[12px]" style={{color:'var(--warning)'}}>{error}</p>}
  </div>;
}
