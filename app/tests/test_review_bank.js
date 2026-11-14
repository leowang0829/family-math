const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const dist=path.resolve(__dirname,'../dist'),bank=require(path.join(dist,'review-bank.js')),ctx={window:{}};vm.createContext(ctx);
for(const f of ['data.js','curriculum.js'])vm.runInContext(fs.readFileSync(path.join(dist,f),'utf8'),ctx);
const course=Object.values(ctx.window).find(x=>x&&x.lessons),profile='math';let total=0;
for(const lesson of course.lessons){const rows=bank.pool(profile,lesson.id),a=bank.select(profile,lesson.id,[],0,5),b=bank.select(profile,lesson.id,[],1,5);assert(rows.length>=10);assert.equal(new Set(rows.map(q=>q.text+JSON.stringify(q.diagram))).size,rows.length);assert(!b.some(q=>a.some(x=>x.id===q.id)));assert(!bank.select(profile,lesson.id,a.map(q=>({variantId:q.id})),0,5).some(q=>a.some(x=>x.id===q.id)));for(const q of rows){assert.equal(bank.check(q,String(q.answer)),true);assert.equal(bank.check(q,''),null);if(q.type==='choice'){assert(q.options.includes(q.answer));assert.equal(new Set(q.options).size,q.options.length);assert.equal(bank.check(q,q.options.find(x=>x!==q.answer)),false);}else assert.equal(bank.check(q,String(q.answer+1)),false);}total+=rows.length;}
console.log(profile+': '+total+' parameterized questions, deduplication, unseen-first selection, grading and blank guard passed');

