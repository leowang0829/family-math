/* Check releases without interrupting a child's current work. */
(function(root){
  'use strict';
  const editing = context => context.busy || context.modal || context.inputFocused || context.pickingPhoto;
  const safeToRender = context => !editing(context) && !context.practicing && !(context.view==='capture'&&context.hasCapture);
  const safeToReload = context => safeToRender(context) && !context.hasCapture && !context.saving &&
    ['home','library','knowledge','settings'].includes(context.view) && context.idleMs >= 3000;
  function create(options){
    let pending='', checking=false, syncing=false, reloading=false, available=false, lastCheck=0;
    async function apply(){
      if(!pending || !available || reloading || !options.isVisible() || !options.canReload())return false;
      reloading=true;
      try{
        if(await options.beforeReload()===false){reloading=false;return false;}
        options.reload(pending);return true;
      }catch(_){reloading=false;return false;}
    }
    async function check(){
      if(checking || reloading || !options.isVisible())return;
      checking=true;
      try{
        const version=await options.fetchVersion();
        available=/^[a-f0-9]{64}$/.test(version);
        if(/^[a-f0-9]{64}$/.test(version) && version!==options.version){
          if(pending!==version){pending=version;options.onUpdate?.();}
        }else if(version===options.version)pending='';
        await apply();
      }catch(_){available=false;/* Offline: keep the page and all local work. */}
      finally{checking=false;lastCheck=Date.now();}
    }
    async function sync(){
      if(syncing || reloading || !options.isVisible() || !options.canSync())return;
      syncing=true;try{await options.sync();}catch(_){}finally{syncing=false;}
    }
    async function wake(){await check();await sync();}
    function start(){
      const timer=setInterval(()=>{
        if(!options.isVisible())return;
        if(Date.now()-lastCheck>=30000)check();else apply();
      },5000);
      const dataTimer=setInterval(sync,30000);
      return ()=>{clearInterval(timer);clearInterval(dataTimer);};
    }
    return {check,apply,sync,wake,start};
  }
  const api={create,safeToRender,safeToReload};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MathRefresh=api;
})(typeof window==='object'?window:globalThis);
