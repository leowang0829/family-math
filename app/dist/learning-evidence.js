(function(root){
  'use strict';
  function learningEvidence(attempts,count){
    const valid=attempts.filter(a=>Number.isInteger(a.practice)&&a.practice>=0&&a.practice<count&&typeof a.date==='string');
    const independent=valid.filter(a=>a.correct===true&&a.assisted===false);
    const stamp=a=>Number(String(a.id).split('-')[0])||Date.parse(a.date)||0;
    const latest=Array.from({length:count},(_,index)=>valid.filter(a=>a.practice===index).sort((a,b)=>stamp(a)-stamp(b)).slice(-1)[0]);
    return {independent:new Set(independent.map(a=>a.practice)).size,days:new Set(independent.map(a=>a.date)).size,
      mastered:Array.from({length:count},(_,index)=>new Set(independent.filter(a=>a.practice===index).map(a=>a.date)).size>=2).every(Boolean)&&latest.every(a=>a?.correct===true&&a.assisted===false)};
  }
  learningEvidence.recommend=function(lessons,chapter,focusId,evidence,practiced){const current=lessons.filter(l=>l.chapter===chapter),repeat=current.find(l=>evidence(l.id).due&&evidence(l.id).started),focus=lessons.find(l=>l.id===focusId);return repeat||(focus&&!practiced(focus.id)?focus:null)||current.find(l=>!practiced(l.id))||focus||current.find(l=>!evidence(l.id).mastered)||current[0]||lessons[0];};
  root.MathLearningEvidence=learningEvidence;
  if(typeof module!=='undefined'&&module.exports)module.exports=learningEvidence;
})(typeof window!=='undefined'?window:globalThis);
