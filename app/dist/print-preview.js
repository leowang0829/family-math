(() => {
  'use strict';
  const pages=document.getElementById('pages'),summary=document.getElementById('summary'),message=document.getElementById('message'),issues=document.getElementById('issues'),printButton=document.getElementById('print-button');
  const id=location.pathname.match(/^\/print\/([a-f0-9]{32})$/)?.[1];
  const excluded=new Set();let diagramCounter=0,job=null,rendering=false,layoutReady=false,renderAgain=false;
  const el=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};
  const pxmm=96/25.4;
  async function request(path,body){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);try{const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:body===undefined?{}:{'Content-Type':'application/json','X-Math-Request':'1'},body:body===undefined?undefined:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(value.error||'无法读取打印预览');return value;}finally{clearTimeout(timer);}}
  function newPage(){
    const frame=el('div','page-frame'),sheet=el('article','sheet');sheet.style.setProperty('--question-font',document.getElementById('font-size').value+'pt');
    const head=el('header','sheet-header'),brand=el('div');brand.append(el('div','sheet-brand','爱数学'),el('h2','','错题复习单'));const meta=el('div','sheet-meta');meta.append(el('div','','姓名：____________'),el('div','','日期：____________'));head.append(brand,meta);
    const body=el('section','sheet-body'),footer=el('footer','sheet-footer');footer.append(el('span','','认真审题 · 独立作答'),el('span','page-number',''));
    sheet.append(head,body,footer);frame.append(sheet);pages.append(frame);return {frame,sheet,body};
  }
  function fits(page){return page.body.scrollHeight<=page.body.clientHeight+1;}
  function questionShell(number,continued=false){const node=el('section','print-question');node.append(el('h3','question-heading',`第 ${number} 题${continued?'（续）':''}`));const body=el('div','question-body');node.append(body);return {node,body};}
  function renderMath(node){if(typeof renderMathInElement!=='function'||!window.katex)throw Error('公式排版组件尚未加载，请刷新预览。');let error=null;renderMathInElement(node,{delimiters:[{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true},{left:'$$',right:'$$',display:true}],throwOnError:false,trust:false,strict:'error',errorCallback:()=>{error=true;},ignoredTags:['script','noscript','style','textarea','pre','code','option','svg']});if(error||node.querySelector('.katex-error'))throw Error('有公式无法清晰排版，请返回选题后重新生成预览。');}
  function diagramNode(diagram){
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${diagram.width} ${diagram.height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',diagram.description||'原题必要图形');svg.classList.add('question-diagram');
    const width=Math.min(178,100*diagram.width/diagram.height);svg.style.width=width+'mm';svg.style.maxHeight='100mm';
    const patternId='question-hatch-'+(++diagramCounter),defs=document.createElementNS(ns,'defs'),pattern=document.createElementNS(ns,'pattern');pattern.setAttribute('id',patternId);pattern.setAttribute('width','8');pattern.setAttribute('height','8');pattern.setAttribute('patternUnits','userSpaceOnUse');const hatch=document.createElementNS(ns,'path');hatch.setAttribute('d','M-2,2 L2,-2 M0,8 L8,0 M6,10 L10,6');hatch.setAttribute('stroke','#666');hatch.setAttribute('stroke-width','1');pattern.append(hatch);defs.append(pattern);svg.append(defs);
    const add=(tag,attributes,text)=>{const node=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attributes))node.setAttribute(key,String(value));if(text!==undefined)node.textContent=text;svg.append(node);};
    for(const p of diagram.primitives){const stroke={stroke:'#111','stroke-width':1.8,fill:({none:'none',light:'#dedede',dark:'#777',hatch:`url(#${patternId})`}[p.fill]||'none'),'stroke-linecap':'round','stroke-linejoin':'round',...(p.dashed?{'stroke-dasharray':'7 5'}:{})};
      if(p.kind==='line')add('line',{...stroke,x1:p.points[0].x,y1:p.points[0].y,x2:p.points[1].x,y2:p.points[1].y});
      else if(p.kind==='polyline'||p.kind==='polygon')add(p.kind,{...stroke,points:p.points.map(point=>`${point.x},${point.y}`).join(' ')});
      else if(p.kind==='rect')add('rect',{...stroke,x:p.x,y:p.y,width:p.width,height:p.height});
      else if(p.kind==='circle')add('circle',{...stroke,cx:p.x,cy:p.y,r:p.radius});
      else if(p.kind==='text')add('text',{x:p.x,y:p.y,fill:'#111','font-size':p.font_size,'dominant-baseline':'middle','text-anchor':'middle'},p.text);
    }return svg;
  }
  // Split only text outside formula delimiters; a fraction or equation is never cut in half.
  function textChunks(text){if(text.length<=240)return [text];const chunks=[];let current='',math=false;for(let i=0;i<text.length;i++){if(text.slice(i,i+2)==='\\('){math=true;current+='\\(';i++;continue;}if(text.slice(i,i+2)==='\\)'){math=false;current+='\\)';i++;continue;}current+=text[i];if(!math&&(/[。；\n]/.test(text[i])||current.length>=240)){if(current.trim())chunks.push(current.trim());current='';}}if(current.trim())chunks.push(current.trim());return chunks;}
  function questionUnits(question){const units=[];for(const block of question.blocks){const contents=block.kind==='text'?textChunks(block.content):[block.content];for(const content of contents){const node=el('div',block.kind==='math'?'question-block question-math':'question-block');if(block.kind==='math')katex.render(content,node,{displayMode:true,throwOnError:true,trust:false,strict:'error'});else{node.textContent=content;renderMath(node);}units.push(node);}}if(question.diagram.required)units.push(diagramNode(question.diagram));return units;}
  function answerSpace(mm){const node=el('div','answer-space');node.style.height=mm+'mm';node.setAttribute('aria-label','作答空间');for(let y=14;y<mm;y+=14){const rule=el('div','answer-rule');rule.style.top=y+'mm';node.append(rule);}return node;}
  function appendQuestion(question,number,page){
    const units=questionUnits(question),space=Math.min(125,Math.max(50,question.answer_space_mm)*Number(document.getElementById('answer-space').value));
    let shell=questionShell(number);for(const unit of units)shell.body.append(unit);shell.body.append(el('div','answer-label','作答区'),answerSpace(space));page.body.append(shell.node);
    if(fits(page))return page;
    shell.node.remove();
    if(page.body.childElementCount){page=newPage();page.body.append(shell.node);if(fits(page))return page;shell.node.remove();}
    // Very long questions continue at natural paragraph/formula/figure boundaries.
    shell=questionShell(number);page.body.append(shell.node);
    for(const unit of units){shell.body.append(unit);if(!fits(page)){unit.remove();if(!shell.body.childElementCount)throw Error(`第 ${number} 题的公式或图形超过可打印范围，请核对题目。`);page=newPage();shell=questionShell(number,true);page.body.append(shell.node);shell.body.append(unit);if(!fits(page))throw Error(`第 ${number} 题有无法分页的内容，请核对排版。`);}}
    const label=el('div','answer-label','作答区');shell.body.append(label);let blank=answerSpace(space);shell.body.append(blank);
    if(!fits(page)){blank.remove();const available=Math.floor((page.body.clientHeight-page.body.scrollHeight)/pxmm)-4;let remaining=space;if(available>=25){shell.body.append(answerSpace(Math.min(available,space)));remaining-=Math.min(available,space);}else label.remove();if(remaining>0){page=newPage();shell=questionShell(number,true);page.body.append(shell.node);shell.body.append(el('div','answer-label','继续作答'),answerSpace(remaining));}}
    if(!fits(page))throw Error(`第 ${number} 题作答区分页失败，请重新预览。`);return page;
  }
  function scalePreview(){const scale=Math.min(1,(document.documentElement.clientWidth-24)/(210*pxmm));for(const frame of pages.children){frame.style.width=(210*pxmm*scale)+'px';frame.style.height=(297*pxmm*scale)+'px';frame.firstElementChild.style.transform=`scale(${scale})`;}}
  function activeItems(){return job?job.items.filter(item=>!excluded.has(item.id)):[];}
  async function regenerate(button){button.disabled=true;try{const result=await request('/api/print-jobs',{ids:activeItems().map(item=>item.id)});location.assign(result.url);}catch(error){message.textContent=error.message;button.disabled=false;}}
  function showIssues(){issues.replaceChildren();if(activeItems().some(item=>item.state!=='ready')){const retry=el('button','','重新恢复题目');retry.addEventListener('click',()=>regenerate(retry));issues.append(retry);}for(const item of activeItems().filter(item=>item.state!=='ready')){const card=el('div','issue');card.append(el('h2','',`${item.title}需要核对`),el('p','',item.error||item.question?.review_note||'题目内容尚未确认。'));const remove=el('button','','暂不打印此题');remove.addEventListener('click',()=>{excluded.add(item.id);layout();});card.append(remove);issues.append(card);} }
  async function layout(){
    if(rendering){renderAgain=true;return;}rendering=true;layoutReady=false;printButton.disabled=true;
    try{pages.replaceChildren();showIssues();let page=newPage(),number=0;const items=activeItems();for(const item of items.filter(item=>item.state==='ready')){page=appendQuestion(item.question,++number,page);}if(!number){pages.replaceChildren();summary.textContent='没有可打印题目';message.textContent='请返回错题本选择完整的题目，或移除需要核对的项目。';return;}
      await document.fonts.ready;
      // KaTeX fonts load after formulas are created. Lay out once more with final metrics.
      pages.replaceChildren();page=newPage();number=0;for(const item of items.filter(item=>item.state==='ready'))page=appendQuestion(item.question,++number,page);
      const sheets=[...pages.querySelectorAll('.sheet')];for(const [index,sheet]of sheets.entries())sheet.querySelector('.page-number').textContent=`第 ${index+1} / ${sheets.length} 页`;
      const unresolved=items.some(item=>item.state!=='ready');summary.textContent=`${number} 道题 · ${sheets.length} 张 A4 · ${document.getElementById('font-size').value} 磅字号`;
      message.textContent=unresolved?'部分题目有内容无法确认。请先查看提示，或暂不打印这些题，再继续打印。':'已清除手写作答与批改痕迹。请浏览题目、公式和图形，确认后打印。';
      for(const sheet of sheets){if(sheet.querySelector('.sheet-body').scrollHeight>sheet.querySelector('.sheet-body').clientHeight+1)throw Error('页面内容超出纸张，已暂停打印，请重新预览。');}
      for(const body of pages.querySelectorAll('.question-body')){if(body.scrollWidth>body.clientWidth+1)throw Error('有公式或图形超出页面宽度，已暂停打印，请核对题目。');}
      scalePreview();layoutReady=!unresolved;printButton.disabled=!layoutReady;
    }catch(error){message.textContent=error.message||'打印排版失败，请重新生成预览。';message.classList.add('print-error');printButton.disabled=true;}
    finally{rendering=false;if(renderAgain){renderAgain=false;layout();}}
  }
  async function poll(){
    try{job=await request('/api/print-jobs/'+id);if(job.state==='preparing'){summary.textContent=`正在恢复原题 · ${job.completed} / ${job.total} 道`;message.textContent='正在清除手写答案、演算和批改痕迹，并核对公式与图形。完成后会自动显示 A4 预览。';setTimeout(poll,2000);return;}
      if(job.state==='interrupted')throw Error(job.error);await layout();
    }catch(error){message.textContent=error.name==='AbortError'?'连接 Mac 超时。请保持 Mac 开机后刷新预览。':error.message;summary.textContent='预览暂未完成';const retry=el('button','','重新生成预览');retry.addEventListener('click',async()=>{retry.disabled=true;try{if(!job)throw Error('请返回选题后重试。');const result=await request('/api/print-jobs',{ids:job.items.map(item=>item.id)});location.assign(result.url);}catch(e){message.textContent=e.message;retry.disabled=false;}});issues.replaceChildren(retry);}
  }
  printButton.addEventListener('click',()=>{if(layoutReady&&!rendering)window.print();});
  document.getElementById('font-size').addEventListener('change',layout);document.getElementById('answer-space').addEventListener('change',layout);
  window.addEventListener('resize',scalePreview);
  window.addEventListener('beforeprint',()=>{if(!layoutReady){pages.hidden=true;message.textContent='请等待题目恢复及排版完成后，再点击页面上的打印按钮。';}});
  window.addEventListener('afterprint',()=>{pages.hidden=false;scalePreview();});
  if(id)poll();else{summary.textContent='预览地址不正确';message.textContent='请从错题本勾选题目后打开预览。';}
})();
