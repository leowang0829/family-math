const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'../dist');
function boot(){let store={},quota=false;const events={},app={innerHTML:'',addEventListener:(name,f)=>events[name]=f};const document={hidden:false,activeElement:null,documentElement:{style:{}},getElementById:id=>id==='app'?app:{textContent:'',classList:{add(){},remove(){}}},addEventListener(){},querySelector(){return null;}};const window={scrollTo(){},addEventListener(){},ZHIYI_STANDALONE:true};window.MathRefresh={safeToRender:()=>true};const sandbox={window,document,Intl,Date,JSON,Math,Number,String,Map,Set,URL,Blob,console,setTimeout:()=>1,clearTimeout(){},localStorage:{getItem:k=>store[k]||null,setItem(k,v){if(quota)throw Error('quota');store[k]=v;}},sessionStorage:{getItem(){},removeItem(){}},location:{protocol:'file:'},navigator:{}};vm.createContext(sandbox);for(const name of ['data.js','curriculum.js','learning-evidence.js'])vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),sandbox);let js=fs.readFileSync(path.join(root,'app.js'),'utf8');js=js.replace(/\}\)\(\);\s*$/,`window.test={state,checkAnswer,openQuestion,checkLesson,lessonErrors,parseAnswer,persist,markAssistance,allQuestions,readinessCard,libraryHTML,realDetailHTML,captureHTML};})();`);vm.runInContext(js,sandbox);return {test:window.test,app,setQuota:q=>quota=q,store};}
const b=boot(),t=b.test;t.openQuestion('books');const q=b.test.state;
// Variation evidence has its own record and cannot overwrite original mastery.
const dataContext={window:{}};vm.runInNewContext(fs.readFileSync(path.join(root,'data.js'),'utf8'),dataContext);const practices=dataContext.window.ZHIYI_DATA.questions.find(q=>q.id==='books').practices;
for(let p=0;p<3;p++){q.practice=p;q.answer=String(practices[p].answer);t.checkAnswer();}
assert.equal(q.records['review-books'].status,'learning');for(const a of q.attempts)a.date='2026-10-10';
for(let p=0;p<3;p++){q.practice=p;q.answer=String(practices[p].answer);t.checkAnswer();}
assert.equal(q.records['review-books'].status,'mastered');q.practice=1;q.answer='-999';t.checkAnswer();assert.equal(q.records['review-books'].status,'learning');
t.openQuestion('books');q.practice=1;q.answer=String(practices[1].answer);t.checkAnswer();assert.equal(q.attempts.at(-1).assisted,true,'leaving/reentering cannot erase help');assert.equal(q.records['review-books'].status,'learning');
assert.equal(q.records.books,undefined,'variation attempts do not write original status');
assert.equal(t.allQuestions().some(x=>x.id==='books'),false,'examples do not inflate real library');
q.learning={lesson:'1.1',mode:'practice',practice:0,answer:'999999',usedHint:false};t.checkLesson();assert.equal(t.lessonErrors().length,1);const wrong=t.lessonErrors()[0];t.openQuestion(wrong.id);assert.equal(q.view,'lesson');assert.equal(q.learning.lesson,'1.1');assert.equal(q.learning.practice,0);
for(const [input,expected]of [['-1/2',-.5],['３／４',.75],['.5',.5],['−2',-2]])assert.equal(t.parseAnswer(input),expected);assert.ok(Number.isNaN(t.parseAnswer('1/0')));
b.setQuota(true);assert.equal(t.persist(),false);assert.ok(t.readinessCard().includes('缺少 AI 密钥'));
console.log('7 delivery flows passed: mastery regression, persistent assistance, real library, class errors, routed practice, fraction input, failed storage.');

const automatic=boot(),a=automatic.test;
a.state.drafts=['wrong','uncertain','correct','no_answer'].map((assessment,index)=>({id:'auto-'+index,serverId:'auto-'+index,title:assessment,problem:'题目',topic:'integer',status:'draft',serverStatus:assessment==='wrong'?'ready':'needs_review',assessment,tags:[]}));
a.state.drafts.push({id:'import',isImport:true,title:'导入记录',problem:'照片',status:'draft'});
assert.deepEqual(Array.from(a.allQuestions(),q=>q.id),['auto-0'],'only confirmed mistakes appear in the library');
assert.ok(!a.libraryHTML().includes('最近的自动整理'));
assert.ok(!a.captureHTML().includes('待核对'));
assert.ok(!a.realDetailHTML(a.state.drafts[1]).includes('corrected-problem'),'no parent transcription form');
console.log('Automatic library checks passed: no history panel, no manual confirmation, only confirmed mistakes.');
