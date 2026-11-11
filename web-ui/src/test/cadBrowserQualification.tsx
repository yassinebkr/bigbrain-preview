/** Mount the real Atelier against an isolated copy of a retained document. */
import { useRef, useState } from 'react';
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
  const [probe, setProbe] = useState('');
  const [testing, setTesting] = useState(false);
  const [clicks, setClicks] = useState(0);
  const responses = useRef(0);
  async function qualifyWorker() {
    if (testing) return;
    setTesting(true);
    const started = performance.now();
    let previous = started, maximumGap = 0, frames = 0, animation = 0;
    const tick = (now: number) => {
      maximumGap = Math.max(maximumGap, now - previous); previous = now; frames++;
      animation = requestAnimationFrame(tick);
    };
    animation = requestAnimationFrame(tick);
    const result: Record<string, unknown> = {};
    const call = async (action: string, data: Record<string, unknown> = {}) => {
      const response = await fetch(`/api/cad/browser/${action}`, {method:'POST', headers:{'Content-Type':'application/json','X-BigBrain-CAD':'1'},
        body: JSON.stringify({...data, documentId:run.cad?.document_id, sessionId:run.sessionId})});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
      return body.value;
    };
    type Inspection = { params: {name: string; value: number}[]; timeline: {error?: string}[] };
    type CanvasRuntime = { adapter?: string; draw?: {triangles: number} };
    const frame = document.querySelector<HTMLIFrameElement>('[data-cad-editor] iframe');
    const api = (frame?.contentWindow as (Window & {solidcraft?: {
      inspect(options: {measure: boolean}): Promise<Inspection>;
      request(method: string, params: object): Promise<CanvasRuntime>;
    }}) | null)?.solidcraft;
    const inspect = async () => {
      const data = await api!.inspect({measure:false});
      const value = data.params.find(item => item.name === 'flange_thickness')?.value;
      if (!Number.isFinite(value) || data.timeline.some(feature => feature.error)) throw new Error('Invalid cached drawing 42');
      return value!;
    };
    try {
      const capability = await call('capability');
      if (!capability.worker || !frame || !api) throw new Error('Ouvrir le visualiseur Worker avant le contrôle');
      const initial = await inspect();
      let state = await call('state');
      if (state.owner === 'user') state = await call('resume', {revision:state.revision, hash:state.hash});
      const operationId = crypto.randomUUID();
      await call('enqueue', {operationId, revision:state.revision, hash:state.hash, command:'parameters.change',
        params:{name:'flange_thickness', expression:`${initial + 1} mm`}});
      setProbe('Reconstruction dans le Worker…');
      const deadline = performance.now() + 120000;
      let receipt;
      while (performance.now() < deadline) {
        receipt = await call('result', {operationId});
        if (['failed', 'cancelled'].includes(receipt.status)) throw new Error(JSON.stringify(receipt));
        if (receipt.status === 'accepted' && await inspect() === initial + 1) break;
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      if (receipt?.status !== 'accepted' || await inspect() !== initial + 1) throw new Error('Checkpoint accepté non affiché');
      if (document.querySelector('[data-cad-editor] iframe') !== frame) throw new Error('Le visualiseur a été remplacé');
      const rendered = await api.request('ui.inspect', {});
      if (!(rendered.draw?.triangles && rendered.draw.triangles > 0)) throw new Error('Le rendu du checkpoint manque');
      Object.assign(result, {status:'passed', initial, displayed:initial + 1, receipt, rendered,
        durationMs:performance.now() - started});
      if (maximumGap >= 200) throw new Error('Interface bloquée pendant la reconstruction');
      setProbe(`Checkpoint ${receipt.revision} affiché · ${Math.round(maximumGap)} ms entre images au maximum`);
    } catch (error) { Object.assign(result, {status:'failed', error:String(error)}); setProbe(String(error)); }
    finally {
      cancelAnimationFrame(animation);
      Object.assign(result, {maximumGap, frames, responseClicks:responses.current});
      await fetch('/cad-qualification-fixture/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(result)});
      setTesting(false);
    }
  }
  return <div className="h-screen flex flex-col" style={{background:'var(--bg-primary)',color:'var(--text-primary)'}}>
    <nav className="p-3 flex gap-4 border-b" style={{borderColor:'var(--border-subtle)'}}>
      <span className="mr-auto">Atelier · qualification sur copie</span>
      {new URLSearchParams(location.search).has('worker') && <>
        <span role="status">{probe}</span>
        <button disabled={testing} onClick={() => void qualifyWorker()}>Tester la reconstruction Worker</button>
        <button onClick={() => {responses.current++; setClicks(responses.current);}}>Réactivité : {clicks}</button>
      </>}
      <button onClick={() => setOther(value => !value)}>{other ? 'Retour à la pièce' : 'Autre projet'}</button>
    </nav>
    {other ? <p className="p-8">Autre projet · éditeur conservé en mémoire</p> :
      <ContextWorkspace>{() => <div className="p-6"><h1>Conversation</h1><p className="text-sm mt-4">Qualification de l’éditeur intégré, sur une copie du document conservé.</p></div>}</ContextWorkspace>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<Fixture />);
