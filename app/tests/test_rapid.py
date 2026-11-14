import copy,io,json,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_server
server=test_server.server

def rapid(n,a='wrong',t='none',w='24÷6=5',c=.99):
 return {'n':str(n),'p':'24个苹果平均分给6人，每人几个？','w':w,'a':a,'t':t,'c':c,'e':'24/6','s':5 if a=='wrong' else 4 if a=='correct' else None,'k':'integer','r':'核对计算结果','b':[0,0,1000,300]}
def page(*qs):return {'questions':list(qs),'note':''}
class RapidTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=server.App(self.tmp.name,'127.0.0.1',0);self.app.save_config({'provider':'qwen','key':'fixture-only','model':'qwen3.8-max'})
  c=json.loads(self.app.config_path.read_text());c['routing']='hybrid-v1';self.app.config_path.write_text(json.dumps(c));self.parent=self.app.save_question({'image':test_server.IMAGE,'client_id':'rapid-fixture'});self.collector=self.app.rapid_collector()
 def tearDown(self):
  self.app.stopping.set();self.app.scan_pool.shutdown(wait=True);self.app.pool.shutdown(wait=True);self.app.practice_pool.shutdown(wait=True);self.tmp.cleanup()
 def test_fast_call_uses_max_without_thinking_and_recovery_bounded(self):
  with patch.object(self.app,'request_ai',return_value=page(rapid(1))) as request:
   self.collector.call(self.app.get_question(self.parent['id']));body=request.call_args.args[2];self.assertEqual(body['model'],'qwen3.8-max');self.assertFalse(body['enable_thinking']);self.assertEqual(body['reasoning_effort'],'none')
   self.collector.call(self.app.get_question(self.parent['id']),'recover',targets=[]);body=request.call_args.args[2];self.assertTrue(body['enable_thinking']);self.assertLessEqual(body['thinking_budget'],1536);self.assertIn('局部',body['messages'][0]['content'])
 def test_collects_teacher_own_wrong_and_blank_separately_without_inventing_wrong(self):
  value=page(rapid(1,'correct','wrong',w='24÷6=4'),rapid(2),rapid(3,'no_answer',w='不会做'),rapid(4,'correct',w='24÷6=4'))
  with patch.object(self.app,'request_ai',return_value=value),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  children=[x for x in self.app.list_questions() if x['parent_id']]
  self.assertEqual(len(children),3);self.assertEqual({c['collection_source'] for c in children},{'teacher','ai','unanswered'})
  self.assertEqual(next(c for c in children if c['collection_source']=='unanswered')['assessment'],'no_answer');self.assertEqual(result['import_result']['wrong'],2);self.assertEqual(result['import_result']['learning'],1)
 def test_known_results_published_before_uncertain_review_finishes(self):
  entered=threading.Event();release=threading.Event()
  def call(config,*args):
   if config['_stage']=='rapid_recover':entered.set();release.wait(3);return page(rapid(2,'no_answer',w=''))
   return page(rapid(1),rapid(2,'uncertain',c=.3))
  with patch.object(self.app,'request_ai',side_effect=call),patch.object(self.app,'start_solve'):
   thread=threading.Thread(target=self.collector.collect,args=(self.parent['id'],));thread.start();self.assertTrue(entered.wait(2))
   p=self.app.dto(self.app.get_question(self.parent['id']));self.assertEqual(p['status'],'processing');self.assertEqual(p['phase'],'refining');self.assertEqual(p['import_result']['wrong'],1);self.assertEqual(len(p['children']),2)
   ids={c['id'] for c in p['children']};release.set();thread.join(3);self.assertFalse(thread.is_alive());p=self.app.dto(self.app.get_question(self.parent['id']));self.assertEqual(p['status'],'collected');self.assertEqual(p['import_result']['learning'],1);self.assertEqual(ids,{c['id'] for c in p['children']})
 def test_cache_reuse_and_reprocessing_preserve_ids(self):
  with patch.object(self.app,'request_ai',return_value=page(rapid(1))),patch.object(self.app,'start_solve'):
   self.collector.collect(self.parent['id']);ids={q['id'] for q in self.app.list_questions()}
  with patch.object(self.app,'request_ai') as call,patch.object(self.app,'start_solve'):
   result=self.app.rapid_collector().collect(self.parent['id']);call.assert_not_called();self.assertTrue(result['import_result']['cache_hit']);self.assertEqual(ids,{q['id'] for q in self.app.list_questions()})
 def test_bad_expression_and_low_confidence_never_pretend_correct(self):
  q=rapid(1,'correct');q['e']='1/0';r=self.collector.normalise(page(q))['questions'][0];self.assertEqual(r['collection_source'],'recognition_pending')
  q=rapid(1,'wrong',c=.2);self.assertEqual(self.collector.normalise(page(q))['questions'][0]['assessment'],'uncertain')
 def test_review_failure_retains_unresolved_photo_as_learning_item(self):
  with patch.object(self.app,'request_ai',side_effect=lambda config,*args:(_ for _ in ()).throw(ValueError('AI 响应超时')) if config['_stage']=='rapid_recover' else page(rapid(1,'uncertain',c=.2))),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  self.assertEqual(result['status'],'collected');self.assertEqual(result['import_result']['pending'],1);self.assertEqual(len(result['children']),1);self.assertEqual(list((self.app.data/'recognition-cache').glob('*.json')),[])
 def test_missing_formula_is_never_labelled_as_merely_unattempted(self):
  q=rapid(8,'no_answer',w='');q['p']='动脑筋：在下面算式中的□里填上合适的数字，使算式成立。';q['r']='算式未拍入画面';q['e']='';q['s']=None
  result=self.collector.normalise(page(q))['questions'][0];self.assertEqual(result['collection_source'],'recognition_pending');self.assertFalse(self.collector.needs_recovery(result))
  fragment=copy.deepcopy(q);fragment['p']='C. 8支钢笔一共160元 D. 20支钢笔一共160元';fragment['r']='题干不完整';parsed=self.collector.normalise(page(fragment))['questions'][0];self.assertEqual(parsed['collection_source'],'recognition_pending');self.assertFalse(self.collector.needs_recovery(parsed))
  with patch.object(self.app,'request_ai',return_value=page(q)) as call,patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
   self.assertEqual(call.call_count,2);self.assertEqual(result['import_result']['pending'],1);self.assertEqual(result['import_result']['learning'],0);self.assertEqual(list((self.app.data/'recognition-cache').glob('*.json')),[])
 def test_api_permission_error_does_not_retry_or_spend_on_other_models(self):
  with patch.object(self.app,'request_ai',side_effect=ValueError('AI 额度不足')) as call:
   with self.assertRaises(ValueError):self.collector.collect(self.parent['id'])
   self.assertEqual(call.call_count,2)
 def test_collection_queue_separate_from_explanation_queue(self):
  with patch.object(self.app.scan_pool,'submit') as scan,patch.object(self.app.pool,'submit') as solve:
   self.app.start_solve(self.parent['id'],auto_collect=True);scan.assert_called_once();solve.assert_not_called()
 def test_auditor_restores_teacher_cross_hidden_under_correction(self):
  def call(config,*args):
   return page(rapid(1,'correct','wrong' if config['_stage']=='rapid_audit' else 'correct',w='24÷6=4'))
  with patch.object(self.app,'request_ai',side_effect=call),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  children=[q for q in self.app.list_questions() if q['parent_id']];self.assertEqual(len(children),1);self.assertEqual(children[0]['collection_source'],'teacher');self.assertEqual(children[0]['ai_assessment'],'correct');self.assertEqual(result['import_result']['wrong'],1)
 def test_cutoff_question_from_inventory_is_retained_when_grader_omits_it(self):
  def call(config,*args):
   if config['_stage']=='rapid_audit':return page(rapid(1,'correct'),rapid(2,'uncertain',w='题干被照片截断',c=.2))
   if config['_stage']=='rapid_recover':return page(rapid(2,'uncertain',w='题干被照片截断',c=.2))
   return page(rapid(1,'correct'))
  with patch.object(self.app,'request_ai',side_effect=call),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  self.assertEqual(result['import_result']['total'],2);self.assertEqual(result['import_result']['pending'],1);self.assertEqual(len(result['children']),1)
 def test_fast_child_explanation_keeps_max_but_avoids_thinking_until_repair(self):
  row=dict(self.app.get_question(self.parent['id']));row.update(parent_id='page',collection_policy='rapid-v3',collection_source='unanswered')
  value=test_server.solution();value['practices']=[]
  with patch.object(self.app,'request_ai',side_effect=lambda *args:copy.deepcopy(value)) as call:
   self.app.call_ai(row,include_practices=False);self.assertFalse(call.call_args.args[2]['enable_thinking']);self.assertEqual(call.call_args.args[2]['model'],'qwen3.8-max')
   self.app.call_ai(row,repair=True,mode='careful',include_practices=False);self.assertTrue(call.call_args.args[2]['enable_thinking'])
if __name__=='__main__':unittest.main()
