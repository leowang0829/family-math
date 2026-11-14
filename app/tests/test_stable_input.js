const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={module:{exports:{}},Set,Array};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist/stable-render.js'),'utf8').replace('const api={render};','const api={render,patch};'),context);
function input(value,attribute,document){
 const attrs=new Map([['id','library-search'],['type','search'],['value',attribute]]),writes=[];
 return {nodeType:1,tagName:'INPUT',id:'library-search',type:'search',ownerDocument:document,value,childNodes:[],writes,
  get attributes(){return [...attrs].map(([name,value])=>({name,value}));},getAttribute:k=>attrs.get(k)??null,hasAttribute:k=>attrs.has(k),setAttribute(k,v){writes.push(k);attrs.set(k,v);},removeAttribute:k=>attrs.delete(k)};
}
const document={},old=input('fen','旧条件',document),next=input('分数','分数',document);document.activeElement=old;
context.module.exports.patch(old,next);assert.equal(old.value,'fen');assert.equal(old.getAttribute('value'),'旧条件');assert(!old.writes.includes('value'),'IME composition must not receive a default-value mutation');
document.activeElement=null;context.module.exports.patch(old,next);assert.equal(old.value,'分数');assert.equal(old.getAttribute('value'),'分数');
console.log('Stable DOM preserves composing input value/defaultValue and updates unfocused controls.');
