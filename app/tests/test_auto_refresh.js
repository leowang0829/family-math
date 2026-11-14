const assert=require('node:assert/strict');
const refresh=require('../dist/auto-refresh.js');
const base={view:'home',idleMs:4000};
assert.equal(refresh.safeToReload(base),true);
for(const context of [
  {...base,view:'lesson'},{...base,view:'review'},{...base,view:'detail'},
  {...base,inputFocused:true},{...base,hasCapture:true},{...base,busy:true},
  {...base,modal:true},{...base,pickingPhoto:true},{...base,saving:true},{...base,idleMs:1000}
])assert.equal(refresh.safeToReload(context),false,'unfinished work must block release reloads');
assert.equal(refresh.safeToRender({...base,practicing:true}),false);
assert.equal(refresh.safeToRender({...base,view:'capture',pickingPhoto:true}),false,'native Photos picker blocks background DOM replacement');
assert.equal(refresh.safeToRender({...base,view:'capture',hasCapture:true}),false);
(async()=>{
  let allowed=false,visible=true,offline=false,reloads=0,syncs=0,notices=0,saved=0;
  const current='a'.repeat(64),next='b'.repeat(64);
  const controller=refresh.create({version:current,isVisible:()=>visible,canReload:()=>allowed,canSync:()=>allowed,
    fetchVersion:async()=>{if(offline)throw Error('offline');return next;},
    beforeReload:()=>{saved++;return true;},reload:version=>{assert.equal(version,next);reloads++;},
    sync:async()=>{syncs++;},onUpdate:()=>{notices++;}});
  await controller.wake();assert.equal(reloads,0);assert.equal(syncs,0);assert.equal(notices,1);
  await controller.check();assert.equal(notices,1,'do not repeat pending update notices');
  visible=false;allowed=true;await controller.apply();assert.equal(reloads,0,'hidden apps never reload');
  visible=true;offline=true;await controller.check();assert.equal(reloads,0,'offline checks retain work');
  assert.equal(await controller.apply(),false,'offline pending updates also wait');
  offline=false;await controller.wake();assert.equal(reloads,1);assert.equal(saved,1);
  await controller.apply();assert.equal(reloads,1,'one reload per controller');
  const blocked=refresh.create({version:current,isVisible:()=>true,canReload:()=>true,canSync:()=>true,
    fetchVersion:async()=>next,beforeReload:()=>false,reload:()=>{throw Error('unsaved work reloaded');},sync:async()=>{}});
  await blocked.check();assert.equal(await blocked.apply(),false,'failed local saves block reload');
  let release=()=>{},calls=0;
  const syncing=refresh.create({version:current,isVisible:()=>true,canReload:()=>false,canSync:()=>true,
    fetchVersion:async()=>current,beforeReload:()=>true,reload:()=>{},sync:()=>{calls++;return new Promise(resolve=>{release=resolve;});}});
  const first=syncing.sync();await syncing.sync();assert.equal(calls,1,'slow syncs never overlap');release();await first;
  const invalid=refresh.create({version:current,isVisible:()=>true,canReload:()=>true,canSync:()=>true,
    fetchVersion:async()=>'<html>error</html>',beforeReload:()=>true,reload:()=>{throw Error('invalid release');},sync:async()=>{}});
  await invalid.check();
  console.log('Auto-refresh checks passed: safe updates, preserved work, offline/hidden behavior and non-overlapping sync.');
})().catch(error=>{console.error(error);process.exitCode=1;});
