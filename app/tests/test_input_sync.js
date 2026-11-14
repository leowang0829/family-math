const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'../dist');
function boot(){
 const handlers={},timers=new Map();let timer=0,renders=0;
 const input={id:'library-search',type:'search',value:'',selectionStart:0,selectionEnd:0,focus(){throw Error('stable input must not be refocused');},setSelectionRange(){throw Error('native selection must not be reset');}};
 const app={innerHTML:'',addEventListener(name,fn){(handlers[name]||=[]).push(fn);}};
 const document={hidden:false,activeElement:input,documentElement:{style:{}},getElementById(id){return id==='app'?app:id==='library-search'?input:{textContent:'',classList:{add(){},remove(){}}};},addEventListener(){},querySelector(){return null;}};
 const window={ZHIYI_STANDALONE:true,scrollTo(){},addEventListener(){},MathRefresh:{safeToRender:()=>true},MathStableRender:{render(_app,html){renders++;app.innerHTML=html;}}};
 const context={window,document,Intl,Date,JSON,Math,Number,String,Map,Set,URL,Blob,console,localStorage:{getItem(){return null;},setItem(){}},sessionStorage:{getItem(){},removeItem(){}},location:{protocol:'file:'},navigator:{},setTimeout(fn){const id=++timer;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);}};
 vm.createContext(context);
 for(const name of ['data.js','curriculum.js','learning-evidence.js'])vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),context);
 let code=fs.readFileSync(path.join(root,'app.js'),'utf8');code=code.replace(/\}\)\(\);\s*$/,`window.test={state,scheduleProgress,setApi:f=>api=f};})();`);vm.runInContext(code,context);timers.clear();
 return {t:window.test,input,app,renders:()=>renders,timers,emit(name,extra={}){for(const fn of handlers[name]||[])fn({target:input,...extra});},async next(){const [id,fn]=timers.entries().next().value||[];assert(fn,'expected a queued callback');timers.delete(id);return fn();}};
}
(async()=>{
 const b=boot();b.t.state.view='library';const count=b.renders();
 b.emit('compositionstart');b.input.value='fen';b.emit('input',{isComposing:true});assert.equal(b.t.state.search,'');assert.equal(b.timers.size,0);assert.equal(b.renders(),count);
 b.input.value='分数';b.emit('compositionend');b.emit('input',{isComposing:false});assert.equal(b.timers.size,1);await b.next();assert.equal(b.t.state.search,'分数');assert.equal(b.renders(),count+1);assert(b.app.innerHTML.includes('value="分数"'));
 b.input.value='分';b.emit('input');b.input.value='分数大小';b.emit('input');assert.equal(b.timers.size,1);await b.next();assert.equal(b.t.state.search,'分数大小');
 b.input.value='<script>&"';b.emit('input');await b.next();assert(!b.app.innerHTML.includes('value="<script>'));assert(b.app.innerHTML.includes('&lt;script&gt;&amp;&quot;'));
 b.input.value='';b.emit('search');await b.next();assert.equal(b.t.state.search,'');
 b.input.value='取消';b.emit('input');b.emit('compositionstart');assert.equal(b.timers.size,0,'starting the next composition cancels pending redraw');

 const c=boot(),pending=[],payloads=[];let inFlight=0,peak=0;
 c.t.state.connection.paired=true;c.t.state.records={one:{updatedAt:1}};
 c.t.setApi(async(_path,body)=>{payloads.push(body);inFlight++;peak=Math.max(peak,inFlight);await new Promise(resolve=>pending.push(resolve));inFlight--;});
 c.t.scheduleProgress();const first=c.next();assert.equal(inFlight,1);
 c.t.state.records.two={updatedAt:2};c.t.scheduleProgress();await c.next();assert.equal(peak,1,'progress saves may not overlap');assert(!payloads[0].progress.records.two,'in-flight payload is an immutable snapshot');
 pending.shift()();await first;assert(c.t.state.syncDirty,'an older response cannot acknowledge newer work');
 const second=c.next();assert.equal(inFlight,1);assert(payloads[1].progress.records.two);pending.shift()();await second;assert.equal(c.t.state.syncDirty,false);assert.equal(peak,1);
 c.t.setApi(async()=>{throw Error('offline');});c.t.scheduleProgress();await c.next();assert(c.t.state.syncDirty,'network failure keeps local work marked pending');
 console.log('Chinese composition, debounced search, escaped input, native focus, serial progress saves and stale acknowledgements passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
