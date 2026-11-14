/* Preserve loaded images and stable controls during background status updates. */
(function(root){
 'use strict';
 const key=node=>node.nodeType===1?(node.id?'id:'+node.id:node.getAttribute('data-stable-key')?'key:'+node.getAttribute('data-stable-key'):null):null;
 const compatible=(a,b)=>a&&a.nodeType===b.nodeType&&(a.nodeType!==1||(a.tagName===b.tagName&&key(a)===key(b)));
 function patch(old,next){
  if(old.nodeType!==1){if(old.nodeValue!==next.nodeValue)old.nodeValue=next.nodeValue;return;}
  const keepDraftSource=old.tagName==='IMG'&&old.id==='draft-photo'&&old.getAttribute('data-photo-id')===next.getAttribute('data-photo-id')&&!next.hasAttribute('src');
  for(const attr of Array.from(old.attributes))if(!next.hasAttribute(attr.name)&&!(keepDraftSource&&attr.name==='src'))old.removeAttribute(attr.name);
  const focusedValue=old.ownerDocument.activeElement===old&&['INPUT','TEXTAREA'].includes(old.tagName);
  for(const attr of Array.from(next.attributes))if(!(focusedValue&&attr.name==='value')&&old.getAttribute(attr.name)!==attr.value)old.setAttribute(attr.name,attr.value);
  children(old,next);
  if(old.tagName==='INPUT'){
   if(old.type==='checkbox'||old.type==='radio'){if(old.checked!==next.checked)old.checked=next.checked;}
   else if(old.ownerDocument.activeElement!==old&&old.value!==next.value)old.value=next.value;
  }else if((old.tagName==='TEXTAREA'||old.tagName==='SELECT')&&old.ownerDocument.activeElement!==old&&old.value!==next.value)old.value=next.value;
 }
 function children(parent,next){
  const old=Array.from(parent.childNodes),used=new Set();
  Array.from(next.childNodes).forEach((desired,index)=>{
   const at=parent.childNodes[index];let chosen;
   if(compatible(at,desired)&&!used.has(at))chosen=at;
   else if(key(desired))chosen=old.find(n=>!used.has(n)&&compatible(n,desired));
   if(!chosen)chosen=desired.cloneNode(true);
   else patch(chosen,desired);
   used.add(chosen);if(parent.childNodes[index]!==chosen)parent.insertBefore(chosen,parent.childNodes[index]||null);
  });
  for(const node of Array.from(parent.childNodes))if(!used.has(node))parent.removeChild(node);
 }
 function render(container,html){const template=container.ownerDocument.createElement('template');template.innerHTML=html;children(container,template.content);}
 const api={render};if(typeof module==='object'&&module.exports)module.exports=api;else root.MathStableRender=api;
})(typeof window==='object'?window:globalThis);
