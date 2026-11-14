/* Device-local handwriting. No recognition requests or network calls. */
(function(root){
 'use strict';
 const fingerprint=text=>{let n=2166136261;for(const c of String(text)){n^=c.charCodeAt(0);n=Math.imul(n,16777619);}return (n>>>0).toString(36);};
 function createModel(initial=[]){
  let strokes=Array.isArray(initial)?initial.filter(s=>s&&['pen','eraser'].includes(s.tool)&&Array.isArray(s.points)).map(s=>({tool:s.tool,points:s.points.filter(p=>Array.isArray(p)&&p.length===2&&p.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=1)).slice(0,12000)})):[];
  const history=[];
  return {get strokes(){return strokes;},add(stroke){if(!stroke.points.length)return;strokes.push(stroke);history.push({type:'add'});},clear(){if(strokes.length){history.push({type:'clear',strokes});strokes=[];}},undo(){const action=history.pop();if(!action)return false;if(action.type==='clear')strokes=action.strokes;else strokes.pop();return true;}};
 }
 function createStore(storage,profile){
  const prefix='math-handwriting-v1:'+profile+':';
  return {read(key){try{return JSON.parse(storage.getItem(prefix+key)||'[]');}catch(_){return [];}},write(key,strokes){try{storage.setItem(prefix+key,JSON.stringify(strokes));return true;}catch(_){return false;}},key:(kind,id,index,text)=>kind+':'+id+':'+index+':'+fingerprint(text)};
 }
 function createUI(doc,storage,profile){
  const store=createStore(storage,profile);let panel,canvas,context,currentKey='',model=createModel(),active=null,tool='pen',penOnly=false,opened=false,previousFocus;
  const status=message=>{panel.querySelector('[data-scratch-status]').textContent=message;};
  function save(){if(!currentKey)return true;const ok=store.write(currentKey,model.strokes);status(ok?'草稿已保存在这台设备':'草稿暂未保存，空间可能不足，请先不要关闭页面');return ok;}
  function line(stroke,width,height){if(!stroke.points.length)return;context.save();context.globalCompositeOperation=stroke.tool==='eraser'?'destination-out':'source-over';context.strokeStyle='#304e45';context.fillStyle='#304e45';context.lineWidth=stroke.tool==='eraser'?22:2.5;context.lineCap='round';context.lineJoin='round';context.beginPath();stroke.points.forEach(([x,y],i)=>i?context.lineTo(x*width,y*height):context.moveTo(x*width,y*height));if(stroke.points.length===1){const [x,y]=stroke.points[0];context.arc(x*width,y*height,context.lineWidth/2,0,Math.PI*2);context.fill();}else context.stroke();context.restore();}
  function redraw(){if(!canvas)return;const rect=canvas.getBoundingClientRect();if(!rect.width||!rect.height)return;const ratio=Math.min(root.devicePixelRatio||1,2),width=Math.round(rect.width*ratio),height=Math.round(rect.height*ratio);if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}context.setTransform(ratio,0,0,ratio,0,0);context.clearRect(0,0,rect.width,rect.height);for(const stroke of model.strokes)line(stroke,rect.width,rect.height);if(active)line(active.stroke,rect.width,rect.height);}
  const point=event=>{const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))].map(n=>Math.round(n*10000)/10000);};
  function finish(){if(!active)return;model.add(active.stroke);active=null;redraw();save();}
  function clearPadSelection(){const selection=doc.getSelection?.();if(selection&&[selection.anchorNode,selection.focusNode].some(node=>node&&panel.contains(node)))selection.removeAllRanges();}
  function ensure(){if(panel)return;
   panel=doc.createElement('aside');panel.id='math-scratchpad';panel.className='math-scratchpad';panel.hidden=true;panel.setAttribute('aria-label','手写草稿');
   panel.innerHTML='<header class="scratch-header"><div><strong>手写草稿</strong><span data-scratch-status role="status">手指或 Apple Pencil 都可以写</span></div><button type="button" data-scratch-close>收起</button></header><p class="scratch-question"></p><div class="scratch-tools"><button type="button" data-scratch-tool="pen" aria-pressed="true">画笔</button><button type="button" data-scratch-tool="eraser" aria-pressed="false">橡皮</button><button type="button" data-scratch-undo>撤销</button><button type="button" data-scratch-clear>清空</button><label><input type="checkbox" data-scratch-pen-only>仅 Apple Pencil</label></div><div class="scratch-paper"><canvas aria-label="手写计算草稿区域"></canvas></div><footer><span>写完后，将结果填入答案框。</span><button type="button" data-scratch-answer>回到答案</button></footer>';
   doc.body.append(panel);canvas=panel.querySelector('canvas');context=canvas.getContext('2d');
   // iPad can select toolbar text during palm contact, even when the canvas is protected.
   for(const name of ['selectstart','contextmenu','dragstart'])panel.addEventListener(name,event=>event.preventDefault(),{capture:true});
   panel.addEventListener('pointerdown',clearPadSelection,{capture:true});
   panel.addEventListener('click',e=>{const button=e.target.closest('button');if(!button)return;if(button.hasAttribute('data-scratch-close')||button.hasAttribute('data-scratch-answer')){const focusAnswer=button.hasAttribute('data-scratch-answer');close();if(focusAnswer)doc.querySelector('#lesson-answer,#practice-answer')?.focus();return;}if(button.dataset.scratchTool){finish();tool=button.dataset.scratchTool;for(const b of panel.querySelectorAll('[data-scratch-tool]'))b.setAttribute('aria-pressed',String(b===button));canvas.dataset.tool=tool;}else if(button.hasAttribute('data-scratch-undo')){finish();model.undo();redraw();save();}else if(button.hasAttribute('data-scratch-clear')){finish();model.clear();redraw();save();}});
   panel.querySelector('[data-scratch-pen-only]').addEventListener('change',event=>{finish();penOnly=event.target.checked;});
   canvas.addEventListener('pointerdown',event=>{event.preventDefault();if(active||event.button>0||(penOnly&&event.pointerType!=='pen'))return;active={id:event.pointerId,stroke:{tool,points:[point(event)]}};try{canvas.setPointerCapture(event.pointerId);}catch(_){}redraw();});
   canvas.addEventListener('pointermove',event=>{if(!active||event.pointerId!==active.id)return;event.preventDefault();const events=event.getCoalescedEvents?.()||[event];for(const e of events.length?events:[event]){if(active.stroke.points.length<12000)active.stroke.points.push(point(e));}redraw();});
   for(const name of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(name,event=>{if(active?.id===event.pointerId){if(name==='pointerup')active.stroke.points.push(point(event));finish();}});
   if(root.ResizeObserver)new root.ResizeObserver(redraw).observe(canvas);
   root.addEventListener('resize',()=>{finish();redraw();});
   doc.addEventListener('visibilitychange',()=>{if(doc.hidden){finish();save();}});root.addEventListener('pagehide',()=>{finish();save();});
   doc.addEventListener('keydown',event=>{if(opened&&event.key==='Escape')close();});
  }
  function open(options){ensure();finish();if(currentKey)save();previousFocus=doc.activeElement;currentKey=options.key;model=createModel(store.read(currentKey));panel.querySelector('.scratch-question').textContent=options.prompt||options.title||'在这里算一算';panel.hidden=false;opened=true;clearPadSelection();doc.body.classList.add('math-scratch-open');previousFocus?.blur?.();redraw();status('草稿按这道题单独保存');doc.dispatchEvent(new root.CustomEvent('math-scratchpad-change'));}
  function close(){if(!panel)return;finish();save();panel.hidden=true;opened=false;doc.body.classList.remove('math-scratch-open');previousFocus?.focus?.();doc.dispatchEvent(new root.CustomEvent('math-scratchpad-change'));}
  return {open,close,isOpen:()=>opened,isDrawing:()=>!!active,currentKey:()=>currentKey,key:store.key};
 }
 const api={createModel,createStore,fingerprint,createUI};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else{const profile=docProfile();let storage;try{storage=root.localStorage;}catch(_){storage=null;}root.MathScratchpad=createUI(root.document,storage,profile);root.MathScratchpadCore=api;}
 function docProfile(){return root.document.currentScript?.dataset.profile||'family';}
})(typeof window==='object'?window:globalThis);
