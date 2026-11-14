import copy,json,time,unittest
from unittest.mock import patch
import test_server
server=test_server.server

def scanned(number,assessment='wrong',confidence=.99):
    return {'number':str(number),'title':'第'+str(number)+'题','problem':'24个苹果平均分给6人，每人几个？','student_work':'24÷6=5','topic':'integer','lesson_id':'1.1','assessment':assessment,'teacher_mark':'none','confidence':confidence,'reason':'计算24÷6应为4，原作答5。','correct_number':4,'student_number':5 if assessment=='wrong' else 4,'check_expression':'24/6'}

class ScanValidation(unittest.TestCase):
    def test_local_comparison_overrules_inconsistent_assessment(self):
        q=scanned(1);q['student_number']=4
        self.assertEqual(server.validate_scan({'questions':[q],'note':''})['questions'][0]['assessment'],'correct')
    def test_low_confidence_and_bad_calculation_are_not_asserted_wrong(self):
        q=scanned(1,confidence=.5)
        self.assertEqual(server.validate_scan({'questions':[q],'note':''})['questions'][0]['assessment'],'uncertain')
        q=scanned(1);q['check_expression']='100/2'
        self.assertEqual(server.validate_scan({'questions':[q],'note':''})['questions'][0]['assessment'],'uncertain')
    def test_no_visible_work_cannot_be_auto_wrong(self):
        q=scanned(1);q['student_work']='';q['student_number']=None
        self.assertEqual(server.validate_scan({'questions':[q],'note':''})['questions'][0]['assessment'],'no_answer')
    def test_invalid_shapes_and_hostile_expression_are_rejected_or_pending(self):
        with self.assertRaises(ValueError):server.validate_scan({'questions':[{}],'note':''})
        q=scanned(1);q['check_expression']="__import__('os').system('true')"
        self.assertEqual(server.validate_scan({'questions':[q],'note':''})['questions'][0]['assessment'],'uncertain')

class AutoCollectTests(test_server.HTTPTests):
    def test_upload_starts_whole_page_scan_and_retry_does_not_duplicate_job(self):
        self.pair();self.app.save_config({'key':'fixture-only'})
        body={'client_id':'auto-upload-fixture','image':test_server.IMAGE,'auto_collect':True}
        with patch.object(self.app.pool,'submit') as submit:
            status,_,raw=self.request('/api/questions',body)
            item=json.loads(raw)['question'];self.assertEqual(status,201)
            self.assertEqual(item['status'],'processing');self.assertTrue(item['is_import'])
            self.assertEqual(submit.call_args.args[0],self.app.scan_and_collect)
            status,_,raw=self.request('/api/questions',body)
            self.assertEqual(json.loads(raw)['question']['id'],item['id']);self.assertEqual(submit.call_count,1)
    def test_upload_without_key_saves_photo_and_reports_needs_setup(self):
        self.pair()
        with patch.object(self.app.pool,'submit') as submit:
            status,_,raw=self.request('/api/questions',{'client_id':'no-key-auto','image':test_server.IMAGE,'auto_collect':True})
            self.assertEqual(status,201);self.assertEqual(json.loads(raw)['question']['status'],'needs_setup');submit.assert_not_called()
        self.assertEqual(len(list(self.app.photos.iterdir())),1)
    def test_auto_upload_rejects_invalid_automatic_setting_before_save(self):
        self.pair()
        self.assertEqual(self.request('/api/questions',{'image':test_server.IMAGE,'auto_collect':'yes'})[0],400)
        self.assertEqual(len(self.app.list_questions()),0)
    def test_mixed_page_rechecks_uncertain_and_collects_only_confirmed_wrong(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        uncertain=scanned(3,confidence=.4);uncertain['correct_number']=None;uncertain['student_number']=None
        scan=server.validate_scan({'questions':[scanned(1),scanned(2,'correct'),uncertain],'note':'测试整页三题'})
        core=server.validate_solution(test_server.solution())
        with patch.object(self.app,'call_scan',return_value=scan),patch.object(self.app,'call_ai',return_value=core):
            self.assertEqual(self.request('/api/questions/'+q['id']+'/solve',{'auto_collect':True})[0],202)
            for _ in range(200):
                if not self.app.active:break
                time.sleep(.01)
            parent=self.app.dto(self.app.get_question(q['id']));self.assertTrue(parent['is_import']);self.assertEqual(parent['status'],'collected')
            self.assertEqual(parent['import_result']['total'],3);self.assertEqual(parent['import_result']['correct'],1);self.assertEqual(parent['import_result']['wrong'],1);self.assertEqual(parent['import_result']['pending'],0);self.assertEqual(parent['import_result']['unrecognized'],1);self.assertEqual(parent['import_result']['rechecks'],1)
            children=[r for r in self.app.list_questions() if r['parent_id']==q['id']]
            self.assertEqual(len(children),1);self.assertEqual({c['assessment'] for c in children},{'wrong'})
            self.assertEqual(next(c for c in children if c['assessment']=='wrong')['status'],'ready')
            self.assertEqual(next(c for c in children if c['assessment']=='wrong')['target_number'],'1')
            self.assertEqual(len(list(self.app.photos.iterdir())),1,'children share the private original photo')
            self.app.start_solve(q['id'],auto_collect=True)
            for _ in range(200):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(len(self.app.list_questions()),2,'rescan must not duplicate children')
        self.app.update_question(q['id'],{'archived':True});self.assertTrue(all(r['archived'] for r in self.app.list_questions()))
        self.app.update_question(q['id'],{'archived':False});self.assertTrue(all(not r['archived'] for r in self.app.list_questions()))
    def tearDown(self):
        self.app.stopping.set()
        super().tearDown()

    def test_second_ai_pass_resolves_wrong_and_correct_without_manual_items(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        first={'questions':[scanned(1,'uncertain',.5),scanned(2,'uncertain',.5)],'note':''}
        second={'questions':[scanned(1),scanned(2,'correct')],'note':'AI已复核'}
        with patch.object(self.app,'call_scan',side_effect=[first,second]) as model,patch.object(self.app,'call_ai',return_value=server.validate_solution(test_server.solution())):
            self.app.start_solve(q['id'],auto_collect=True)
            for _ in range(250):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(model.call_count,2)
            self.assertEqual(model.call_args.kwargs['mode'],'careful')
            children=[r for r in self.app.list_questions() if r['parent_id']==q['id']]
            self.assertEqual(len(children),1);self.assertEqual(children[0]['assessment'],'wrong');self.assertEqual(children[0]['status'],'ready')

    def test_old_pending_question_reuses_id_when_ai_confirms_error(self):
        self.pair();parent=self.save();self.app.save_config({'key':'fixture-only'})
        with self.app.db() as db:
            db.execute("UPDATE questions SET is_import=1,status='collected' WHERE id=?",(parent['id'],))
        old=self.app.save_question({'client_id':'legacy-child','image':test_server.IMAGE,'problem':'旧识别文字'})
        with self.app.db() as db:
            db.execute("UPDATE questions SET parent_id=?,target_number='1',assessment='uncertain',status='needs_review' WHERE id=?",(parent['id'],old['id']))
        with patch.object(self.app,'call_scan',return_value={'questions':[scanned(1)],'note':''}),patch.object(self.app,'call_ai',return_value=server.validate_solution(test_server.solution())):
            self.app.resume_automatic_review()
            for _ in range(250):
                if self.app.get_question(old['id'])['status']=='ready':break
                time.sleep(.01)
            self.app.stopping.set()
            self.assertEqual(self.app.get_question(old['id'])['assessment'],'wrong')
            self.assertEqual(self.app.get_question(old['id'])['status'],'ready')
            self.assertEqual(len(self.app.list_questions()),2,'existing learning records must retain their ID')

    def test_unreadable_solution_gets_an_automatic_image_recheck(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        unclear=test_server.solution();unclear.update(needs_review=True,review_note='分母不清楚')
        with patch.object(self.app,'call_ai',side_effect=[server.validate_solution(unclear),server.validate_solution(test_server.solution())]) as model:
            self.app.start_solve(q['id'])
            for _ in range(250):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(self.app.get_question(q['id'])['status'],'ready')
            self.assertTrue(model.call_args.kwargs['vision_review'])

    def test_all_correct_page_does_not_create_wrong_questions(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        with patch.object(self.app,'call_scan',return_value=server.validate_scan({'questions':[scanned(1,'correct')],'note':'全部正确'})),patch.object(self.app,'call_ai') as core:
            self.app.start_solve(q['id'],auto_collect=True)
            for _ in range(200):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(len(self.app.list_questions()),1);core.assert_not_called()
            self.assertEqual(self.app.dto(self.app.get_question(q['id']))['import_result']['wrong'],0)

for name in test_server.HTTPTests.__dict__:
    if name.startswith('test_'):setattr(AutoCollectTests,name,None)
