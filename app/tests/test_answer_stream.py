# -*- coding: utf-8 -*-
import importlib.util,io,json,threading,unittest
from pathlib import Path
from unittest.mock import patch
from test_rapid import RapidTests,rapid,page

spec=importlib.util.spec_from_file_location('answer_stream',Path(__file__).resolve().parents[1]/'answer_stream.py')
stream=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream)

def packet(text='',finish=None,usage=None):
 value={'choices':[{'index':0,'delta':{'content':text},'finish_reason':finish}]}
 if usage:value['usage']=usage
 return ('data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode()

class StreamDecoderTests(unittest.TestCase):
 def test_one_character_chunks_with_nested_strings_never_emit_half_question(self):
  events=[];p=stream.QuestionStream(events.append)
  first={'p':'括号 } [ 和 "引号" 与 \\','b':[0,1,2,3],'n':'1'}
  prefix='{"note":"questions [ is text", "questions":['+json.dumps(first,ensure_ascii=False)
  for c in prefix[:-1]:p.feed(c)
  self.assertEqual(events,[]);p.feed(prefix[-1]);self.assertEqual(events[0]['questions'],[first])
  p.feed(',{"n":"2"}]}');self.assertEqual(len(events),2)
 def test_objects_outside_questions_are_not_published(self):
  events=[];p=stream.QuestionStream(events.append);p.feed('{"other":[{"n":"bad"}],"questions":[]}')
  self.assertEqual(events,[])
 def test_final_shape_and_usage_are_preserved(self):
  events=[]
  raw=packet('{"questions":[{"n":"1"}')+packet('],"note":""}',finish='stop',usage={'prompt_tokens':8,'completion_tokens':5})+b'data: [DONE]\n\n'
  result=stream.read_qwen_stream(io.BytesIO(raw),5,events.append)
  self.assertEqual(result['usage']['completion_tokens'],5);self.assertEqual(result['choices'][0]['finish_reason'],'stop')
  self.assertEqual(json.loads(result['choices'][0]['message']['content'])['questions'],[{'n':'1'}]);self.assertEqual(len(events),1)
 def test_missing_finish_is_not_fabricated(self):
  result=stream.read_qwen_stream(io.BytesIO(packet('{"questions":[]}')),5)
  self.assertIsNone(result['choices'][0]['finish_reason'])
 def test_usage_only_event_and_heartbeat(self):
  raw=b': heartbeat\n\n'+packet('{"questions":[]}',finish='stop')+b'data: {"choices":[],"usage":{"prompt_tokens":11}}\n\ndata: [DONE]\n\n'
  self.assertEqual(stream.read_qwen_stream(io.BytesIO(raw),5)['usage']['prompt_tokens'],11)
 def test_invalid_or_refused_stream_fails_without_guessing(self):
  for raw in [b'data: {invalid}\n',b'data: {"error":{"code":"bad"}}\n',b'data: {"choices":[{"delta":{"refusal":"no"}}]}\n']:
   with self.assertRaises(ValueError):stream.read_qwen_stream(io.BytesIO(raw),5)
 def test_deadline_and_size_are_bounded(self):
  with self.assertRaises(TimeoutError):stream.read_qwen_stream(io.BytesIO(packet('a')),-1)
  with self.assertRaises(ValueError):stream.QuestionStream(lambda _:None).feed('x'*2_000_001)

class StreamingPipelineTests(RapidTests):
 def test_first_answer_is_persisted_before_remaining_model_output(self):
  entered=threading.Event();release=threading.Event();errors=[]
  one=rapid(1,'correct',w='4');one['v']='4'
  two=rapid(2);two['v']='4'
  class Response(io.BytesIO):
   reads=0
   def readline(inner,*args):
    inner.reads+=1
    if inner.reads==3:entered.set();release.wait(3)
    return super(Response,inner).readline(*args)
  def open_fake(request,*args,**kwargs):
   body=json.loads(request.data)
   if body.get('stream'):
    text=packet('{"questions":['+json.dumps(one)+',')+packet(json.dumps(two)+'],"note":""}',finish='stop',usage={'prompt_tokens':1,'completion_tokens':1})+b'data: [DONE]\n\n'
    return Response(text)
   return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(page(one,two))}}]}).encode())
  def run():
   try:self.collector.collect(self.parent['id'])
   except Exception as e:errors.append(e)
  with patch('urllib.request.urlopen',side_effect=open_fake),patch.object(self.app,'start_solve'):
   worker=threading.Thread(target=run);worker.start()
   try:
    self.assertTrue(entered.wait(2));result=self.app.dto(self.app.get_question(self.parent['id']))
    self.assertTrue(result['import_result']['provisional']);self.assertEqual(result['import_result']['items'][0]['answer'],'4');self.assertTrue(worker.is_alive())
   finally:release.set();worker.join(5)
  self.assertFalse(errors);result=self.app.dto(self.app.get_question(self.parent['id']))
  self.assertFalse(result['import_result']['provisional']);self.assertEqual(len(result['import_result']['items']),2)
 def test_failed_stream_is_not_retried_as_a_paid_nonstream_call(self):
  from test_rapid import server
  with patch('urllib.request.urlopen',return_value=io.BytesIO(packet('{"questions":[]}',finish='length'))) as request:
   with self.assertRaises(ValueError):self.app.request_ai(self.app.config(),'https://fixture.invalid',{'model':'qwen3.8-max','stream':True},5)
  self.assertEqual(request.call_count,1)

if __name__=='__main__':unittest.main()
