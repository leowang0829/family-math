import copy,json,time,unittest
from unittest.mock import patch
import test_server
from test_auto_collect import scanned
server=test_server.server

class TeacherCollectionPolicyTests(unittest.TestCase):
    def checked(self,q):return server.validate_scan({'questions':[q],'note':''})['questions'][0]
    def test_teacher_cross_survives_correct_answer_and_is_idempotent(self):
        q=scanned(1,'correct');q['teacher_mark']='wrong'
        result=self.checked(q)
        self.assertEqual(result['assessment'],'wrong');self.assertEqual(result['ai_assessment'],'correct');self.assertEqual(result['collection_source'],'teacher')
        self.assertEqual(self.checked(copy.deepcopy(result)),result)
    def test_teacher_cross_kept_with_no_answer_low_confidence_or_bad_calculation(self):
        for key in ['blank','uncertain','bad_expression']:
            q=scanned(1);q['teacher_mark']='wrong'
            if key=='blank':q['student_work']='';q['student_number']=None
            if key=='uncertain':q['confidence']=.3
            if key=='bad_expression':q['check_expression']='1/0'
            result=self.checked(q);self.assertEqual(result['assessment'],'wrong');self.assertEqual(result['collection_source'],'teacher')
    def test_unmarked_or_ambiguous_mark_uses_ai_judgement(self):
        for mark in ['none','unclear','correct']:
            q=scanned(1);q['teacher_mark']=mark
            self.assertEqual(self.checked(q)['collection_source'],'ai')
        q=scanned(1,'correct');self.assertEqual(self.checked(q)['assessment'],'correct')
        q=scanned(1,confidence=.4);self.assertEqual(self.checked(q)['assessment'],'uncertain')
    def test_both_sources_preserved(self):
        q=scanned(1);q['teacher_mark']='wrong';self.assertEqual(self.checked(q)['collection_source'],'both')
    def test_later_review_cannot_remove_extracted_teacher_cross(self):
        marked=scanned(1,'uncertain',.5);marked['teacher_mark']='wrong'
        review=scanned(1,'correct')
        result=server.merge_teacher_marks({'questions':[review],'note':''},{'questions':[marked],'note':''})
        self.assertEqual(result['questions'][0]['assessment'],'wrong');self.assertEqual(result['questions'][0]['ai_assessment'],'correct')
    def test_marked_question_omitted_by_review_is_retained(self):
        marked=scanned(1);marked['teacher_mark']='wrong'
        result=server.merge_teacher_marks({'questions':[],'note':''},{'questions':[marked],'note':''})
        self.assertEqual(len(result['questions']),1);self.assertEqual(result['questions'][0]['teacher_mark'],'wrong')

    def test_review_failure_still_keeps_extracted_teacher_cross(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            app=server.App(directory,'127.0.0.1',0)
            try:
                app.save_config({'provider':'qwen','key':'fixture-only','model':'qwen3.8-max'})
                config=json.loads(app.config_path.read_text());config['routing']='hybrid-v1';app.config_path.write_text(json.dumps(config))
                parent=app.save_question({'image':test_server.IMAGE,'client_id':'fallback-page'})
                teacher=scanned(1,'uncertain',.4);teacher['teacher_mark']='wrong'
                unmarked=scanned(2,'uncertain',.4)
                with patch.object(app,'call_scan',side_effect=[{'questions':[teacher,unmarked],'note':''},ValueError('AI连接超时')]):
                    result,_,cached=app.hybrid_scan(app.get_question(parent['id']))
                self.assertEqual(result['questions'][0]['assessment'],'wrong');self.assertEqual(result['questions'][1]['assessment'],'uncertain')
                self.assertFalse(cached);self.assertIn('复核暂未完成',result['note']);self.assertEqual(list((Path(directory)/'recognition-cache').glob('*.json')),[])
            finally:
                app.stopping.set();app.pool.shutdown(wait=True);app.practice_pool.shutdown(wait=True)

class TeacherCollectionFlowTests(test_server.HTTPTests):
    def run_scan(self,parent,scan):
        with patch.object(self.app,'call_scan',return_value=scan),patch.object(self.app,'call_ai',return_value=server.validate_solution(test_server.solution())):
            self.app.start_solve(parent['id'],auto_collect=True)
            for _ in range(300):
                if not self.app.active:break
                time.sleep(.01)
            self.assertFalse(self.app.active)
    def test_teacher_and_ai_union_collects_preserves_provenance_and_deduplicates(self):
        self.pair();parent=self.save();self.app.save_config({'key':'fixture-only'})
        teacher=scanned(1,'correct');teacher['teacher_mark']='wrong'
        ai=scanned(2)
        correct=scanned(3,'correct')
        scan={'questions':[teacher,ai,correct],'note':'fixture'}
        self.run_scan(parent,copy.deepcopy(scan))
        children=[r for r in self.app.list_questions() if r['parent_id']==parent['id']]
        self.assertEqual(len(children),2)
        self.assertEqual({r['collection_source'] for r in children},{'teacher','ai'})
        teacher_child=next(r for r in children if r['teacher_mark']=='wrong');saved_id=teacher_child['id']
        self.assertEqual(teacher_child['ai_assessment'],'correct')
        self.assertEqual(self.app.dto(self.app.get_question(parent['id']))['import_result']['wrong'],2)
        self.run_scan(parent,copy.deepcopy(scan));self.assertEqual(len(self.app.list_questions()),3)
        revised={'questions':[scanned(1,'correct'),ai,correct],'note':'later review omitted teacher flag'}
        self.run_scan(parent,copy.deepcopy(revised))
        self.assertEqual(self.app.get_question(saved_id)['assessment'],'wrong');self.assertEqual(self.app.get_question(saved_id)['teacher_mark'],'wrong')
    def test_teacher_cross_stays_visible_when_explanation_cannot_read_photo(self):
        self.pair();parent=self.save();self.app.save_config({'key':'fixture-only'})
        q=scanned(1,'uncertain',.4);q['teacher_mark']='wrong'
        value=test_server.solution();value.update(needs_review=True,review_note='原照片部分模糊')
        with patch.object(self.app,'call_scan',return_value={'questions':[q],'note':''}),patch.object(self.app,'call_ai',return_value=server.validate_solution(value)):
            self.app.start_solve(parent['id'],auto_collect=True)
            for _ in range(300):
                if not self.app.active:break
                time.sleep(.01)
        children=[r for r in self.app.list_questions() if r['parent_id']==parent['id']]
        self.assertEqual(len(children),1);self.assertEqual(children[0]['assessment'],'wrong');self.assertEqual(children[0]['status'],'needs_review')
    def test_new_policy_has_distinct_recognition_cache_and_no_automatic_bulk_replay(self):
        self.assertIn('COLLECTION_POLICY',__import__('pathlib').Path(server.__file__).read_text())
        self.assertEqual(self.app.health()['collection_policy'],'teacher-or-ai-v1')

for name in test_server.HTTPTests.__dict__:
    if name.startswith('test_'):setattr(TeacherCollectionFlowTests,name,None)
