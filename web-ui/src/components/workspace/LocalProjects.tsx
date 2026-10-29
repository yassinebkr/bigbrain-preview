import { useCallback, useEffect, useRef, useState } from 'react';
import { FolderOpen, FolderPlus, ChevronLeft, FileText, Play, RefreshCw, Unplug } from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';

interface LocalProject {
  id: string; name: string; root: string; revision: number;
  rights: string[]; state: string; availability?: string; diagnostic?: string;
  transactions?: { id: string; state: string; paths: string[] }[];
}
interface Entry { name: string; path: string; type: 'file' | 'folder' }
interface Selection { ticket: string; path: string; relink?: { id: string; revision: number } }

async function api<T>(action: string, data: object = {}): Promise<T> {
  const response = await fetch(`/api/local-projects${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-BigBrain-Local': '1' },
    body: JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Erreur ${response.status}`);
  return body as T;
}

export function LocalProjects() {
  const sessionId = useAppStore((state) => state.activeSessionKey);
  const theme = useAppStore((state) => state.theme);
  const [projects, setProjects] = useState<LocalProject[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [directory, setDirectory] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [document, setDocument] = useState<{ path: string; content: string; sha256: string } | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [permissionProject, setPermissionProject] = useState<LocalProject | null>(null);
  const [rights, setRights] = useState<string[]>(['read']);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [output, setOutput] = useState('');
  const generation = useRef(0);
  const streamController = useRef<AbortController | null>(null);
  const project = projects.find((item) => item.id === selectedId);
  const button = 'inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-40';

  const refresh = useCallback(async () => {
    const version = ++generation.current;
    try {
      const result = await api<{ projects: LocalProject[]; selectedProjectId: string | null }>(
        '/projects', { sessionId });
      if (version !== generation.current) return;
      setProjects(result.projects.filter((item) => item.state !== 'detached'));
      setSelectedId(result.selectedProjectId);
    } catch (cause) { if (version === generation.current) setError(String(cause)); }
  }, [sessionId]);

  useEffect(() => {
    setDirectory(''); setEntries([]); setDocument(null); setOutput(''); setError('');
    void refresh();
    return () => { generation.current += 1; streamController.current?.abort(); };
  }, [refresh]);

  useEffect(() => {
    let active = true;
    setEntries([]); setDocument(null); setOutput('');
    if (project?.state === 'attached' && project.availability === 'available') {
      api<{ entries: Entry[] }>('/list', { projectId: project.id, revision: project.revision, path: directory })
        .then((result) => { if (active) setEntries(result.entries); })
        .catch((cause) => { if (active) setError(String(cause)); });
    }
    return () => { active = false; };
  }, [project?.id, project?.revision, project?.availability, project?.state, directory, sessionId]);

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }

  async function select(id: string | null) {
    await api('/select', { sessionId, projectId: id });
    setSelectedId(id); setDirectory(''); setDocument(null); setOutput('');
  }

  async function grant() {
    if (selection) {
      const attached = selection.relink
        ? await api<LocalProject>('/relink', { ticket: selection.ticket, projectId: selection.relink.id, revision: selection.relink.revision })
        : await api<LocalProject>('/attach', { ticket: selection.ticket, rights });
      setSelection(null);
      await select(attached.id);
    } else if (permissionProject) {
      await api('/grant', { projectId: permissionProject.id, revision: permissionProject.revision, rights });
      setPermissionProject(null);
    }
    await refresh();
  }

  async function runFile(path: string) {
    if (!project) return;
    setOutput('');
    const controller = new AbortController();
    streamController.current = controller;
    const response = await fetch('/api/local-projects/run-stream', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-BigBrain-Local': '1' },
      body: JSON.stringify({ projectId: project.id, revision: project.revision, argv: ['python', '-u', path] }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) throw new Error('Exécution indisponible');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    let terminal = false;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split('\n');
      pending = lines.pop() || '';
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === 'output') setOutput((previous) => previous + event.text);
        else if (event.type === 'result') { terminal = true; setOutput((previous) => `${previous}\nCode de sortie : ${event.exitCode}`); }
        else if (event.type === 'error') { terminal = true; throw new Error(event.error); }
      }
    }
    if (!terminal) throw new Error('La connexion s’est terminée avant le résultat');
  }

  return <section className="flex h-full min-h-0 flex-col p-4 gap-4" style={{ color: 'var(--text-primary)' }} aria-label="Projets locaux">
    <div className="flex flex-wrap items-center gap-2">
      <button className={button} disabled={busy} onClick={() => void perform(async () => {
        const chosen = await api<Selection & { cancelled?: boolean }>('/choose', {});
        if (!chosen.cancelled) { setSelection(chosen); setRights(['read']); }
      })}><FolderPlus size={16} /> Lier un dossier</button>
      <button className={button} disabled={busy} onClick={() => void refresh()} aria-label="Actualiser les projets locaux"><RefreshCw size={16} /></button>
      <span className="text-xs text-[var(--text-secondary)]">Les fichiers restent dans leur dossier d’origine.</span>
    </div>
    {error && <p role="alert" className="rounded-xl bg-amber-500/10 p-3 text-sm text-amber-300">{error}</p>}
    <div className="flex flex-1 min-h-0 gap-4 max-md:flex-col">
      <aside className="w-64 shrink-0 overflow-auto rounded-2xl bg-[var(--bg-surface)] p-2 max-md:w-full">
        {projects.length === 0 && <p className="p-3 text-sm text-[var(--text-secondary)]">Choisissez un dossier local pour consulter son projet.</p>}
        {projects.map((item) => <button key={item.id} className={`${button} w-full flex-col items-start text-left ${item.id === selectedId ? 'bg-sky-500/15 text-sky-300' : ''}`}
          onClick={() => void perform(() => select(item.id))} disabled={busy || item.state !== 'attached'}>
          <span className="flex items-center gap-2"><FolderOpen size={16} />{item.name}</span>
          <span className="text-xs opacity-70 break-all">{item.root}</span>
          <span className="text-xs opacity-70">{item.state === 'revoked' ? 'Accès révoqué' : item.availability === 'unavailable' ? 'Dossier indisponible' : item.rights.includes('write') ? 'Lecture et écriture' : 'Lecture seule'}{item.state === 'attached' && item.rights.includes('execute') ? ' · Exécution autorisée' : ''}</span>
        </button>)}
      </aside>
      <main className="flex flex-1 min-w-0 min-h-0 flex-col gap-3 overflow-auto rounded-2xl bg-[var(--bg-surface)] p-4">
        {project ? <>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-medium mr-auto">{project.name}</h2>
            <button className={button} disabled={busy} onClick={() => { setPermissionProject(project); setRights(project.rights); }}>Droits d’accès</button>
            {project.state === 'attached' && <button className={button} onClick={() => {
              void api('/revoke', { projectId: project.id, revision: project.revision })
                .then(() => refresh()).catch((cause) => setError(String(cause)));
            }}>Révoquer l’accès</button>}
            <button className={button} disabled={busy} onClick={() => void perform(async () => {
              await api('/detach', { projectId: project.id, revision: project.revision });
              await select(null); await refresh();
            })}><Unplug size={15} /> Détacher</button>
          </div>
          <p className="text-xs text-[var(--text-secondary)] break-all">{project.root}</p>
          {project.transactions?.map((transaction) => <div key={transaction.id} className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
            <p className="font-medium">Une modification interrompue nécessite une récupération.</p>
            <p className="mt-2 text-[var(--text-secondary)] break-all">{transaction.paths.join(', ')}</p>
            <button className={`${button} mt-2`} disabled={busy || !project.rights.includes('write')} onClick={() => void perform(async () => {
              const result = await api<{ state: string; conflicts: string[] }>('/recover', { projectId: project.id, revision: project.revision, transactionId: transaction.id });
              await refresh();
              if (result.conflicts.length) setError(`Vos modifications sont conservées. Résolution nécessaire : ${result.conflicts.join(', ')}`);
            })}>Restaurer les fichiers de cette opération</button>
          </div>)}
          {project.state === 'revoked' ? <div role="status"><p>L’accès à ce projet est révoqué.</p>
            <button className={button} disabled={busy} onClick={() => void perform(async () => {
              await api('/restore', { projectId: project.id, revision: project.revision }); await refresh();
            })}>Rétablir les droits précédents</button></div>
          : project.availability === 'unavailable' ? <div role="status"><p>Dossier indisponible. Reconnectez son disque, puis actualisez.</p>
            <button className={button} disabled={busy} onClick={() => void perform(async () => {
              const chosen = await api<Selection & { cancelled?: boolean }>('/choose', {});
              if (!chosen.cancelled) setSelection({ ...chosen, relink: { id: project.id, revision: project.revision } });
            })}>Retrouver le dossier déplacé</button></div> : <>
            <div className="flex items-center gap-2 text-sm">
              {directory && <button className={button} onClick={() => setDirectory(directory.split('/').slice(0, -1).join('/'))}><ChevronLeft size={15} /> Retour</button>}
              <span>{directory || 'Racine du projet'}</span>
            </div>
            <div className="flex flex-wrap gap-2">{entries.map((entry) => <button key={entry.path} className={button} disabled={busy}
              onClick={() => entry.type === 'folder' ? setDirectory(entry.path) : void perform(async () => {
                const result = await api<{ content: string; sha256: string }>('/read', { projectId: project.id, revision: project.revision, path: entry.path });
                setDocument({ path: entry.path, ...result });
              })}>{entry.type === 'folder' ? <FolderOpen size={15} /> : <FileText size={15} />}{entry.name}</button>)}</div>
            {document && <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2"><span className="text-sm mr-auto">{document.path}</span>
                {document.path.endsWith('.py') && <button className={button} disabled={busy || !project.rights.includes('execute')} onClick={() => void perform(async () => {
                  await runFile(document.path);
                })}><Play size={15} /> Exécuter</button>}
              </div>
              <pre className="overflow-auto rounded-xl bg-black/20 p-4 text-xs whitespace-pre">{document.content}</pre>
            </div>}
            {output && <pre role="log" className="whitespace-pre-wrap rounded-xl bg-black/30 p-4 text-xs">{output}</pre>}
          </>}
        </> : <p className="m-auto text-sm text-[var(--text-secondary)]">Sélectionnez un projet local.</p>}
      </main>
    </div>
    <Dialog open={Boolean(selection || permissionProject)} onOpenChange={(open) => { if (!open) { setSelection(null); setPermissionProject(null); } }}>
      <DialogContent data-theme={theme} className="rounded-2xl" style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }}>
        <DialogTitle>{selection?.relink ? 'Retrouver ce projet' : selection ? 'Lier ce dossier' : 'Droits du projet'}</DialogTitle>
        <DialogDescription className="break-all" style={{ color: 'var(--text-secondary)' }}>{selection?.path || permissionProject?.root}</DialogDescription>
        <p className="text-sm">{selection?.relink ? 'Le dossier doit conserver l’identité du projet d’origine. Les droits précédents seront rétablis.' : 'La lecture autorise la consultation locale. Chaque action supplémentaire possède son propre droit.'}</p>
        {!selection?.relink && [['write', 'Modifier les sources'], ['execute', 'Exécuter dans une copie isolée'], ['transmit', 'Transmettre les sources au modèle']].map(([right, label]) => <label key={right} className="flex items-center gap-3 text-sm">
          <input type="checkbox" checked={rights.includes(right)} onChange={(event) => setRights((previous) => event.target.checked ? [...previous, right] : previous.filter((item) => item !== right))} />{label}
        </label>)}
        {!selection?.relink && rights.includes('transmit') && <p className="text-xs text-[var(--text-secondary)]">Le fournisseur destinataire et les fichiers autorisés seront confirmés dans le contrat du travail.</p>}
        <button className={`${button} justify-center`} style={{ backgroundColor: 'var(--accent-blue)', color: '#fff' }} disabled={busy} onClick={() => void perform(grant)}>Confirmer les droits</button>
      </DialogContent>
    </Dialog>
  </section>;
}
