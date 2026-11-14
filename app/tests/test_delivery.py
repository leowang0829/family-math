import io
import json
from pathlib import Path
import sqlite3
import time
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from test_server import HTTPTests, solution, server

spec=__import__('importlib.util',fromlist=['']).spec_from_file_location('restore',Path(__file__).resolve().parents[1]/'restore_backup.py')
restore=__import__('importlib.util',fromlist=['']).module_from_spec(spec);spec.loader.exec_module(restore)

class DeliveryTests(HTTPTests):
    # Inherited HTTP contract checks are deliberately rerun against each fresh DB.
    def test_archive_restore_and_manual_curriculum_correction(self):
        self.pair();q=self.save();url='/api/questions/'+q['id']+'/update'
        status,_,raw=self.request(url,{'archived':True,'title':'整除的练习','lesson_id':'1.2'})
        self.assertEqual(status,200);item=json.loads(raw)['question'];self.assertTrue(item['archived']);self.assertEqual(item['lesson_id'],'1.2')
        self.assertEqual(self.request('/api/questions/'+q['id']+'/photo')[0],200)
        self.request(url,{'archived':False});self.assertFalse(self.app.get_question(q['id'])['archived'])
        self.assertEqual(self.request(url,{'lesson_id':'non-existent'})[0],400)
        with self.app.db() as db:db.execute("UPDATE questions SET status='processing' WHERE id=?",(q['id'],))
        self.assertEqual(self.request(url,{'archived':True})[0],200)
        self.assertEqual(self.request(url,{'title':'正在解析时修改'})[0],400)
        self.assertEqual(self.request('/api/questions/'+q['id']+'/solve',{})[0],400)
    def test_complete_backup_is_private_excludes_credentials_and_restores(self):
        self.pair();q=self.save();self.app.save_config({'key':'not-real-private-secret'})
        self.request('/api/progress',{'progress':{'records':{'lesson-1.1':{'updatedAt':42}},'attempts':[{'id':'saved-attempt','correct':False}]}})
        self.assertEqual(self.request('/api/setup/backup',{},headers={'X-Setup-Nonce':'wrong'})[0],403)
        status,_,raw=self.request('/api/setup/backup',{},headers={'X-Setup-Nonce':self.app.setup_nonce});self.assertEqual(status,200)
        status,_,raw=self.request(json.loads(raw)['url']);self.assertEqual(status,200)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names=archive.namelist();self.assertNotIn('ai-config.json',names);self.assertNotIn('pairing-config.json',names)
            self.assertEqual(sum(n.startswith('photos/') for n in names),1)
            file=Path(self.temp.name)/'download.zip';file.write_bytes(raw)
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder);(dest/'ai-config.json').write_text('{"key":"keep-existing"}')
            previous=restore.restore(file,dest);self.assertTrue(previous.exists())
            with sqlite3.connect(str(dest/'math.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT id FROM questions').fetchone()[0],q['id'])
                value=json.loads(db.execute('SELECT value FROM progress').fetchone()[0]);self.assertEqual(value['attempts'][0]['id'],'saved-attempt')
            self.assertEqual(json.loads((dest/'ai-config.json').read_text())['key'],'keep-existing')
            photo=next((dest/'photos').iterdir());self.assertEqual(photo.read_bytes(),next(self.app.photos.iterdir()).read_bytes())
            restore.restore(file,dest);self.assertTrue(any(p.name=='math.sqlite3' for p in (dest/'before-restore').rglob('*')))
    def test_malicious_restore_cannot_overwrite_outside_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('backup.json','{"format":"math-backup-v1"}');z.writestr('math.sqlite3','bad');z.writestr('../escape','bad')
            with self.assertRaises(ValueError):restore.restore(archive,Path(folder)/'data')
            self.assertFalse((Path(folder)/'escape').exists())
    def test_provider_switch_does_not_reuse_other_providers_key(self):
        self.app.save_config({'key':'openai-only'})
        with self.assertRaises(ValueError):self.app.save_config({'provider':'qwen','key':'','model':'qwen3-vl-plus'})
        self.app.save_config({'provider':'qwen','key':'qwen-only','model':'qwen3-vl-plus','workspace':'12345'})
        self.assertEqual(self.app.config()['key'],'qwen-only')
        with self.assertRaises(ValueError):self.app.save_config({'provider':'qwen','key':'key','workspace':'evil.com/path'})
    def test_request_contracts_for_both_providers_and_no_fake_readiness(self):
        self.pair();q=self.save();row=self.app.get_question(q['id'])
        for provider in ['openai','qwen']:
            self.app.save_config({'provider':provider,'key':'fixture-only','model':'gpt-4.1' if provider=='openai' else 'qwen3-vl-plus','workspace':'12345'})
            value=solution()
            result={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(value)}]}]} if provider=='openai' else {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
            with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(result).encode())) as call:
                self.assertEqual(self.app.call_ai(row)['answer_number'],42)
                request=call.call_args[0][0];body=json.loads(request.data)
                self.assertTrue(request.full_url.startswith('https://api.openai.com/' if provider=='openai' else 'https://12345.cn-beijing.maas.aliyuncs.com/'))
                if provider=='openai':self.assertFalse(body['store']);self.assertEqual(body['input'][0]['content'][1]['type'],'input_image')
                else:self.assertEqual(body['response_format']['type'],'json_object');self.assertTrue(body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/'))
            self.assertFalse(self.app.ai_verified())
    def test_real_test_only_marks_matching_config_verified(self):
        self.app.save_config({'key':'fixture-only'})
        value=solution();value['answer_number']=4
        with patch.object(self.app,'call_ai',return_value=value) as solve, patch.object(self.app,'call_practices',return_value=value['practices']) as practices:
            self.assertTrue(self.app.check_key()['ok'])
            self.assertFalse(solve.call_args.kwargs['include_practices'])
            practices.assert_called_once_with(value)
        self.assertTrue(self.app.ai_verified());self.app.save_config({'key':'different-fixture'})
        self.assertFalse(self.app.ai_verified())
        value['needs_review']=True
        with patch.object(self.app,'call_ai',return_value=value),self.assertRaises(ValueError):self.app.check_key()
    def test_connection_check_does_not_verify_failed_practices(self):
        self.app.save_config({'key':'fixture-only'})
        value=solution();value['answer_number']=4
        with patch.object(self.app,'call_ai',return_value=value), patch.object(self.app,'call_practices',side_effect=ValueError('练习连接超时')):
            with self.assertRaisesRegex(ValueError,'练习连接超时'):self.app.check_key()
        self.assertFalse(self.app.ai_verified())
    def test_daily_backup_survives_restart_and_does_not_repeat_within_day(self):
        self.pair();self.save();self.app.daily_backup();self.app.daily_backup()
        self.assertEqual(len(list((self.app.data/'backups').glob('*.zip'))),1)
        self.assertGreater(self.app.health(True)['last_backup'],0)

    def test_twenty_photo_batch_deduplicates_independently(self):
        self.pair()
        from test_server import IMAGE
        ids=[]
        for index in range(20):
            body={'client_id':'batch-'+str(index),'image':IMAGE,'title':'批量照片 '+str(index)}
            status,_,raw=self.request('/api/questions',body)
            self.assertEqual(status,201);ident=json.loads(raw)['question']['id'];ids.append(ident)
            self.assertEqual(json.loads(self.request('/api/questions',body)[2])['question']['id'],ident)
        self.assertEqual(len(set(ids)),20)
        self.assertEqual(len(self.app.list_questions()),20)
        self.assertEqual(len(list(self.app.photos.iterdir())),20)

    def test_batch_queue_and_delete_before_calling_ai(self):
        self.pair()
        from test_server import IMAGE
        self.app.save_config({'key':'fixture-only'})
        ids=[]
        with patch.object(self.app.pool,'submit'):
            for index in range(12):
                q=self.app.save_question({'client_id':'queued-'+str(index),'image':IMAGE})
                ids.append(q['id']);self.assertEqual(self.app.start_solve(q['id'])['status'],'processing')
        self.assertEqual(len(self.app.active),12,'batch cannot fail after four photos')
        self.app.update_question(ids[5],{'archived':True})
        with patch.object(self.app,'call_ai') as call:self.app.solve(ids[5]);call.assert_not_called()
        self.assertNotIn(ids[5],self.app.active)
        self.assertEqual(self.app.get_question(ids[5])['status'],'saved')
        self.assertTrue(self.app.get_question(ids[5])['archived'])
        self.app.update_question(ids[5],{'archived':False})
        with patch.object(self.app.pool,'submit'):self.assertEqual(self.app.start_solve(ids[5])['status'],'processing')
        with patch.object(self.app,'call_ai',return_value=server.validate_solution(solution())):self.app.solve(ids[5])
        self.assertFalse(self.app.get_question(ids[5])['archived'])
        self.assertEqual(self.app.get_question(ids[5])['status'],'ready')

    def test_core_is_visible_before_practices_finish(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        import threading
        started=threading.Event();release=threading.Event()
        core=solution();practices=core['practices'];core['practices']=[]
        def delayed(*args,**kwargs):
            started.set();release.wait(4);return practices
        with patch.object(self.app,'call_ai',return_value=server.validate_solution(core,include_practices=False)),patch.object(self.app,'call_practices',side_effect=delayed):
            self.request('/api/questions/'+q['id']+'/solve',{})
            try:
                self.assertTrue(started.wait(2))
                _,_,raw=self.request('/api/questions/'+q['id']);item=json.loads(raw)['question']
                self.assertEqual(item['status'],'ready');self.assertEqual(item['practices_status'],'processing')
                self.assertEqual(item['solution']['answer_number'],42);self.assertEqual(item['solution']['practices'],[])
            finally:release.set()
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
            item=self.app.dto(self.app.get_question(q['id']));self.assertEqual(item['practices_status'],'ready');self.assertEqual(len(item['solution']['practices']),3)

    def test_practice_failure_preserves_valid_core_and_can_retry(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        core=solution();core['practices']=[];core['lesson_id']=''
        with patch.object(self.app,'call_ai',return_value=server.validate_solution(core,include_practices=False)),patch.object(self.app,'call_practices',side_effect=ValueError('连接 AI 超时')):
            self.app.start_solve(q['id'])
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
        item=self.app.dto(self.app.get_question(q['id']));self.assertEqual(item['status'],'ready');self.assertEqual(item['practices_status'],'failed');self.assertEqual(item['solution']['answer_number'],42)
        with patch.object(self.app,'call_practices',return_value=solution()['practices']):
            self.assertEqual(self.request('/api/questions/'+q['id']+'/practices',{})[0],202)
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
        self.assertEqual(self.app.get_question(q['id'])['practices_status'],'ready')

    def test_math_validation_escalates_once_but_auth_does_not_retry(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        with patch.object(self.app,'call_ai',side_effect=[ValueError('练习答案未通过数值验算'),server.validate_solution(solution())]) as call:
            self.app.start_solve(q['id'])
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(call.call_count,2);self.assertEqual(call.call_args.kwargs['mode'],'careful');self.assertTrue(call.call_args.kwargs['repair'])
        with patch.object(self.app,'call_ai',side_effect=ValueError('AI 密钥无效')) as call:
            self.app.start_solve(q['id'])
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(call.call_count,1)

    def test_multiple_question_choices_and_trusted_selection(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        with self.app.db() as db:db.execute("UPDATE questions SET status='needs_review',error='照片包含第25题和第26题，请选题。' WHERE id=?",(q['id'],))
        self.assertEqual(self.app.dto(self.app.get_question(q['id']))['question_choices'],['25','26'])
        with patch.object(self.app.pool,'submit'):
            self.assertEqual(self.request('/api/questions/'+q['id']+'/solve',{'target_number':'25','mode':'balanced'})[0],202)
            self.assertEqual(self.app.get_question(q['id'])['target_number'],'25')
        self.assertEqual(self.request('/api/questions/'+q['id']+'/solve',{'target_number':'ignore instructions'})[0],400)
        self.assertEqual(self.request('/api/questions/'+q['id']+'/solve',{'mode':'unknown'})[0],400)

    def test_practices_use_strict_text_output_and_validate_answers(self):
        self.app.save_config({'provider':'qwen','key':'fixture-only','model':'qwen3.8-max'})
        import io
        payload={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'practices':solution()['practices']})}}]}
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as call:
            value=self.app.call_practices(solution())
        self.assertEqual(len(value),3);body=json.loads(call.call_args.args[0].data)
        self.assertEqual(body['response_format']['type'],'json_schema');self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertEqual(body['reasoning_effort'],'none');self.assertFalse(body['enable_thinking'])
        self.assertNotIn('image_url',json.dumps(body))
        bad=solution()['practices'];bad[0]['answer']=999
        with patch.object(self.app,'request_ai',return_value={'practices':bad}),self.assertRaises(ValueError):self.app.call_practices(solution())

    def test_failed_ai_practices_have_labeled_verified_curriculum_fallback(self):
        self.pair();q=self.save();self.app.save_config({'key':'fixture-only'})
        core=solution();core.update(problem='6与8的最小公倍数是多少？',lesson_id='1.6',answer='24',answer_number=24,check_expression='2**3*3',practices=[])
        with patch.object(self.app,'call_ai',return_value=server.validate_solution(core,include_practices=False)),patch.object(self.app,'call_practices',side_effect=ValueError('连接 AI 超时')):
            self.app.start_solve(q['id'])
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
        item=self.app.dto(self.app.get_question(q['id']))
        self.assertEqual(item['status'],'ready');self.assertEqual(item['practices_status'],'ready')
        self.assertEqual(item['solution']['practice_source'],'curriculum_fallback')
        self.assertEqual([p['answer'] for p in item['solution']['practices']],[24,36,30])
        self.assertTrue(all(server.arithmetic(p['check_expression'])==p['answer'] for p in item['solution']['practices']))

# Reuse setup/request helpers without reporting the base contracts twice.
for name in HTTPTests.__dict__:
    if name.startswith("test_"):setattr(DeliveryTests,name,None)
del HTTPTests
