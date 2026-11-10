// Exercise the actual pinned geometry engine in a dedicated Worker.
const workerSource = `
import init, {open, execute, save} from '${location.origin}/runtime/bigbrain_worker_probe.js';
await init();
self.onmessage = ({data}) => {
  const started=performance.now();
  try {
    let result;
    if(data.action==='open') result=open(new Uint8Array(data.bytes));
    else if(data.action==='execute') result=JSON.parse(execute(data.command,JSON.stringify(data.params)));
    else if(data.action==='save') result=save();
    else throw new Error('Unknown probe action');
    const response={id:data.id,result,ms:performance.now()-started};
    self.postMessage(response,result instanceof Uint8Array ? [result.buffer] : []);
  } catch(error) {self.postMessage({id:data.id,error:String(error),ms:performance.now()-started});}
};
self.postMessage({ready:true});`;
const output=document.querySelector('pre');
const record={stages:[],userAgent:navigator.userAgent};
let previous=performance.now(), maxGap=0, active=false, frames=0;
function tick(now){if(active){maxGap=Math.max(maxGap,now-previous);frames++;}previous=now;requestAnimationFrame(tick);}
requestAnimationFrame(tick);
document.querySelector('#responsive').onclick=()=>{
  record.clicks=(record.clicks||0)+1;
  document.querySelector('#clicks').textContent=String(record.clicks);
};
async function persist(){
  record.maxHostFrameGapMs=maxGap;record.frames=frames;
  output.textContent=JSON.stringify(record,null,2);
  const response=await fetch('/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(record)});
  if(!response.ok)throw new Error('Evidence persistence failed');
}
document.querySelector('#run').onclick=async()=>{
  document.querySelector('#run').disabled=true;
  const url=URL.createObjectURL(new Blob([workerSource],{type:'text/javascript'}));
  const worker=new Worker(url,{type:'module'});
  let sequence=0;const pending=new Map();
  const ready=new Promise((resolve,reject)=>{
    worker.onmessage=({data})=>{
      if(data.ready){resolve();return;}
      const request=pending.get(data.id);if(!request)return;
      pending.delete(data.id);data.error?request.reject(new Error(data.error)):request.resolve(data);
    };
    worker.onerror=event=>{const error=new Error(event.message);reject(error);for(const request of pending.values())request.reject(error);pending.clear();};
  });
  const call=(action,data={})=>new Promise((resolve,reject)=>{
    const id=++sequence;pending.set(id,{resolve,reject});worker.postMessage({id,action,...data});
  });
  async function stage(name,action){
    record.pendingStage={name,started:new Date().toISOString()};await persist();
    const started=performance.now();const value=await action();
    record.stages.push({name,ms:performance.now()-started,workerMs:value?.ms});
    delete record.pendingStage;await persist();return value?.result;
  }
  try{
    active=true;await ready;
    const bytes=await (await fetch('/fixture.sc')).arrayBuffer();
    await stage('open retained drawing42',()=>call('open',{bytes}));
    record.initial=await stage('inspect initial',()=>call('execute',{command:'document.inspect',params:{measure:true}}));
    const parameter=record.initial.params.find(item=>item.name==='flange_thickness');
    if(!parameter)throw new Error('Retained qualification parameter unavailable');
    await stage('edit parameter',()=>call('execute',{command:'parameters.change',params:{name:parameter.name,expression:(parameter.value+1)+' mm'}}));
    record.edited=await stage('inspect edited',()=>call('execute',{command:'document.inspect',params:{measure:true}}));
    await stage('undo',()=>call('execute',{command:'edit.undo',params:{}}));
    record.undone=await stage('inspect undone',()=>call('execute',{command:'document.inspect',params:{measure:true}}));
    const saved=await stage('save native checkpoint',()=>call('save'));
    const stored=await fetch('/saved.sc',{method:'POST',body:saved});if(!stored.ok)throw new Error('Checkpoint persistence failed');
    await stage('reopen checkpoint',()=>call('open',{bytes:saved.buffer}));
    record.reopened=await stage('inspect reopened',()=>call('execute',{command:'document.inspect',params:{measure:true}}));
    record.status='observed';
  }catch(error){record.status='failed';record.error=String(error);}
  finally{active=false;worker.terminate();URL.revokeObjectURL(url);await persist();}
};
