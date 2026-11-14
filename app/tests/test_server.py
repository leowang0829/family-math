import base64
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('math_server',Path(__file__).resolve().parents[1]/'server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
IMAGE='data:image/png;base64,'+base64.b64encode((Path(__file__).resolve().parents[1]/'dist/assets/icon-180.png').read_bytes()).decode()


def solution():
    return {'needs_review':False,'review_note':'','title':'验算测试题','problem':'120 本书，用去2/5和1/4，还剩多少本？','student_work':'照片中未见作答','topic':'fraction','lesson_id':'2.9','knowledge_points':['求剩余部分'],'diagnosis':'还没有可判断的错因，先看解题方法。','hint':'先求剩下的分率。','steps':[{'title':'求剩余分率','text':'从1中减去。','math':'1-2/5-1/4=7/20'},{'title':'求数量','text':'总数乘分率。','math':'120*7/20=42'}],'answer':'42 本','answer_number':42,'check_expression':'120*(1-2/5-1/4)','concept':'部分量=总数×分率','extension':'已知部分求整体','practices':[{'kind':kind,'text':'测试用变式，不是真实AI结果','answer':n,'unit':'本','hint':'先求分率','solution':str(n),'check_expression':expr} for kind,n,expr in [('换数字',90,'200*(1-3/10-1/4)'),('换情境',70,'200*(1-2/5-1/4)'),('多想一步',14,'120*(1-2/5-1/4)/3')]]}


class ArithmeticTests(unittest.TestCase):
    def test_fraction(self):self.assertAlmostEqual(server.arithmetic('120*(1-2/5-1/4)'),42)
    def test_reject_code_and_expensive_expression(self):
        for expr in ["__import__('os').system('true')",'2**1000000','(1).__class__','1/0','1e300*1e300','[1,2]']:
            with self.subTest(expr=expr),self.assertRaises((ValueError,ZeroDivisionError)):server.arithmetic(expr)
    def test_numeric_verification(self):
        self.assertIn('verification',server.validate_solution(solution()))
        bad=solution();bad['practices'][0]['answer']=91
        with self.assertRaises(ValueError):server.validate_solution(bad)
    def test_unclear_photo_cannot_reveal_answer(self):
        data=solution();data['needs_review']=True;data['review_note']='看不清分母'
        value=server.validate_solution(data);self.assertEqual(value['answer'],'');self.assertEqual(value['practices'],[]);self.assertIsNone(value['answer_number'])
    def test_missing_or_hostile_fields(self):
        data=solution();del data['problem']
        with self.assertRaises(ValueError):server.validate_solution(data)
        data=solution();data['practices'][0]['answer']=float('nan')
        with self.assertRaises(ValueError):server.validate_solution(data)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'OPENAI_API_KEY':''});self.env.start()
        self.app=server.App(self.temp.name,'127.0.0.1',0)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.app.port=self.http.server_address[1];self.http.app=self.app
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.app.port)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));self.cookie=''
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.app.pool.shutdown(wait=True);self.app.practice_pool.shutdown(wait=True);self.env.stop();self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        hs={'Cookie':self.cookie}
        if body is not None:hs.update({'Content-Type':'application/json','X-Math-Request':'1','Origin':self.url})
        hs.update(headers or {})
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=hs)
        try:
            with self.opener.open(req,timeout=5) as r:return r.status,r.headers,r.read()
        except urllib.error.HTTPError as error:return error.code,error.headers,error.read()
    def pair(self):
        status,headers,body=self.request('/api/pair',{'code':self.app.pair_code});self.assertEqual(status,200);self.cookie=headers['Set-Cookie'].split(';')[0]
    def save(self):
        status,_,body=self.request('/api/questions',{'client_id':'test-question','image':IMAGE,'title':'测试题'});self.assertEqual(status,201);return json.loads(body)['question']
    def test_health_no_secret(self):
        status,_,body=self.request('/api/health');self.assertEqual(status,200);data=json.loads(body);self.assertFalse(data['paired']);self.assertFalse(data['ai_configured']);self.assertNotIn('key',data);self.assertNotIn('pair_code',data)
    def test_pair_required_for_photos(self):
        self.assertEqual(self.request('/api/questions')[0],401);self.assertEqual(self.request('/api/questions',{'image':IMAGE})[0],401)
        self.assertEqual(self.request('/api/pair',{'code':'invalid'})[0],401)
    def test_fixed_pairing_restart_retains_sessions_and_no_daily_expiry(self):
        self.pair()
        code_file=Path(self.temp.name)/'pairing-config.json'
        code_file.write_text(json.dumps({'code':'666666'}))
        old=self.app
        self.app=server.App(self.temp.name,'127.0.0.1',self.app.port)
        self.http.app=self.app;old.pool.shutdown(wait=True)
        self.assertEqual(self.app.pair_code,'666666');self.assertTrue(self.app.pair_fixed)
        self.assertEqual(self.request('/api/questions')[0],200,'existing device session survives restart')
        self.assertEqual(self.request('/pairing-config.json')[0],404)
        self.assertEqual(code_file.stat().st_mode&0o777,0o600)
        self.assertEqual(self.request('/api/pair',{'code':'147881'})[0],401)
        with patch.object(server.time,'time',return_value=time.time()+2*86400):
            self.assertEqual(self.request('/api/pair',{'code':'666666'})[0],200,'fixed code works beyond 24 hours')
        _,_,raw=self.request('/api/setup');self.assertTrue(json.loads(raw)['pair_code_fixed'])
    def test_random_code_still_expires(self):
        self.assertFalse(self.app.pair_fixed)
        self.app.pair_until=0
        self.assertEqual(self.request('/api/pair',{'code':self.app.pair_code})[0],401)
    def test_invalid_fixed_code_does_not_silently_change_code(self):
        (Path(self.temp.name)/'pairing-config.json').write_text(json.dumps({'code':'not-six-digits'}))
        with self.assertRaises(ValueError):server.App(self.temp.name,'127.0.0.1',self.app.port)
    def test_save_deduplicate_photo_and_no_key(self):
        self.pair();q=self.save();self.assertEqual(q['status'],'needs_setup')
        self.assertTrue(self.app.get_question(q['id'])['photo']);self.assertEqual(len(list(self.app.photos.iterdir())),1)
        self.assertEqual(self.save()['id'],q['id']);self.assertEqual(len(list(self.app.photos.iterdir())),1)
        status,_,body=self.request('/api/questions/'+q['id']+'/photo');self.assertEqual(status,200);self.assertGreater(len(body),20)
        status,_,body=self.request('/api/questions/'+q['id']+'/solve',{});self.assertEqual(status,202);self.assertEqual(json.loads(body)['question']['status'],'needs_setup')
        self.assertFalse(self.app.active)
    def test_second_device_sees_same_question(self):
        self.pair();q=self.save();self.cookie='';self.pair();_,_,body=self.request('/api/questions');self.assertEqual(json.loads(body)['questions'][0]['id'],q['id'])
    def test_private_files_and_cross_origin_blocked(self):
        self.assertEqual(self.request('/api/setup',{},headers={'X-Setup-Nonce':'bad'})[0],403)
        self.assertEqual(self.request('/api/pair',{'code':self.app.pair_code},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/health',headers={'Host':'evil.example:'+str(self.app.port)})[0],403)
        for path in ['/../server.py','/ai-config.json','/math.sqlite3','/photos/anything.png']:
            with self.subTest(path=path):self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/setup',headers={'Host':'192.168.1.2:'+str(self.app.port)})[0],403)
    def test_config_permissions_no_return_key(self):
        status,_,body=self.request('/api/setup',{'key':'test-secret-not-real','model':'gpt-4.1'},headers={'X-Setup-Nonce':self.app.setup_nonce});self.assertEqual(status,200)
        self.assertEqual(self.app.config_path.stat().st_mode&0o777,0o600)
        _,_,body=self.request('/api/setup');self.assertNotIn(b'test-secret-not-real',body)
    def test_qwen_flagship_keeps_reasoning_with_bounded_budget(self):
        self.app.save_config({'provider':'qwen','key':'test-secret-not-real','workspace':'test-workspace','model':'qwen3.8-max'})
        result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(solution())}}]}
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(result).encode())) as call:
            value=self.app.call_ai({'photo':'test.png','problem':'','lesson_id':'1.1'},b'test-image')
        request=call.call_args.args[0];body=json.loads(request.data)
        self.assertEqual(request.full_url,'https://test-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions')
        self.assertTrue(body['enable_thinking']);self.assertEqual(body['reasoning_effort'],'low');self.assertEqual(body['max_tokens'],12000)
        self.assertEqual(body['model'],'qwen3.8-max');self.assertEqual(body['response_format']['type'],'json_object')
        self.assertEqual(body['messages'][1]['content'][1]['type'],'image_url')
        self.assertEqual(value['answer_number'],42)
        self.assertGreaterEqual(call.call_args.kwargs['timeout'],180)
    def test_deep_reasoning_has_more_time_without_changing_model(self):
        self.app.save_config({'provider':'qwen','key':'fixture-only','model':'qwen3.8-max'})
        result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(solution())}}]}
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(result).encode())) as call:
            self.app.call_ai({'photo':'test.png','problem':'','lesson_id':'1.1'},b'test-image',mode='careful')
        self.assertGreaterEqual(call.call_args.kwargs['timeout'],300)
        self.assertEqual(json.loads(call.call_args.args[0].data)['model'],'qwen3.8-max')
    def test_transport_timeout_has_specific_message_and_is_not_retried(self):
        with patch.object(server.urllib.request,'urlopen',side_effect=TimeoutError) as call:
            with self.assertRaisesRegex(ValueError,'AI 响应超时'):
                self.app.request_ai({'provider':'qwen','key':'fixture-only'},'https://example.invalid',{'enable_thinking':True,'reasoning_effort':'low'},90)
        self.assertEqual(call.call_count,1)
    def test_no_book_pages_are_served(self):
        self.assertEqual(self.request('/api/textbook')[0],401)
        self.pair()
        self.assertEqual(self.request('/api/textbook')[0],404)
        self.assertEqual(self.request('/api/textbook/page/2')[0],404)
        self.assertEqual(self.request('/textbooks/source.pdf')[0],404)

    def test_invalid_upload(self):
        self.pair();self.assertEqual(self.request('/api/questions',{'image':'data:image/png;base64,AA=='})[0],400)
        self.assertEqual(self.request('/api/questions',{'image':'data:image/jpeg;base64,'+base64.b64encode(b'not-a-jpeg'*10).decode()})[0],400)
    def test_job_success_and_failure_states(self):
        self.pair();q=self.save();self.app.save_config({'key':'unit-test-key'})
        good=server.validate_solution(solution())
        with patch.object(self.app,'call_ai',return_value=good):
            self.request('/api/questions/'+q['id']+'/solve',{})
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(self.app.get_question(q['id'])['status'],'ready')
        with patch.object(self.app,'call_ai',side_effect=ValueError('AI 密钥无效')):
            self.request('/api/questions/'+q['id']+'/solve',{})
            for _ in range(100):
                if not self.app.active:break
                time.sleep(.01)
            self.assertEqual(self.app.get_question(q['id'])['status'],'failed');self.assertIn('密钥无效',self.app.get_question(q['id'])['error'])
    def test_stale_progress_does_not_erase_newer_attempt(self):
        self.pair()
        self.request('/api/progress',{'progress':{'records':{'books':{'status':'learning','updatedAt':20}},'attempts':[{'id':'new','date':'2026-10-14'}]}})
        self.request('/api/progress',{'progress':{'records':{'books':{'status':'pending','updatedAt':10}},'attempts':[{'id':'old','date':'2026-10-13'}]}})
        _,_,raw=self.request('/api/progress');value=json.loads(raw)['progress'];self.assertEqual(value['records']['books']['status'],'learning');self.assertEqual({a['id'] for a in value['attempts']},{'old','new'})


if __name__=='__main__':unittest.main()
