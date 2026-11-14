# -*- coding: utf-8 -*-
import copy,datetime,importlib.util,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import test_server as fixtures
spec=importlib.util.spec_from_file_location('reward_module',Path(__file__).resolve().parents[1]/'rewards.py');reward=importlib.util.module_from_spec(spec);spec.loader.exec_module(reward)
DAY='2026-11-10'
def progress(count=6,today=False):
 day=datetime.date.fromisoformat(DAY);attempts=[{'id':str(i)+'-past','questionId':'original-q'+str(i),'date':(day-datetime.timedelta(days=count-i)).isoformat(),'correct':True} for i in range(count)]
 if today:attempts.append({'id':'100-today','questionId':'original-today','date':DAY,'correct':True})
 return {'attempts':attempts,'records':{'keep':{'status':'mastered','updatedAt':1}}}
class RewardsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=fixtures.server.App(self.tmp.name,'127.0.0.1',0);self.profile=self.app.health(False)['profile'];self.service=reward.Rewards(self.app,self.profile);self.clock=patch.object(reward,'today',return_value=DAY);self.clock.start();self.write(progress())
 def tearDown(self):
  self.clock.stop();self.app.pool.shutdown(wait=True);self.app.practice_pool.shutdown(wait=True);self.app.scan_pool.shutdown(wait=True);self.tmp.cleanup()
 def write(self,value):
  with self.app.db() as db:db.execute('INSERT INTO progress VALUES(?,?) ON CONFLICT(profile) DO UPDATE SET value=excluded.value',(self.profile,json.dumps(value)))
 def earn(self):self.service.summary();self.write(progress(today=True));return self.service.summary()
 def test_old_history_is_preserved_without_retroactive_credit(self):
  before=json.dumps(progress(),sort_keys=True);result=self.service.summary();self.assertEqual(result['available'],0);self.assertEqual(len(result['checked_days']),6)
  with self.app.db() as db:current=json.loads(db.execute('SELECT value FROM progress WHERE profile=?',(self.profile,)).fetchone()[0])
  self.assertEqual(json.dumps(current,sort_keys=True),before)
 def test_daily_and_badge_are_each_once_even_with_concurrent_refresh(self):
  self.assertEqual(self.earn()['available'],15);errors=[]
  def run():
   try:self.assertEqual(self.service.summary()['available'],15)
   except Exception as e:errors.append(str(e))
  workers=[threading.Thread(target=run) for _ in range(8)]
  for w in workers:w.start()
  for w in workers:w.join()
  self.assertEqual(errors,[]);self.assertEqual(len(self.service.summary()['events']),2)
 def test_pending_reservation_approval_idempotency_and_server_price(self):
  self.earn();body={'request_id':'request-test-001','reward_id':'choice','cost':0,'amount':99999};view=self.service.request(body);self.assertEqual((view['available'],view['reserved']),(5,10));self.assertEqual(self.service.request(body)['reserved'],10)
  with self.assertRaises(ValueError):self.service.request({'request_id':'request-test-002','reward_id':'choice'})
  result=self.service.decide({'request_id':body['request_id'],'decision':'approved'});self.assertEqual((result['balance'],result['available'],result['spent']),(5,5,10))
  again=self.service.decide({'request_id':body['request_id'],'decision':'approved'});self.assertEqual(len(again['events']),3)
  self.assertEqual(self.service.decide({'request_id':body['request_id'],'decision':'rejected'})['balance'],5)
 def test_rejection_releases_reserved_points(self):
  self.earn();self.service.request({'request_id':'request-test-003','reward_id':'choice'});result=self.service.decide({'request_id':'request-test-003','decision':'rejected'});self.assertEqual((result['available'],result['reserved'],result['spent']),(15,0,0))
 def test_rule_updates_do_not_reprice_earned_credit_or_pending_request(self):
  self.earn();self.service.request({'request_id':'request-test-004','reward_id':'choice'});rules=copy.deepcopy(reward.DEFAULT_RULES);rules['daily']=20;rules['points_per_diamond']=3;rules['catalog'][0]['cost']=5
  result=self.service.settings({'rules':rules});self.assertEqual(result['balance'],15);self.assertEqual(result['requests'][0]['diamonds'],10);self.assertEqual(result['requests'][0]['points'],10);self.assertEqual(self.service.summary()['balance'],15)
 def test_daily_five_requires_unique_complete_plan(self):
  p={'records':{'daily-review-'+DAY:{'items':[{'variantId':'v'+str(i)} for i in range(5)]}},'attempts':[{'id':str(i),'date':DAY,'dailyReviewDate':DAY,'variantId':'v'+str(i),'correct':i!=0} for i in range(5)]}
  self.assertEqual(reward.earned_days(p,DAY),[DAY]);p['attempts'][-1]=p['attempts'][0];self.assertEqual(reward.earned_days(p,DAY),[])
 def test_invalid_rules_rejected(self):
  for field,value in [('daily',-5),('points_per_diamond',0),('daily',True)]:
   data=copy.deepcopy(reward.DEFAULT_RULES);data[field]=value
   with self.assertRaises(ValueError):reward.validate_rules(data)
 def test_reenabled_badge_does_not_retroactively_grant_previously_disabled_reward(self):
  self.service.summary();rules=copy.deepcopy(reward.DEFAULT_RULES);rules['milestones']['7']=0;self.service.settings({'rules':rules});self.write(progress(today=True));self.assertEqual(self.service.summary()['balance'],5)
  rules['milestones']['7']=10;self.service.settings({'rules':rules});self.assertEqual(self.service.summary()['balance'],5)
class RewardsHTTPTests(unittest.TestCase):
 setUp=fixtures.HTTPTests.setUp;tearDown=fixtures.HTTPTests.tearDown;request=fixtures.HTTPTests.request
 def pair(self):
  code,headers,body=self.request('/api/pair',{'code':self.app.pair_code});self.assertEqual(code,200);self.cookie=headers['Set-Cookie'].split(';')[0]
 def test_wallet_needs_login_and_parent_actions_require_password(self):
  self.assertEqual(self.request('/api/rewards')[0],401);self.pair();self.assertEqual(self.request('/api/rewards')[0],200)
  status,_,body=self.request('/api/rewards/settings',{'rules':reward.DEFAULT_RULES,'parent_password':'wrong'});self.assertEqual(status,403)
  rules=copy.deepcopy(reward.DEFAULT_RULES);rules['daily']=7
  self.assertEqual(self.request('/api/rewards/settings',{'rules':rules,'parent_password':self.app.pair_code})[0],200)
  self.assertEqual(json.loads(self.request('/api/rewards')[2])['rules']['daily'],7)
 def test_progress_save_is_additive_and_returns_wallet_without_models(self):
  self.pair();code,_,body=self.request('/api/progress',{'progress':progress(today=True)});self.assertEqual(code,200);self.assertIn('rewards',json.loads(body))
  code,_,raw=self.request('/api/progress');self.assertEqual(json.loads(raw)['progress']['records']['keep']['status'],'mastered')
