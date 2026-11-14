const assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),vm=require('vm');
const source=fs.readFileSync(path.resolve(__dirname,'../dist/app.js'),'utf8');
const action=source.match(/case 'select-print-visible':(\{.*?render\(\);break;\})/)[0];
const clearAction=source.match(/case 'clear-library-selection':(\{.*?render\(\);break;\})/)[0];
for(const count of [51,125,250]){
 const questions=Array.from({length:count},(_,i)=>({id:'q'+i,serverId:'q'+i,title:'test'+i,problem:'1+1',topic:i%2?'fraction':'integer',tags:[]}));
 const state={librarySelection:new Set(),filter:'all',topicFilter:'all',search:''};let renders=0;let clearedKey='';
 const context=vm.createContext({state,allQuestions:()=>questions,record:()=>({status:'pending'}),render:()=>renders++,sessionStorage:{removeItem:key=>clearedKey=key}});
 const click=()=>vm.runInContext("switch('select-print-visible'){"+action+'}',context);
 click();assert.equal(state.librarySelection.size,count);assert(state.librarySelection.has('q'+(count-1)),'last selected item must not be truncated');click();assert.equal(state.librarySelection.size,count,'select all is idempotent');
 const clear=()=>vm.runInContext("switch('clear-library-selection'){"+clearAction+'}',context);clear();assert.equal(state.librarySelection.size,0);assert.equal(clearedKey,'math-print-selection');
 state.topicFilter='fraction';click();assert.equal(state.librarySelection.size,questions.filter(q=>q.topic==='fraction').length);assert([...state.librarySelection].every(id=>questions.find(q=>q.id===id).topic==='fraction'));
 state.topicFilter='integer';click();assert.equal(state.librarySelection.size,count,'selecting another filter retains prior selection');clear();assert.equal(state.librarySelection.size,0,'cancel clears visible and hidden selected questions');
 state.librarySelection.clear();state.topicFilter='all';state.search='test12';click();assert.equal(state.librarySelection.size,questions.filter(q=>q.title.includes('test12')).length);assert.equal(renders,7);
}
console.log('Select all: 51 / 125 / 250 questions, last item retained, idempotent select, explicit cancel, hidden selection and print-return cache clearing passed.');
