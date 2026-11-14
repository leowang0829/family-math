# -*- coding: utf-8 -*-
from test_rapid import RapidTests,rapid,page,patch
class HomeworkAnswerTests(RapidTests):
 def test_fast_model_requires_the_answer_field_in_response_schema(self):
  with patch.object(self.app,'request_ai',return_value=page(rapid(1))) as request:
   self.collector.call(self.app.get_question(self.parent['id']))
  fmt=request.call_args.args[2]['response_format']
  self.assertEqual(fmt['type'],'json_schema');self.assertTrue(fmt['json_schema']['strict'])
  self.assertIn('v',fmt['json_schema']['schema']['properties']['questions']['items']['required'])
 def test_numeric_answer_uses_checked_expression_not_model_text(self):
  q=rapid(1);q['v']='999'
  parsed=self.collector.normalise(page(q))['questions'][0]
  self.assertEqual(parsed['quick_answer'],'4')
 def test_unresolved_answer_is_not_shown(self):
  q=rapid(1,'uncertain',c=.3);q['v']='猜测999'
  self.assertEqual(self.collector.normalise(page(q))['questions'][0]['quick_answer'],'')
 def test_text_answer_keeps_all_parts(self):
  q=rapid(1,'no_answer',w='');q.update(e='',s=None,v='（1）甲方案；（2）便宜10元。')
  self.assertEqual(self.collector.normalise(page(q))['questions'][0]['quick_answer'],q['v'])
 def test_one_numeric_subanswer_does_not_replace_all_parts_or_grade_whole_problem(self):
  q=rapid(25,'wrong',w='（1）20；（2）35')
  q.update(p='长200米宽140米。（1）最大间距多少？（2）最少几棵树？',e='(200+140)*2/20',s=34,v='（1）20米；（2）34棵。')
  value=self.collector.normalise(page(q))['questions'][0]
  self.assertEqual(value['quick_answer'],q['v']);self.assertIsNone(value['correct_number'])
  self.assertEqual(value['ai_assessment'],'wrong')
 def test_publish_keeps_correct_rows_and_wrong_links_without_extra_calls(self):
  a=rapid(1,'correct',w='4');a['v']='4';b=rapid(2);b['v']='4'
  with patch.object(self.app,'request_ai',return_value=page(a,b)),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  items=result['import_result']['items']
  self.assertEqual(len(items),2);self.assertEqual(items[0]['assessment'],'correct');self.assertEqual(items[0]['answer'],'4')
  self.assertEqual(items[0]['child_id'],'');self.assertTrue(items[1]['child_id'])
  self.assertEqual(len([q for q in self.app.list_questions() if q['parent_id']]),1)

 def test_finished_explanation_answer_is_returned_in_parent(self):
  import json
  with patch.object(self.app,'request_ai',return_value=page(rapid(1))),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  child=result['children'][0]['id']
  with self.app.db() as db:db.execute("UPDATE questions SET solution=?,status='ready' WHERE id=?",(json.dumps({'answer':'完整参考答案'}),child))
  self.assertEqual(self.app.dto(self.app.get_question(self.parent['id']))['children'][0]['answer'],'完整参考答案')
  with self.app.db() as db:db.execute("UPDATE questions SET status='needs_review' WHERE id=?",(child,))
  self.assertEqual(self.app.dto(self.app.get_question(self.parent['id']))['children'][0]['answer'],'')
 def test_archived_children_are_not_counted_as_collected_wrong_questions(self):
  with patch.object(self.app,'request_ai',return_value=page(rapid(1),rapid(2))),patch.object(self.app,'start_solve'):
   result=self.collector.collect(self.parent['id'])
  self.assertEqual(result['import_result']['wrong'],2)
  self.app.update_question(result['children'][0]['id'],{'archived':True})
  self.assertEqual(self.app.dto(self.app.get_question(self.parent['id']))['import_result']['wrong'],1)
  self.app.update_question(result['children'][0]['id'],{'archived':False})
  self.assertEqual(self.app.dto(self.app.get_question(self.parent['id']))['import_result']['wrong'],2)
