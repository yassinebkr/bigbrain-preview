// Real WASM qualification with retained receipts and injected transport loss.
import { CadBrowserTransport, CadBrowserExecutor, SolidCraftBrowserEngine } from '/static/cad-browser-bridge.mjs';
const config = await (await fetch('/config')).json();
const transport = new CadBrowserTransport(config.documentId, config.sessionId);
const engine = new SolidCraftBrowserEngine(document.querySelector('#editor'), '/app/index.html?webgl', config.build);
const executor = new CadBrowserExecutor(transport, engine);
const report = await (await fetch('/report')).json();
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const parameter = async () => (await engine.api.inspect({measure:false})).params.find(p => p.name === 'width').value;
async function record(name, action) {
  document.querySelector('#status').textContent = name;
  const start = performance.now();
  const detail = await action();
  report.stages.push({ name, ms: performance.now() - start, detail });
  await fetch('/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(report)});
  document.querySelector('#report').textContent = JSON.stringify(report, null, 2);
}
async function enqueue(id, value) {
  const state = await transport.call('state');
  return transport.call('enqueue', {operationId:id, revision:state.revision, hash:state.hash,
    command:'parameters.change', params:{name:'width', expression:`${value} mm`}});
}
async function run() {
  document.querySelector('#run').disabled = true;
  delete report.error;
  try {
    await executor.connect();
    if (!new URL(location.href).searchParams.has('resume')) {
      const width = await parameter();
      report.initialWidth = width;
      await record('capabilities and agent command', async () => {
        await executor.control('resume');
        assert(engine.frame.inert, 'Editor must be locked during agent ownership');
        await enqueue('first', width + 1);
        await executor.step();
        assert(await parameter() === width + 1, 'Browser parameter edit missing');
        return { revision:executor.state.revision, commandCount:executor.state.capabilities.commands.length };
      });
      await record('lost acknowledgement after committed checkpoint', async () => {
        await enqueue('lost-ack', width + 2);
        const call = transport.call.bind(transport);
        transport.call = async (action, data) => {
          const value = await call(action, data);
          if (action === 'accept') throw new Error('Injected lost acknowledgement');
          return value;
        };
        try { await executor.step(); } catch (error) { assert(String(error).includes('Injected'), String(error)); }
        transport.call = call;
        await executor.connect();
        assert(await parameter() === width + 2, 'Committed result lost after acknowledgement failure');
        assert(await executor.step() === null, 'Accepted command executed twice');
        assert(executor.state.revision === 2, 'Duplicate revision after reconnect');
        return executor.state.operations;
      });
      await record('interruption after geometry before checkpoint commit', async () => {
        await enqueue('interrupted', width + 3);
        const operation = await transport.call('claim', {generation:executor.state.generation});
        await engine.execute(operation.command, operation.params);
        assert(await parameter() === width + 3, 'Injected interruption did not execute geometry');
        assert((await transport.call('state')).revision === 2, 'Uncommitted geometry advanced revision');
        return {operationId:operation.id, retainedRevision:2};
      });
      // Reload the whole host page, discarding its JS state and the WASM instance.
      location.href = '/?resume=1';
      return;
    }
    const width = report.initialWidth;
    await record('full page reload restores and replays uncertain operation', async () => {
      assert(await parameter() === width + 2, 'Reload failed to restore accepted base');
      await executor.step();
      assert(await parameter() === width + 3, 'Interrupted operation did not replay');
      assert(executor.state.revision === 3, 'Replay produced wrong revision');
      return executor.state.operations;
    });
    await record('pause drains operation and manual save governs resume', async () => {
      await enqueue('pause-operation', width + 4);
      const operation = await transport.call('claim', {generation:executor.state.generation});
      await executor.control('pause');
      assert(engine.frame.inert && executor.state.pause, 'Pause unlocked an executing operation');
      const result = await engine.execute(operation.command, operation.params);
      const bytes = await engine.save();
      let text = ''; for (const value of bytes) text += String.fromCharCode(value);
      await transport.call('accept', {operationId:operation.id, generation:operation.generation, native:btoa(text), result});
      executor.update(await transport.call('state'));
      assert(!engine.frame.inert && executor.state.owner === 'user', 'Pause failed to transfer editing');
      await engine.api.execute('parameters.change', {name:'width', expression:`${width+5} mm`});
      executor.dirty = true;
      let rejected = false;
      try { await executor.control('resume'); } catch { rejected = true; }
      assert(rejected, 'Unsaved user edits admitted to agent');
      await executor.saveManual();
      await executor.control('resume');
      await enqueue('after-manual', width + 6);
      await executor.step();
      assert(await parameter() === width + 6, 'Agent failed after manual checkpoint');
      return {revision:executor.state.revision, width:await parameter()};
    });
    await record('stop revokes running operation and restores accepted geometry', async () => {
      await enqueue('stopped', width + 7);
      const operation = await transport.call('claim', {generation:executor.state.generation});
      await engine.execute(operation.command, operation.params);
      await executor.control('stop');
      assert(await parameter() === width + 6, 'Stop retained unaccepted geometry');
      assert(executor.state.owner === 'user', 'Stop retained agent ownership');
      return executor.state.operations;
    });
    await record('server queue constructs a named solid through serial command pump', async () => {
      await executor.control('resume');
      const state = await transport.call('state');
      await transport.call('enqueue', {operationId:'new-solid', revision:state.revision, hash:state.hash,
        command:'solid.box', params:{length:'10 mm', width:'10 mm', height:'10 mm', corner:[100,0,0],
          name:'BridgeBoxFeature', body_name:'BridgeBox'}});
      const abort = new AbortController();
      const pump = executor.run(abort.signal);
      try {
        const deadline = performance.now() + 30000;
        let receipt;
        while (performance.now() < deadline) {
          receipt = await transport.call('result', {operationId:'new-solid'});
          if (receipt.status === 'accepted' || receipt.status === 'failed') break;
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        assert(receipt.status === 'accepted', 'Serial pump failed to construct the solid');
        const inspection = await engine.api.inspect({measure:false});
        assert(inspection.bodies.some(body => body.name === 'BridgeBox'), 'Named constructed solid missing');
        return {revision:receipt.revision, bodyNames:inspection.bodies.map(body => body.name)};
      } finally { abort.abort(); await pump; }
    });
    report.status = 'passed';
  } catch(error) {
    report.status = 'failed'; report.error = String(error);
  }
  await fetch('/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(report)});
  document.querySelector('#status').textContent = report.status;
  document.querySelector('#report').textContent = JSON.stringify(report, null, 2);
}
document.querySelector('#run').onclick = run;
if (new URL(location.href).searchParams.has('resume')) run();
