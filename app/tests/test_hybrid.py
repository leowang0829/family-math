import copy, io, json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import test_server
from test_auto_collect import scanned
server = test_server.server

class HybridTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = server.App(self.temp.name, '127.0.0.1', 0)
        self.app.save_config({'provider':'qwen','key':'fixture-only','model':'qwen3.8-max'})
        config=json.loads(self.app.config_path.read_text()); config['routing']='hybrid-v1'
        self.app.config_path.write_text(json.dumps(config))
        self.item=self.app.save_question({'image':test_server.IMAGE,'client_id':'hybrid-fixture'})
    def tearDown(self):
        self.app.stopping.set(); self.app.pool.shutdown(wait=True); self.app.practice_pool.shutdown(wait=True)
        self.temp.cleanup()
    def test_routes_extraction_practices_to_flash_and_verdict_solution_to_max(self):
        for stage in ['extract','practices']:
            self.assertEqual(self.app.stage_config(stage)['model'],'qwen3.8-flash')
        for stage in ['review','solve','print']:
            self.assertEqual(self.app.stage_config(stage)['model'],'qwen3.8-max')
        self.app.save_config({'provider':'qwen','key':'','model':'qwen3.8-max'})
        self.assertTrue(self.app.hybrid_enabled())
    def test_max_reads_source_even_when_flash_reports_no_questions_and_result_is_cached(self):
        scan={'questions':[scanned(1,'correct')],'note':''}
        with patch.object(self.app,'call_scan',side_effect=[{'questions':[],'note':''},scan]) as call:
            result, reviews, cached=self.app.hybrid_scan(self.app.get_question(self.item['id']))
            self.assertEqual(call.call_count,2); self.assertEqual(call.call_args.kwargs['mode'],'careful')
            self.assertEqual(reviews,1); self.assertFalse(cached)
        with patch.object(self.app,'call_scan') as call:
            result, reviews, cached=self.app.hybrid_scan(self.app.get_question(self.item['id']))
            self.assertTrue(cached); call.assert_not_called()
    def test_uncertain_page_is_not_cached_as_final(self):
        scan={'questions':[scanned(1,'uncertain',.5)],'note':''}
        with patch.object(self.app,'call_scan',return_value=scan) as call:
            self.app.hybrid_scan(self.app.get_question(self.item['id']))
            self.app.hybrid_scan(self.app.get_question(self.item['id']))
            self.assertEqual(call.call_count,4)
    def test_flash_extracts_without_thinking_and_max_review_keeps_photo(self):
        scan={'questions':[scanned(1)],'note':''}
        with patch.object(self.app,'request_ai',return_value=scan) as call:
            self.app.call_scan(self.app.get_question(self.item['id']))
            body=call.call_args.args[2]
            self.assertEqual(body['model'],'qwen3.8-flash');self.assertFalse(body['enable_thinking']);self.assertIn('JSON',body['messages'][0]['content'])
            self.app.call_scan(self.app.get_question(self.item['id']),mode='careful',previous=scan)
            body=call.call_args.args[2]
            self.assertEqual(body['model'],'qwen3.8-max');self.assertEqual(body['reasoning_effort'],'medium')
            self.assertEqual(body['messages'][1]['content'][1]['type'],'image_url')
    def test_explanation_does_not_generate_practices_until_requested(self):
        core=copy.deepcopy(test_server.solution());core['practices']=[]
        with patch.object(self.app,'call_ai',return_value=core),patch.object(self.app.practice_pool,'submit') as submit:
            self.app.solve(self.item['id'])
            row=self.app.get_question(self.item['id'])
            self.assertEqual(row['status'],'ready');self.assertEqual(row['practices_status'],'on_demand')
            submit.assert_not_called()
        with patch.object(self.app,'request_ai',return_value={'practices':test_server.solution()['practices']}) as call:
            self.app.solve_practices(self.item['id'])
            self.assertEqual(call.call_args.args[2]['model'],'qwen3.8-flash')
            self.app.start_practices(self.item['id'])
            self.assertEqual(call.call_count,1,'stored practices are reused')
    def test_usage_counts_reasoning_within_output_and_marks_unknown_cost(self):
        result={'id':'fixture-request','usage':{'prompt_tokens':1000,'completion_tokens':2000,
            'prompt_tokens_details':{'cached_tokens':100},'completion_tokens_details':{'reasoning_tokens':1500}},
            'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        config=self.app.stage_config('review')
        with patch.object(server.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(result).encode())):
            self.app.request_ai(config,'https://example.invalid',{'model':config['model']},1)
        with self.app.db() as db: row=db.execute('SELECT * FROM ai_usage').fetchone()
        self.assertEqual(row['output_tokens'],2000);self.assertEqual(row['reasoning_tokens'],1500)
        self.assertAlmostEqual(row['estimated_cny'],.08295)
        with patch.object(server.urllib.request,'urlopen',side_effect=TimeoutError):
            with self.assertRaises(ValueError):self.app.request_ai(config,'https://example.invalid',{'model':config['model']},1)
        self.assertEqual(self.app.usage_summary()['items'][0]['unknown_cost_calls'],1)
        self.assertNotIn('fixture-only',json.dumps(self.app.usage_summary()))

    def test_repeated_upload_of_collected_photo_reuses_parent(self):
        with self.app.db() as db:
            db.execute("UPDATE questions SET is_import=1,status='collected' WHERE id=?",(self.item['id'],))
        repeated=self.app.save_question({'image':test_server.IMAGE,'client_id':'second-upload','auto_collect':True})
        self.assertEqual(repeated['id'],self.item['id'])
        self.assertEqual(len(self.app.list_questions()),1)
