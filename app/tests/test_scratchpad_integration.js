const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const core=require('../dist/scratchpad.js');
for(const folder of ['current app']){
 const root=path.resolve(__dirname,'../dist'),events=[],app={innerHTML:'',addEventListener(){}};let opened=false,key='',opens=0;
 const pad={isOpen:()=>opened,currentKey:()=>key,key:core.createStore(null,'x').key,open(o){opened=true;key=o.key;opens++},close(){opened=false}};
 const document={hidden:false,activeElement:null,documentElement:{style:{}},getElementById:id=>id==='app'?app:{textContent:'',classList:{add(){},remove(){}}},addEventListener(n,f){events.push([n,f])},querySelector(){return null}};
 const window={MathScratchpad:pad,scrollTo(){},addEventListener(){},ZHIYI_STANDALONE:true};
 const sandbox={window,document,Intl,Date,JSON,Math,Number,String,Map,Set,URL,Blob,console,setTimeout:()=>1,clearTimeout(){},localStorage:{getItem(){},setItem(){}},sessionStorage:{getItem(){},removeItem(){}},location:{protocol:'file:'},navigator:{}};vm.createContext(sandbox);
 for(const f of ['data.js','curriculum.js','learning-evidence.js','auto-refresh.js'])vm.runInContext(fs.readFileSync(path.join(root,f),'utf8'),sandbox);
 let js=fs.readFileSync(path.join(root,'app.js'),'utf8').replace(/\}\)\(\);\s*$/,`window.test={state,openLesson,setLessonPractice,render,refreshContext,practiceHTML,scratchContext};})();`);vm.runInContext(js,sandbox);
 const t=window.test;t.openLesson('1.1','practice');assert(app.innerHTML.includes('data-action="open-scratchpad"'));const c=t.scratchContext();pad.open({key:pad.key(c.kind,c.id,c.index,c.prompt)});t.render();assert.equal(opens,1,'feedback render must not reset undo history');assert(t.refreshContext().modal,'writing blocks background render/reload');t.setLessonPractice(1);assert.equal(opens,2,'switching questions loads separate scratchpad');t.state.view='home';t.render();assert.equal(opened,false);
 const q={id:'qa',title:'test',topic:'integer',status:'pending',practices:[{text:'5 < 8 & 3 > 1',kind:'基础',unit:'',hint:'',solution:''}],tags:[]};t.state.drafts=[q];t.state.selected='qa';t.state.practice=0;t.state.view='detail';t.state.tab='practice';const escaped={...q,practices:q.practices.map(p=>({...p,text:'5 &lt; 8 &amp; 3 &gt; 1'}))};const html=t.practiceHTML(escaped);assert(html.includes(pad.key('question','qa',0,q.practices[0].text)));assert(html.includes('data-scratch-prompt="5 &lt; 8 &amp; 3 &gt; 1"'));
 t.state.view='review';t.state.review={ids:['qa'],index:0,done:false};assert.equal(t.scratchContext().id,'qa');console.log(folder+': curriculum, AI variation and review contexts; per-question switching; refresh lock; escaped prompt identity passed');
}
