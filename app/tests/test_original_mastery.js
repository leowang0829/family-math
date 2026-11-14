const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const workspace=path.resolve(__dirname,'../../..');
function boot(folder){
 const root=path.resolve(__dirname,'../dist'),handlers={};let store={};const app={innerHTML:'',addEventListener:(k,f)=>handlers['app:'+k]=f};
 const document={hidden:false,activeElement:null,documentElement:{style:{}},getElementById:id=>id==='app'?app:{textContent:'',classList:{add(){},remove(){}}},addEventListener:(k,f)=>{(handlers[k]||(handlers[k]=[])).push(f)},querySelector:()=>null};
 const window={scrollTo(){},addEventListener(){},ZHIYI_STANDALONE:true};window.MathRefresh={safeToRender:()=>true};
 const ctx={window,document,Intl,Date,JSON,Math,Number,String,Map,Set,URL,Blob,console,setTimeout:()=>1,clearTimeout(){},localStorage:{getItem:k=>store[k]||null,setItem:(k,v)=>store[k]=v},sessionStorage:{getItem(){},removeItem(){}},location:{protocol:'file:'},navigator:{}};vm.createContext(ctx);
 for(const file of ['data.js','curriculum.js','learning-evidence.js','daily-quotes.js','answer-fields.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx);
 let js=fs.readFileSync(path.join(root,'app.js'),'utf8');js=js.replace(/\}\)\(\);\s*$/,`window.test={state,record,due,reviewHTML,lessonErrors,openLesson,checkLesson,workbookHTML,startWorkbook,structuredHTML,submitCard,prepareCard,cardKey,checkAnswer,lessonPracticeHTML,checkLesson,originalEvidence,saveStructuredAttempt,originalHTML,homeHTML,scratchContext,markOriginalHelp,setApi:f=>api=f};})();`);vm.runInContext(js,ctx);return {t:window.test,window,app};
}

for(const folder of [path.basename(path.resolve(__dirname,'..'))]){
 const {t,app}=boot(folder),id='a'.repeat(32);const q={id,serverId:id,title:'测试错题',problem:'2+3',topic:'integer',serverStatus:'ready',assessment:'wrong',status:'pending',practices:[0,1,2].map(()=>({text:'2+3',answer:5,unit:'',hint:'先相加',solution:'5'})),solution:{problem:'2+3',answer:'5'}};
 t.state.drafts=[q];t.state.connection={paired:true};const entry={answers:{p1:'5'},message:'答对'},right={correct:true,total_parts:1,correct_parts:1,results:[]},wrong={...right,correct:false};const context={scope:'original',question_id:id,index:0};
 t.saveStructuredAttempt(context,entry,{...right,correct:null});assert.equal(t.state.attempts.length,0);assert.notEqual(t.record(q).status,'mastered');
 t.saveStructuredAttempt(context,entry,wrong);assert.notEqual(t.record(q).status,'mastered');
 t.saveStructuredAttempt(context,entry,right);assert.equal(t.record(q).status,'mastered','one whole original pass earns mastery');assert(t.due().some(x=>x.id===id),'mastered originals still supply variants for review');
 t.state.selected=id;t.state.tab='practice';t.state.answer='0';t.checkAnswer();assert.equal(t.record(q).status,'mastered','wrong variation cannot overwrite original');assert(t.state.records['review-'+id]);t.state.answer='5';t.checkAnswer();assert.equal(t.record(q).status,'mastered');
 t.saveStructuredAttempt({scope:'practice',question_id:id,index:1},entry,wrong);assert.equal(t.record(q).status,'mastered','structured variation also isolated');
 t.state.records[id]={status:'learning'};assert.equal(t.record(q).status,'mastered','historical successful original is reflected without replay');assert(t.libraryHTML===undefined||t.record(q).status==='mastered');
 t.state.records['review-'+id].due='2000-01-01';q.practices=[];q.practicesStatus='on_demand';assert(t.due().some(x=>x.id===id),'on-demand variants remain reachable without paid auto generation');
 const b=boot(folder).t;b.state.drafts=[q];b.state.originalHelp={[id+':'+new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())]:true};b.saveStructuredAttempt(context,entry,right);assert.equal(b.record(q).status,'mastered','correct original counts; assistance still recorded');assert(b.state.attempts[0].assisted);
 const c=boot(folder),course=Object.values(c.window).find(x=>x&&Array.isArray(x.lessons));const lesson=course.lessons[0],day=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());c.t.state.attempts=[{id:'1-wrong',questionId:'lesson-'+lesson.id,practice:0,correct:false,assisted:false,date:day}];assert.equal(c.t.lessonErrors().length,1);c.t.openLesson(lesson.id,'practice');c.t.state.learning.answer=String(lesson.practices[0].answer);c.t.checkLesson();assert.equal(c.t.lessonErrors()[0].status,'mastered','one corrected curriculum wrong question does not wait for the whole lesson');
 console.log(folder+': whole pass once, no partial/uncertain pass, historical progress, assisted trace, numerical/structured review isolation, mastered and on-demand review eligibility passed');
}
