import importlib.util
import json
import math
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('math_server',ROOT/'server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
COURSE=json.loads((ROOT/'curriculum/curriculum.json').read_text())

class CurriculumTests(unittest.TestCase):
 def test_knowledge_index_is_not_bound_to_a_book(self):
  self.assertEqual(COURSE['id'],'math-foundations')
  self.assertNotIn('publisher',COURSE)
  self.assertEqual(len(COURSE['chapters']),4)
  self.assertTrue(all('page' not in lesson and 'end' not in lesson for lesson in COURSE['lessons']))
 def test_every_lesson_has_complete_original_content(self):
  self.assertEqual(len(COURSE['lessons']),25)
  self.assertEqual(sum(len(l['practices']) for l in COURSE['lessons']),75)
  for lesson in COURSE['lessons']:
   with self.subTest(lesson=lesson['id']):
    self.assertTrue(lesson['goal']);self.assertGreaterEqual(len(lesson['concept']),2)
    self.assertTrue(lesson['formula']);self.assertTrue(lesson['pitfall']);self.assertTrue(lesson['example']['steps']);self.assertTrue(lesson['example']['answer'])
    self.assertEqual(len(lesson['practices']),3)
 def test_all_numeric_answers_pass_arithmetic(self):
  for lesson in COURSE['lessons']:
   for index,p in enumerate(lesson['practices']):
    with self.subTest(lesson=lesson['id'],exercise=index):
     if p['type']=='number':self.assertTrue(math.isclose(module.arithmetic(p['check']),p['answer'],rel_tol=1e-10,abs_tol=1e-10))
     else:self.assertIn(p['answer'],p['options']);self.assertEqual(len(p['options']),len(set(p['options'])))
     self.assertTrue(p['hint']);self.assertTrue(p['solution'])
 def test_prerequisites_form_a_forward_learning_path(self):
  order={l['id']:i for i,l in enumerate(COURSE['lessons'])}
  for l in COURSE['lessons']:
   for prerequisite in l['prerequisites']:
    self.assertIn(prerequisite,order);self.assertLess(order[prerequisite],order[l['id']])
 def test_every_lesson_belongs_to_an_existing_topic(self):
  chapters={chapter['id'] for chapter in COURSE['chapters']}
  self.assertTrue(all(lesson['chapter'] in chapters for lesson in COURSE['lessons']))
 def test_classroom_default_and_example_links(self):
  self.assertEqual(COURSE['initialChapter'],'1')
  ids={l['id'] for l in COURSE['lessons']}
  self.assertTrue(all(value in ids for value in COURSE['questionLinks'].values()))

if __name__=='__main__':unittest.main()
