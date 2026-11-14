"""Additive family diamond ledger. All amounts and redemptions are server-controlled."""
import copy,datetime,json,re,time,uuid
from pathlib import Path

DEFAULT_RULES={'daily':5,'milestones':{'3':5,'7':10,'14':20,'30':50},'points_per_diamond':1,'catalog':[{'id':'choice','title':'挑选今晚的家庭活动','cost':10},{'id':'game','title':'30分钟亲子游戏','cost':25},{'id':'weekend','title':'决定一次周末活动','cost':50}]}
DAY=re.compile(r'^\d{4}-\d{2}-\d{2}$')
def today():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()
def valid_day(day):
 try:return isinstance(day,str) and bool(DAY.fullmatch(day)) and datetime.date.fromisoformat(day).isoformat()==day
 except ValueError:return False
def earned_days(progress,day,examples=()):
 earned=set();daily={};failed=set()
 rows=[a for a in progress.get('attempts',[]) if isinstance(a,dict)]
 rows.sort(key=lambda a:(str(a.get('date','')),str(a.get('id','')).split('-')[0].zfill(16)))
 for a in rows:
  date=a.get('date');correct=a.get('correct')
  if not valid_day(date) or date>day or type(correct) is not bool:continue
  question=str(a.get('questionId',''))
  if question.startswith('original-') and len(question)>9 and question[9:] not in examples and correct:earned.add(date)
  variant=a.get('variantId')
  if isinstance(variant,str) and variant and a.get('dailyReviewDate')==date:daily.setdefault(date,set()).add(variant)
  key=('bank:'+str(variant)) if variant else ('lesson:'+question+':'+str(a.get('practice'))) if question.startswith('lesson-') else None
  if key:
   if correct and key in failed:earned.add(date)
   if not correct:failed.add(key)
 records=progress.get('records',{})
 for date,ids in daily.items():
  plan=records.get('daily-review-'+date,{}).get('items')
  planned=[x.get('variantId') for x in plan if isinstance(x,dict) and isinstance(x.get('variantId'),str)] if isinstance(plan,list) else None
  if (len(planned)==5 and len(set(planned))==5 and all(i in ids for i in planned)) if planned is not None else len(ids)>=5:earned.add(date)
 return sorted(earned)
def validate_rules(value):
 if not isinstance(value,dict) or set(value)!=set(DEFAULT_RULES):raise ValueError('奖励规则不完整')
 if type(value['daily']) is not int or not 1<=value['daily']<=50:raise ValueError('每日奖励请输入1至50钻')
 if type(value['points_per_diamond']) is not int or not 1<=value['points_per_diamond']<=100:raise ValueError('兑换比例请输入1至100')
 if not isinstance(value['milestones'],dict) or set(value['milestones'])!={'3','7','14','30'}:raise ValueError('成长奖励不完整')
 if any(type(n) is not int or not 0<=n<=500 for n in value['milestones'].values()):raise ValueError('成长奖励请输入0至500钻')
 catalog=value['catalog']
 if not isinstance(catalog,list) or not 1<=len(catalog)<=12:raise ValueError('请设置1至12项家庭奖励')
 ids=set()
 for item in catalog:
  if not isinstance(item,dict) or set(item)!={'id','title','cost'} or not isinstance(item['id'],str) or not re.fullmatch('[a-z0-9_-]{1,40}',item['id']) or item['id'] in ids:raise ValueError('奖励项目不正确')
  ids.add(item['id'])
  if not isinstance(item['title'],str) or not 1<=len(item['title'].strip())<=60 or type(item['cost']) is not int or not 1<=item['cost']<=10000:raise ValueError('奖励名称或钻石数量不正确')
 return copy.deepcopy(value)

class Rewards:
 def __init__(self,app,profile):
  self.app,self.profile=app,profile
  try:self.examples={q['id'] for q in json.loads((Path(__file__).parent/'dist/data.js').read_text().split('=',1)[1].strip().rstrip(';'))['questions']}
  except (OSError,ValueError,KeyError,TypeError):self.examples=set()
  with app.db() as db:db.executescript('''
   CREATE TABLE IF NOT EXISTS family_reward_settings(profile TEXT PRIMARY KEY,value TEXT NOT NULL,started_day TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS family_reward_events(id TEXT PRIMARY KEY,profile TEXT NOT NULL,source TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,amount INTEGER NOT NULL,created REAL NOT NULL,detail TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS family_reward_requests(id TEXT PRIMARY KEY,profile TEXT NOT NULL,reward_id TEXT NOT NULL,title TEXT NOT NULL,diamonds INTEGER NOT NULL,points INTEGER NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,decided REAL NOT NULL DEFAULT 0);
  ''')
 def _sync(self,db,day):
  row=db.execute('SELECT value FROM progress WHERE profile=?',(self.profile,)).fetchone();progress=json.loads(row['value']) if row else {'records':{},'attempts':[]}
  days=earned_days(progress,day,self.examples)
  saved=db.execute('SELECT * FROM family_reward_settings WHERE profile=?',(self.profile,)).fetchone()
  if not saved:
   db.execute('INSERT INTO family_reward_settings VALUES(?,?,?)',(self.profile,json.dumps(DEFAULT_RULES,ensure_ascii=False),day));rules=copy.deepcopy(DEFAULT_RULES);started=day
  else:rules=json.loads(saved['value']);started=saved['started_day']
  def grant(source,kind,amount,detail):
   db.execute('INSERT OR IGNORE INTO family_reward_events VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,self.profile,self.profile+':'+source,kind,amount,time.time(),json.dumps(detail,ensure_ascii=False)))
  for date in days:
   if date>=started:grant('day:'+date,'daily',rules['daily'],{'date':date,'title':'每日成长打卡'})
  for goal,amount in rules['milestones'].items():
   n=int(goal)
   if len(days)>=n and days[n-1]>=started:grant('badge:'+goal,'badge',amount,{'date':days[n-1],'title':'累计'+goal+'天成长奖励'})
  return rules,started,days
 def _view(self,db,rules,started,days):
  events=[dict(r) for r in db.execute('SELECT * FROM family_reward_events WHERE profile=? ORDER BY created DESC,id',(self.profile,))]
  requests=[dict(r) for r in db.execute('SELECT * FROM family_reward_requests WHERE profile=? ORDER BY created DESC,id',(self.profile,))]
  for e in events:e['detail']=json.loads(e['detail'])
  balance=sum(e['amount'] for e in events);reserved=sum(r['diamonds'] for r in requests if r['status']=='pending')
  return {'profile':self.profile,'balance':balance,'available':balance-reserved,'reserved':reserved,'earned':sum(max(0,e['amount']) for e in events),'spent':-sum(min(0,e['amount']) for e in events),'rules':rules,'started_day':started,'checked_days':days,'events':events[:100],'requests':requests[:100]}
 def summary(self,day=None):
  day=day or today()
  with self.app.db() as db:
   db.execute('BEGIN IMMEDIATE');rules,started,days=self._sync(db,day);return self._view(db,rules,started,days)
 def request(self,body):
  ident=body.get('request_id');reward_id=body.get('reward_id')
  if not isinstance(ident,str) or not re.fullmatch('[a-zA-Z0-9_-]{12,80}',ident):raise ValueError('兑换请求编号不正确')
  with self.app.db() as db:
   db.execute('BEGIN IMMEDIATE');rules,started,days=self._sync(db,today())
   prior=db.execute('SELECT * FROM family_reward_requests WHERE id=?',(ident,)).fetchone()
   if prior:
    if prior['profile']!=self.profile or prior['reward_id']!=reward_id:raise ValueError('兑换请求编号已被使用')
    return self._view(db,rules,started,days)
   reward=next((r for r in rules['catalog'] if r['id']==reward_id),None)
   if not reward:raise ValueError('这个家庭奖励已调整，请刷新后再选')
   view=self._view(db,rules,started,days)
   if reward['cost']>view['available']:raise ValueError('可用钻石还不够，再积累一点就能兑换啦')
   db.execute('INSERT INTO family_reward_requests VALUES(?,?,?,?,?,?,?,?,?)',(ident,self.profile,reward_id,reward['title'],reward['cost'],reward['cost']*rules['points_per_diamond'],'pending',time.time(),0))
   return self._view(db,rules,started,days)
 def decide(self,body):
  action=body.get('decision')
  if action not in ['approved','rejected']:raise ValueError('请选择确认或退回兑换')
  with self.app.db() as db:
   db.execute('BEGIN IMMEDIATE');rules,started,days=self._sync(db,today())
   request=db.execute('SELECT * FROM family_reward_requests WHERE id=? AND profile=?',(body.get('request_id'),self.profile)).fetchone()
   if not request:raise ValueError('兑换申请不存在')
   if request['status']!='pending':return self._view(db,rules,started,days)
   if action=='approved':
    db.execute('INSERT OR IGNORE INTO family_reward_events VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,self.profile,self.profile+':redeem:'+request['id'],'redeem',-request['diamonds'],time.time(),json.dumps({'title':request['title'],'family_points':request['points']},ensure_ascii=False)))
   db.execute('UPDATE family_reward_requests SET status=?,decided=? WHERE id=?',(action,time.time(),request['id']))
   return self._view(db,rules,started,days)
 def settings(self,body):
  rules=validate_rules(body.get('rules'))
  with self.app.db() as db:
   db.execute('BEGIN IMMEDIATE');old,started,days=self._sync(db,today())
   db.execute('UPDATE family_reward_settings SET value=? WHERE profile=?',(json.dumps(rules,ensure_ascii=False),self.profile))
   return self._view(db,rules,started,days)
