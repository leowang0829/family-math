const assert=require('assert/strict'),quotes=require('../dist/daily-quotes.js');
assert.equal(quotes.quotes.length,300);assert.equal(new Set(quotes.quotes.map(q=>q.text)).size,300);
for(const q of quotes.quotes){assert(q.theme);assert.equal(q.kind,'modern-encouragement');assert.equal(q.source,'原创成长寄语');assert(q.text.length<=24);}
for(const profile of ['math']){
 const ids=[];for(let d=0;d<300;d++)ids.push(quotes.get(new Date(Date.UTC(2026,9,25+d)),profile).id);
 assert.equal(new Set(ids).size,300);assert.equal(quotes.get(new Date('2026-10-25T02:00:00Z'),profile).id,quotes.get(new Date('2026-10-25T15:59:59Z'),profile).id);
 assert.notEqual(quotes.get(new Date('2026-10-25T15:59:59Z'),profile).id,quotes.get(new Date('2026-10-25T16:00:00Z'),profile).id);
 assert.equal(quotes.get(new Date(Date.UTC(2026,9,25+300)),profile).id,ids[0]);
}
assert(!quotes.html(new Date('2026-10-25T02:00:00Z')).includes('figcaption'));assert(!quotes.html(new Date('2026-10-25T02:00:00Z')).includes('undefined'));assert(quotes.html(new Date('2026-10-25T02:00:00Z')).includes('每日一句'));
console.log('300 unique modern encouragements; no fabricated attribution; Singapore midnight; same-day stability; 300-day cycle; single-product daily quotes passed');
