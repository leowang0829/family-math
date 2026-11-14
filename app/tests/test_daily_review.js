const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const workspace=path.resolve(__dirname,'../../..');
function boot(folder,initial={},now={value:Date.parse("2026-10-29T10:00:00+08:00")}){
 const root=path.resolve(__dirname,'../dist'),handlers={};let store={};const app={innerHTML:'',addEventListener:(k,f)=>handlers['app:'+k]=f};
 const document={hidden:false,activeElement:null,documentElement:{style:{}},getElementById:id=>id==='app'?app:{textContent:'',classList:{add(){},remove(){}}},addEventListener:(k,f)=>{(handlers[k]||(handlers[k]=[])).push(f)},querySelector:()=>null};
 const window={scrollTo(){},addEventListener(){},ZHIYI_STANDALONE:true};window.MathRefresh={safeToRender:()=>true};
 class TestDate extends Date{constructor(...args){super(...(args.length?args:[now.value]));}static now(){return now.value;}}
 const ctx={window,document,Intl,Date:TestDate,JSON,Math,Number,String,Map,Set,URL,Blob,console,setTimeout:()=>1,clearTimeout(){},localStorage:{getItem:k=>store[k]||JSON.stringify(initial),setItem:(k,v)=>store[k]=v},sessionStorage:{getItem(){},removeItem(){}},location:{protocol:'file:'},navigator:{}};vm.createContext(ctx);
 for(const file of ['data.js','curriculum.js','learning-evidence.js','daily-quotes.js','answer-fields.js','review-bank.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx);
 let js=fs.readFileSync(path.join(root,'app.js'),'utf8');js=js.replace(/\}\)\(\);\s*$/,`window.test={startDailyReview,dailyReviewKey,dailyReviewResults,dailyReviewItems,createDailyReviewPlan,dailyReviewCardHTML,nextBankReview,day:today,state,record,due,reviewHTML,lessonErrors,openLesson,checkLesson,bankErrors,bankEntry,startBankReview,gradeBank,bankReviewHTML,nextVariationIndex,openQuestion,allQuestions,workbookReady,workbookHTML,startWorkbook,structuredHTML,submitCard,prepareCard,cardKey,checkAnswer,lessonPracticeHTML,checkLesson,originalEvidence,saveStructuredAttempt,originalHTML,homeHTML,scratchContext,markOriginalHelp,setApi:f=>api=f};})();`);vm.runInContext(js,ctx);return {t:window.test,window,app,handlers,now};
}



(async()=>{for(const folder of [path.basename(path.resolve(__dirname,'..'))]){
 const {t,app,now}=boot(folder);t.state.connection.paired=false;await t.startDailyReview();
 const day=t.day(),ids=Array.from(t.state.bankReview.items,q=>q.id);assert.equal(ids.length,5);assert.equal(new Set(ids).size,5);assert(t.state.records[t.dailyReviewKey()]);assert(!app.innerHTML.includes('data-action="bank-new-group"'),'daily questions cannot be swapped');
 t.nextBankReview();assert.equal(t.state.bankReview.index,0,'unanswered question cannot count as completed');t.gradeBank();assert.equal(t.dailyReviewAttempts?.length||t.state.attempts.length,0,'blank answer has no progress');
 const q=t.state.bankReview.items[0];t.state.bankReview.answer=String(q.type==='choice'?q.options.find(x=>x!==q.answer):q.answer+1);t.gradeBank();assert.equal(t.bankErrors().length,1,'daily wrong answer is collected immediately');assert.equal(Object.keys(t.dailyReviewResults()).length,1);t.nextBankReview();assert.equal(t.state.bankReview.index,1);
 const saved={records:JSON.parse(JSON.stringify(t.state.records)),attempts:JSON.parse(JSON.stringify(t.state.attempts)),drafts:[]};const resume=boot(folder,saved,now).t;resume.state.connection.paired=false;await resume.startDailyReview();assert.deepEqual(Array.from(resume.state.bankReview.items,q=>q.id),ids,'refresh resumes same five');assert.equal(resume.state.bankReview.index,1,'resume skips already submitted question');
 for(let i=1;i<5;i++){const p=resume.state.bankReview.items[resume.state.bankReview.index];resume.state.bankReview.answer=String(p.answer);resume.gradeBank();resume.nextBankReview();}
 assert(resume.state.bankReview.done);assert.equal(Object.keys(resume.dailyReviewResults()).length,5);assert(resume.dailyReviewCardHTML().includes('今天已完成 5 / 5'));await resume.startDailyReview();assert(resume.state.bankReview.done,'same day completion cannot generate another daily group');assert.equal(resume.state.attempts.filter(a=>a.dailyReviewDate===day).length,5);
 const bad=resume.bankErrors()[0];resume.startWorkbook([bad.id]);resume.bankEntry(bad.id).answer=String(bad.bankQuestion.answer);resume.gradeBank(bad.id);assert.equal(resume.record(resume.bankErrors()[0]).status,'mastered');
 now.value+=86400000;await resume.startDailyReview();assert.notEqual(resume.state.bankReview.day,day);assert.equal(Object.keys(resume.dailyReviewResults()).length,0);assert(!resume.state.bankReview.items.some(q=>ids.includes(q.id)),'next day selects unseen questions');
 const synced={records:JSON.parse(JSON.stringify(resume.state.records)),attempts:JSON.parse(JSON.stringify(resume.state.attempts))};const remote=boot(folder).t;remote.state.connection.paired=true;remote.setApi(async p=>{assert.equal(p,'/api/progress');return {progress:synced};});await remote.startDailyReview();assert.deepEqual(Array.from(remote.state.bankReview.items,q=>q.id),ids,'other connected device resumes cloud daily plan');assert(remote.state.bankReview.done);assert.equal(remote.state.startingDaily,false);
 console.log(folder+': fixed daily five, refresh resume, blank guard, wrong collection, one-pass mastery, next-day rotation and cloud plan resume passed');
}})().catch(e=>{console.error(e);process.exitCode=1;});
