import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import test_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import printing


def clean_question():
    return {'title': '分数应用题',
            'blocks': [{'kind': 'text', 'content': r'一段绳子长120米，先用去全长的\(\frac{2}{5}\)，再用去全长的\(\frac{1}{4}\)。还剩多少米？'}],
            'diagram': {'required': False, 'description': '', 'width': 600, 'height': 300, 'primitives': []},
            'needs_review': False, 'review_note': '', 'answer_space_mm': 60}


def primitive(kind='line', **kwargs):
    item = {'kind': kind, 'x': 0, 'y': 0, 'width': 0, 'height': 0,
            'radius': 0, 'points': [{'x': 40, 'y': 40}, {'x': 200, 'y': 40}],
            'text': '', 'dashed': False, 'font_size': 20, 'fill': 'none'}
    item.update(kwargs)
    return item


class PrintValidation(unittest.TestCase):
    def test_unused_zero_canvas_is_accepted_without_weakening_real_diagrams(self):
        value = clean_question(); value['diagram'].update(width=0, height=0)
        self.assertEqual(printing.validate_question(value)['diagram']['width'], 600)
        value['diagram'].update(required=True, width=0, height=0, primitives=[primitive()])
        with self.assertRaises(ValueError): printing.validate_question(value)

    def test_valid_fractions_and_vector_geometry_are_preserved(self):
        value = clean_question()
        value['diagram'].update(required=True, description='长方形ABCD', primitives=[primitive(), primitive('text', x=40, y=60, text='A', points=[])])
        self.assertEqual(printing.validate_question(value)['diagram']['primitives'][1]['text'], 'A')
        self.assertIn(r'\frac{2}{5}', value['blocks'][0]['content'])

    def test_missing_required_diagram_is_not_silently_printed(self):
        value = clean_question(); value['diagram']['required'] = True
        with self.assertRaises(ValueError): printing.validate_question(value)

    def test_shading_is_preserved_and_clipped_or_tiny_figures_are_rejected(self):
        value = clean_question(); value['diagram'].update(required=True, primitives=[primitive('rect', x=30, y=30, width=80, height=80, fill='hatch', points=[])])
        self.assertEqual(printing.validate_question(value)['diagram']['primitives'][0]['fill'], 'hatch')
        for item in [primitive('rect', x=590, width=40), primitive('circle', x=20, radius=40), primitive('text', font_size=14)]:
            value['diagram'].update(width=1200, primitives=[item])
            if item['kind'] == 'rect': value['diagram']['width'] = 600
            with self.subTest(item=item), self.assertRaises(ValueError): printing.validate_question(value)

    def test_incomplete_question_stays_reviewable(self):
        value = clean_question(); value.update(needs_review=True, review_note='第(1)问缺少原题条件', blocks=[])
        self.assertTrue(printing.validate_question(value)['needs_review'])

    def test_script_primitives_and_invalid_coordinates_are_rejected(self):
        for item in [primitive('script'), primitive(x=float('nan')), primitive(points=[{'x': -1, 'y': 0}, {'x': 1, 'y': 1}])]:
            value = clean_question(); value['diagram'].update(required=True, primitives=[item])
            with self.subTest(item=item), self.assertRaises(ValueError): printing.validate_question(value)


class PrintHTTPTests(test_server.HTTPTests):
    def tearDown(self):
        if self.app.print_service: self.app.print_service.pool.shutdown(wait=True)
        super().tearDown()

    def wait_job(self, ident):
        for _ in range(150):
            job = self.app.printing().load(ident)
            if job['state'] != 'preparing': return job
            time.sleep(.01)
        self.fail('print job did not finish')

    def test_printing_requires_pair_and_ai_and_real_question(self):
        self.assertEqual(self.request('/api/print-jobs', {'ids': ['a' * 32]})[0], 401)
        self.assertEqual(self.request('/print/' + 'a' * 32)[0], 401)
        self.assertEqual(self.request('/api/print-jobs/' + 'a' * 32)[0], 401)
        self.pair(); q = self.save()
        self.assertEqual(self.request('/api/print-jobs', {'ids': [q['id']]})[0], 400)
        self.app.save_config({'key': 'fixture-only'})
        for ids in [[], ['../private'], [None], 'invalid']:
            self.assertEqual(self.request('/api/print-jobs', {'ids': ids})[0], 400)
        self.assertEqual(self.request('/api/print-jobs', {'ids': ['a' * 32]})[0], 404)

    def test_more_than_fifty_unique_questions_keep_every_selected_item(self):
        self.pair(); original = self.save(); self.app.save_config({'key': 'fixture-only'})
        ids = [format(index + 1, '032x') for index in range(125)]
        with self.app.db() as db:
            for ident in ids:
                db.execute('INSERT INTO questions(id,client_id,profile,photo,title,problem,topic,status,error,created) SELECT ?,?,profile,photo,title,problem,topic,status,error,created FROM questions WHERE id=?', (ident, 'print-' + ident, original['id']))
        with patch.object(self.app.printing(), 'clean', return_value=clean_question()) as cleaner:
            status, _, raw = self.request('/api/print-jobs', {'ids': ids})
            self.assertEqual(status, 202)
            job = self.wait_job(json.loads(raw)['id'])
            self.assertEqual(job['total'], 125); self.assertEqual(job['completed'], 125)
            self.assertEqual([item['id'] for item in job['items']], ids)
            self.assertTrue(all(item['state'] == 'ready' for item in job['items']))
            self.assertEqual(cleaner.call_count, 125)

    def test_large_repeated_selection_is_deduplicated_before_preparation(self):
        self.pair(); original = self.save(); self.app.save_config({'key': 'fixture-only'})
        with patch.object(self.app.printing(), 'clean', return_value=clean_question()) as cleaner:
            result = self.app.printing().create([original['id']] * 125)
            job = self.wait_job(result['id'])
            self.assertEqual(job['total'], 1); self.assertEqual(cleaner.call_count, 1)

    def test_vision_reconstruction_is_cached_and_never_sends_solution(self):
        self.pair(); q = self.save()
        self.app.save_config({'provider': 'qwen', 'key': 'fixture-secret', 'model': 'qwen3.8-max', 'workspace': 'fixture-space'})
        with self.app.db() as db: db.execute('UPDATE questions SET target_number=?,student_work=?,solution=? WHERE id=?', ('25', 'PRIVATE-STUDENT-ANSWER', json.dumps({'answer': 'PRIVATE-CORRECT-ANSWER'}), q['id']))
        with patch.object(self.app, 'request_ai', return_value=clean_question()) as model:
            status, _, raw = self.request('/api/print-jobs', {'ids': [q['id'], q['id']]})
            self.assertEqual(status, 202); ident = json.loads(raw)['id']; job = self.wait_job(ident)
            self.assertEqual(len(job['items']), 1); self.assertEqual(job['items'][0]['state'], 'ready')
            body = model.call_args.args[2]; serialized = json.dumps(body, ensure_ascii=False)
            self.assertNotIn('PRIVATE-STUDENT-ANSWER', serialized); self.assertNotIn('PRIVATE-CORRECT-ANSWER', serialized)
            self.assertIn('原图第25题', serialized); self.assertEqual(body['reasoning_effort'], 'xhigh')
            self.assertEqual(body['messages'][1]['content'][1]['type'], 'image_url')
            status, _, raw = self.request('/api/print-jobs', {'ids': [q['id']]}); self.wait_job(json.loads(raw)['id'])
            self.assertEqual(model.call_count, 1, 'reopening preview should reuse a verified clean question')
        status, headers, raw = self.request('/print/' + ident)
        self.assertEqual(status, 200); self.assertIn('object-src', headers['Content-Security-Policy'])
        self.assertNotIn(b'fixture-secret', raw)
        status, _, raw = self.request('/api/print-jobs/' + ident)
        self.assertEqual(status, 200); self.assertNotIn(b'fixture-secret', raw)
        for path in self.app.printing().root.rglob('*.json'): self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.request('/printing/jobs/' + ident + '.json')[0], 404)

    def test_unclear_photo_and_failed_model_are_visible_and_never_cached(self):
        self.pair(); q = self.save(); self.app.save_config({'key': 'fixture-only'})
        value = clean_question(); value.update(needs_review=True, review_note='分母被手写答案遮挡，无法确认')
        with patch.object(self.app, 'request_ai', return_value=value):
            result = self.app.printing().create([q['id']]); job = self.wait_job(result['id'])
            self.assertEqual(job['items'][0]['state'], 'review')
            self.assertFalse(list(self.app.printing().cache.glob('*.json')))
        with patch.object(self.app, 'request_ai', side_effect=ValueError('连接 AI 超时')):
            result = self.app.printing().create([q['id']]); job = self.wait_job(result['id'])
            self.assertEqual(job['items'][0]['state'], 'failed'); self.assertIn('超时', job['items'][0]['error'])

    def test_deleted_and_whole_page_records_are_not_printable_questions(self):
        self.pair(); q = self.save(); self.app.save_config({'key': 'fixture-only'})
        self.app.update_question(q['id'], {'archived': True})
        self.assertEqual(self.request('/api/print-jobs', {'ids': [q['id']]})[0], 400)
        self.app.update_question(q['id'], {'archived': False})
        with self.app.db() as db: db.execute('UPDATE questions SET is_import=1 WHERE id=?', (q['id'],))
        self.assertEqual(self.request('/api/print-jobs', {'ids': [q['id']]})[0], 400)

    def test_restart_does_not_leave_preview_waiting_forever(self):
        service = self.app.printing(); ident = 'a' * 32
        service.write(service.jobs / (ident + '.json'), {'id': ident, 'state': 'preparing', 'items': []})
        self.assertEqual(service.load(ident)['state'], 'interrupted')


for name in test_server.HTTPTests.__dict__:
    if name.startswith('test_'): setattr(PrintHTTPTests, name, None)
