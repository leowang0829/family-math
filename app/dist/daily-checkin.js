/* Daily encouragement derived from existing learning evidence. No network or model calls. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.MathDailyCheckin=api;})(typeof window==='object'?window:globalThis,function(){
 'use strict';
 const milestones=[3,7,14,30];
 const validDay=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&!Number.isNaN(Date.parse(value+'T12:00:00+08:00'))&&new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Singapore'}).format(new Date(value+'T12:00:00+08:00'))===value;
 function shift(day,amount){const date=new Date(day+'T12:00:00+08:00');date.setUTCDate(date.getUTCDate()+amount);return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Singapore'}).format(date);}
 const key=day=>'daily-checkin-v1-'+day;
 function evaluate({attempts=[],records={},day,exampleIds=[]}={}){
  if(!validDay(day))throw Error('Invalid check-in day');
  const days=new Map(),daily=new Map(),failed=new Set(),examples=new Set(exampleIds);
  const add=(date,reason)=>{if(validDay(date)&&date<=day){if(!days.has(date))days.set(date,new Set());days.get(date).add(reason);}};
  const rows=attempts.filter(a=>a&&typeof a==='object').map((a,i)=>({a,i,t:Number(String(a.id||'').split('-')[0])||0})).sort((x,y)=>String(x.a.date||'').localeCompare(String(y.a.date||''))||x.t-y.t||x.i-y.i);
  for(const {a} of rows){
   if(!validDay(a.date)||a.date>day||typeof a.correct!=='boolean')continue;
   if(a.variantId&&validDay(a.dailyReviewDate)&&a.dailyReviewDate===a.date){
    if(!daily.has(a.date))daily.set(a.date,new Set());daily.get(a.date).add(a.variantId);
   }
   const original=typeof a.questionId==='string'&&a.questionId.startsWith('original-')&&!examples.has(a.questionId.slice(9));
   if(original&&a.correct)add(a.date,'original');
   const practiceKey=a.variantId?'bank:'+a.variantId:typeof a.questionId==='string'&&a.questionId.startsWith('lesson-')?'lesson:'+a.questionId+':'+a.practice:null;
   if(practiceKey){if(a.correct&&failed.has(practiceKey))add(a.date,'original');if(!a.correct)failed.add(practiceKey);}
  }
  for(const [date,ids] of daily){
   const planned=records['daily-review-'+date]?.items?.map(q=>q.variantId);
   if(planned?(planned.length===5&&new Set(planned).size===5&&planned.every(id=>ids.has(id))):ids.size>=5)add(date,'daily-five');
  }
  // Existing ledgers are additive; never erase earned days when older attempts are archived/exported.
  for(const [id,r] of Object.entries(records))if(id.startsWith('daily-checkin-v1-')&&r?.version===1&&id===key(r.date))add(r.date,'saved');
  const earned=[...days.keys()].sort(),total=earned.length,checked=days.has(day);
  let cursor=checked?day:shift(day,-1),streak=0;
  while(days.has(cursor)){streak++;cursor=shift(cursor,-1);}
  const badges=milestones.map((goal,i)=>({goal,earned:total>=goal,title:['小小起步','一周成长','坚持发芽','闪亮一个月'][i]})),next=milestones.find(goal=>goal>total)||null;
  const week=Array.from({length:7},(_,i)=>{const date=shift(day,i-6);return {date,today:date===day,earned:days.has(date),label:date===day?'今':new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Singapore',weekday:'narrow'}).format(new Date(date+'T12:00:00+08:00'))};});
  return {day,checked,total,streak,earned,badges,next,remaining:next?next-total:0,week,reasons:[...(days.get(day)||[])]};
 }
 function award(options){const summary=evaluate(options);if(!summary.checked||options.records?.[key(summary.day)])return {summary,record:null};return {summary,record:{version:1,date:summary.day,reasons:summary.reasons.filter(x=>x!=='saved'),updatedAt:options.now??Date.now()}};}
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const badgeMark=goal=>goal===3?'✦':goal===7?'✿':goal===14?'❋':'★';
 function html(summary,profile='math'){
  const mango=false,name='小蘑菇',last=summary.next?milestones[milestones.indexOf(summary.next)-1]||0:30,progress=summary.next?Math.min(100,(summary.total-last)/(summary.next-last)*100):100;
  return `<section class="daily-checkin ${mango?'mango':'mushroom'} ${summary.checked?'is-earned':''}" aria-label="每日成长打卡"><div class="checkin-main"><div class="checkin-character"><span class="checkin-character-halo"></span><img src="assets/icon.svg" alt="${name}"><span class="checkin-character-star">✦</span></div><div class="checkin-copy"><div class="checkin-eyebrow">每天一点点 · 都算进步</div><h2>${summary.checked?'今天的成长，记下啦！':'今天，也向前一小步。'}</h2><p>${summary.checked?'认真完成了一次学习，'+name+'为你开心。':'完成每日 5 题，或订正答对 1 道错题，就会自动打卡。'}</p><span class="checkin-state">${summary.checked?'✓ 今日已打卡':'今日待点亮'}</span></div><div class="checkin-counts"><div><strong>${summary.streak}<small>天</small></strong><span>连续打卡</span></div><div><strong>${summary.total}<small>天</small></strong><span>累计成长</span></div></div></div><div class="checkin-bottom"><div class="checkin-week"><div class="checkin-small-label">最近 7 天</div><div class="checkin-week-days">${summary.week.map(d=>`<div class="checkin-day ${d.earned?'earned':''} ${d.today?'today':''}" aria-label="${esc(d.date)} ${d.earned?'已打卡':'未打卡'}"><span>${d.label}</span><i>${d.earned?'✓':'·'}</i></div>`).join('')}</div></div><div class="checkin-collection"><div class="checkin-small-label">我的成长徽章 <span>${summary.next?'再积累 '+summary.remaining+' 天，点亮下一枚':'30 天徽章已点亮，继续积累每一天'}</span></div><div class="checkin-badges">${summary.badges.map(b=>`<div class="checkin-badge ${b.earned?'earned':''}" title="${esc(b.title)} · 累计${b.goal}天${b.earned?'已点亮':''}"><span>${badgeMark(b.goal)}</span><small>${b.goal} 天</small></div>`).join('')}</div><div class="checkin-meter" role="progressbar" aria-label="下一枚成长徽章" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(progress)}"><i style="width:${progress}%"></i></div></div></div></section>`;
 }
 function celebrate(summary,profile='math',document=globalThis.document){
  if(!document?.body)return;
  document.getElementById('checkin-celebration')?.remove();
  const host=document.createElement('div');host.id='checkin-celebration';host.className='checkin-celebration '+(false?'mango':'mushroom');host.setAttribute('role','status');host.setAttribute('aria-live','polite');
  const badge=milestones.includes(summary.total)?`点亮 ${summary.total} 天成长徽章`:`累计成长 ${summary.total} 天`;
  host.innerHTML=`<div class="checkin-celebration-card"><span class="checkin-spark spark-a">✦</span><span class="checkin-spark spark-b">✧</span><span class="checkin-spark spark-c">✦</span><img src="assets/icon.svg" alt=""><div><span class="checkin-celebration-label">今日打卡成功</span><strong>又进步了一点，真棒！</strong><p>${badge}</p>${summary.diamondAward?`<span class="diamond-gain">✧ +${summary.diamondAward} 钻已到账</span>`:''}</div></div>`;
  document.body.appendChild(host);setTimeout(()=>host.remove(),2200);
 }
 return Object.freeze({evaluate,award,key,html,celebrate,shift});
});
