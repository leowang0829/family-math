import copy,json,tempfile,unittest,importlib.util
from pathlib import Path
import test_server
spec=importlib.util.spec_from_file_location('cards',Path(__file__).resolve().parents[1]/'answer_cards.py');cards=importlib.util.module_from_spec(spec);spec.loader.exec_module(cards)
IDENT='a'*32

def part(ident='p1',answer='23/20',number=23/20,expression='3/4+2/5',kind='number'):
 return {'id':ident,'label':'第'+ident[1:]+'问','kind':kind,'answer':answer,'alternatives':[],'number':number,'unit':'','check_expression':expression}

class FakeApp:
 def __init__(self,root):
  self.data=Path(root);self.calls=[];self.response={'needs_review':False,'review_note':'','parts':[part(),part('p2','11/24',11/24,'5/6-3/8')]}
  self.row={'id':IDENT,'archived':0,'status':'ready','problem':'(1)3/4+2/5=__；(2)5/6-3/8=__','solution':json.dumps({'problem':'(1)3/4+2/5=__；(2)5/6-3/8=__','answer':'23/20；11/24','answer_number':None,'steps':[],'practices':[{'text':'(1)3/4+2/5=__；(2)5/6-3/8=__','answer':1.15,'unit':'','solution':'旧版只给了第一问答案','check_expression':'3/4+2/5'}]})}
 def get_question(self,ident):
  if ident!=IDENT:raise KeyError(ident)
  return self.row
 def stage_config(self,stage):return {'provider':'qwen','model':'qwen3.8-flash','key':'fixture-not-a-real-key','workspace':''}
 def request_ai(self,*args):self.calls.append(args);return copy.deepcopy(self.response)

class AnswerCardsTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.app=FakeApp(self.temp.name);self.service=cards.AnswerCards(self.app,test_server.server.arithmetic,{});self.body={'scope':'original','question_id':IDENT,'index':0}
 def tearDown(self):self.temp.cleanup()
 def test_complete_card_and_text_only_flash_cached(self):
  result=self.service.prepare(self.body);self.assertEqual(len(result['card']['parts']),2);self.assertFalse(result['cache_hit']);self.assertTrue(self.service.prepare(self.body)['cache_hit']);self.assertEqual(len(self.app.calls),1)
  config,url,body,timeout=self.app.calls[0];self.assertEqual(config['_stage'],'answer_card');self.assertEqual(body['model'],'qwen3.8-flash');self.assertNotIn('image_url',json.dumps(body));self.assertEqual(timeout,18)
 def test_all_blanks_required_and_second_wrong_cannot_pass_whole(self):
  card=self.service.prepare(self.body)['card'];request={**self.body,'card_id':card['id'],'answers':{'p1':'1.15','p2':''}}
  with self.assertRaises(ValueError):self.service.grade(request)
  request['answers']['p2']='1/2';result=self.service.grade(request);self.assertFalse(result['correct']);self.assertEqual(result['correct_parts'],1)
  request['answers']['p2']='11/24';result=self.service.grade(request);self.assertTrue(result['correct']);self.assertEqual(result['total_parts'],2);self.assertEqual(len(self.app.calls),1)
 def test_multi_practice_old_single_reference_not_accepted(self):
  result=self.service.prepare({**self.body,'scope':'practice'});self.assertEqual(len(result['card']['parts']),2);self.assertEqual(len(self.app.calls),1)
 def test_omitted_part_rejected(self):
  self.app.response['parts']=self.app.response['parts'][:1]
  with self.assertRaisesRegex(ValueError,'覆盖所有'):self.service.prepare(self.body)
 def test_inconsistent_numeric_key_rejected(self):
  self.app.response['parts'][1]['number']=.5
  with self.assertRaisesRegex(ValueError,'验算'):self.service.prepare(self.body)
 def test_duplicates_and_incomplete_source_rejected(self):
  self.app.response['parts'][1]['id']='p1'
  with self.assertRaisesRegex(ValueError,'题号'):self.service.prepare(self.body)
  self.app.response={'needs_review':True,'review_note':'图形条件不完整','parts':[]}
  with self.assertRaisesRegex(ValueError,'图形'):self.service.prepare(self.body)
 def test_source_change_invalidates_card_and_does_not_modify_original(self):
  before=self.app.row.copy();card=self.service.prepare(self.body)['card'];self.assertEqual(self.app.row,before)
  self.app.row['solution']=self.app.row['solution'].replace('3/4+2/5','1/4+2/5');new=self.service.prepare(self.body)['card'];self.assertNotEqual(card['id'],new['id'])
  with self.assertRaisesRegex(ValueError,'题目已更新'):self.service.grade({**self.body,'card_id':card['id'],'answers':{'p1':'1','p2':'2'}})
 def test_text_equivalence_and_indeterminate_does_not_count_as_wrong(self):
  self.app.response['parts']=[part('p1','直角',None,'','text'),part('p2','因为两边相等',None,'','explanation')]
  card=self.service.prepare(self.body)['card'];self.app.response={'results':[{'id':'p1','correct':True,'feedback':'意思正确。'},{'id':'p2','correct':None,'feedback':'还需要说明理由。'}]}
  result=self.service.grade({**self.body,'card_id':card['id'],'answers':{'p1':'90度的角','p2':'看起来一样'}});self.assertIsNone(result['correct']);self.assertFalse(result['confirmed']);self.assertEqual(result['correct_parts'],1)
 def test_single_registered_curriculum_practice_offline_no_ai(self):
  service=cards.AnswerCards(self.app,test_server.server.arithmetic,{'1.1':{'id':'1.1','practices':[{'text':'计算2+3','answer':5,'solution':'2+3=5','unit':'个'}]}})
  result=service.prepare({'scope':'lesson','lesson_id':'1.1','index':0});self.assertEqual(result['card']['parts'][0]['number'],5);self.assertFalse(self.app.calls)
 def test_8_blanks_are_8_distinct_parts(self):
  s=json.loads(self.app.row['solution']);s['problem']='填写8个结果：'+'；'.join('__' for _ in range(8));self.app.row['solution']=json.dumps(s)
  self.app.response['parts']=[part('p'+str(i+1),'1',1,'1') for i in range(8)];self.assertEqual(len(self.service.prepare(self.body)['card']['parts']),8)
 def test_number_formats(self):
  for value,expected in [('３／４',.75),('1又3/4',1.75),('-1 3/4',-1.75),('75%',.75),('3/0',None),('2+3',None),('NaN',None)]:self.assertEqual(cards.number_value(value),expected)
 def test_expected_part_detection(self):
  for problem,n in [('(1)2+3；(2)4+5',2),('数轴上这个数在__和__之间',2),('谁最快？谁最慢？',2),('求周长和面积',2),('比较1/2与2/3哪个大',1)]:self.assertEqual(cards.required_parts(problem),n)

class NumericRigorTests(unittest.TestCase):
 def test_text_normalization_preserves_ratio_and_decimal(self):
  self.assertNotEqual(cards.normalized('2:3'),cards.normalized('23'))
  self.assertNotEqual(cards.normalized('1.5'),cards.normalized('15'))
  self.assertEqual(cards.number_value('３⁄４'),.75)
 def test_large_numbers_are_not_marked_correct_just_because_relatively_close(self):
  with tempfile.TemporaryDirectory() as td:
   app=FakeApp(td);s=json.loads(app.row['solution']);s.update(problem='计算1000000000+0',answer='1000000000',answer_number=1000000000,check_expression='1000000000');app.row['solution']=json.dumps(s)
   service=cards.AnswerCards(app,test_server.server.arithmetic,{})
   body={'scope':'original','question_id':IDENT};card=service.prepare(body)['card']
   result=service.grade({**body,'card_id':card['id'],'answers':{'p1':'1000000001'}});self.assertFalse(result['correct'])

class AnswerCardHTTPTests(unittest.TestCase):
 setUp=test_server.HTTPTests.setUp
 tearDown=test_server.HTTPTests.tearDown
 request=test_server.HTTPTests.request
 pair=test_server.HTTPTests.pair
 save=test_server.HTTPTests.save
 def test_paired_routes_and_single_value_grade(self):
  for route in ['/api/answer-cards','/api/answer-cards/grade','/api/questions/restore']:self.assertEqual(self.request(route,{})[0],401)
  self.pair();q=self.save();solution=test_server.solution()
  with self.app.db() as db:db.execute("UPDATE questions SET status='ready',problem=?,solution=? WHERE id=?",(solution['problem'],json.dumps(solution),q['id']))
  body={'question_id':q['id'],'scope':'original','index':0}
  status,_,raw=self.request('/api/answer-cards',body);self.assertEqual(status,200);card=json.loads(raw)['card'];self.assertEqual(len(card['parts']),1)
  status,_,raw=self.request('/api/answer-cards/grade',{**body,'card_id':card['id'],'answers':{'p1':'42'}});self.assertEqual(status,200);self.assertTrue(json.loads(raw)['correct'])
  with self.app.db() as db:db.execute('UPDATE questions SET archived=1 WHERE id=?',(q['id'],))
  self.assertEqual(self.request('/api/answer-cards',body)[0],400)
  status,_,raw=self.request('/api/questions/restore',{'ids':[q['id'],q['id']]});self.assertEqual(status,200);self.assertEqual(json.loads(raw)['restored_count'],1)
