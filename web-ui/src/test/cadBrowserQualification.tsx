/** Mount the real Atelier against an isolated copy of a retained document. */
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ContextWorkspace } from '@/components/ContextWorkspace';
import { useAppStore, type RunState } from '@/store/appStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { surfaceId } from '@/lib/morphable';
import '@/index.css';

const run = await (await fetch('/cad-qualification-fixture')).json() as RunState;
useAppStore.setState({ activeSessionKey: run.sessionId, runsById:{[run.id]:run}, completedRuns:[], theme:'dark' });
useWorkspaceStore.getState().update(run.sessionId, {mode:'workspace', selectedId:surfaceId(run,'cad'), width:850});
function Fixture() {
  const [other, setOther] = useState(false);
  return <div className="h-screen flex flex-col" style={{background:'var(--bg-primary)',color:'var(--text-primary)'}}>
    <nav className="p-3 flex gap-4 border-b" style={{borderColor:'var(--border-subtle)'}}>
      <span className="mr-auto">Atelier · qualification sur copie</span>
      <button onClick={() => setOther(value => !value)}>{other ? 'Retour à la pièce' : 'Autre projet'}</button>
    </nav>
    {other ? <p className="p-8">Autre projet · éditeur conservé en mémoire</p> :
      <ContextWorkspace>{() => <div className="p-6"><h1>Conversation</h1><p className="text-sm mt-4">Qualification de l’éditeur intégré, sur une copie du document conservé.</p></div>}</ContextWorkspace>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
