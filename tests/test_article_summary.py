import tempfile
import unittest
from pathlib import Path
from article_summary import SummaryService, SummaryError

TEXT = 'Verified article evidence. ' * 40

class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        def generate(text, url):
            self.calls.append(text)
            return {'text': 'An overview.\n- A key point.', 'provider': 'test', 'model': 'model', 'usage': {}}
        self.service = SummaryService(Path(self.tmp.name), fetch=lambda url: {'text': TEXT, 'coverage': 'extracted article text', 'source_url': url, 'final_url': url}, generate=generate)
        self.article = {'id': 1, 'url': 'https://example.org/one', 'title': 'One'}

    def test_concurrent_failure_is_shared_without_second_generation(self):
        import threading, time
        entered, release = threading.Event(), threading.Event()
        def generate(text, url):
            self.calls.append(text)
            entered.set(); release.wait(2)
            raise RuntimeError('ambiguous provider failure')
        self.service.generate = generate
        errors = []
        def request():
            try:
                self.service.summarize(self.article, 'a')
            except SummaryError as error:
                errors.append(str(error))
        first = threading.Thread(target=request); first.start()
        self.assertTrue(entered.wait(1))
        second = threading.Thread(target=request); second.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            with self.service.guard:
                records = getattr(self.service, 'inflight', None)
                users = [r['users'] for r in records.values()] if records is not None else [r[1] for r in self.service.locks.values()]
                if 2 in users:
                    break
            time.sleep(.01)
        release.set(); first.join(3); second.join(3)
        self.assertEqual(len(errors), 2)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(errors[0], errors[1])

    def test_success_is_cached_without_second_model_call(self):
        first = self.service.summarize(self.article, 'configuration-a')
        second = self.service.summarize(self.article, 'configuration-a')
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(second['source_url'], self.article['url'])

    def test_saved_summary_loads_offline_and_after_service_restart(self):
        first = self.service.summarize(self.article, 'a')
        service = SummaryService(self.tmp.name, fetch=lambda _: self.fail('Must not fetch'), generate=lambda *_: self.fail('Must not generate'))
        saved = service.saved_summary(self.article)
        self.assertEqual(saved['text'], first['text'])
        self.assertTrue(saved['cached'])
        self.assertFalse(saved['stale'])

    def test_stale_summary_is_visible_but_regeneration_replaces_it(self):
        import json, time
        from article_summary import TTL
        self.service.summarize(self.article, 'a')
        path = next(Path(self.tmp.name).glob('*.json'))
        old = json.loads(path.read_text()); old['generated_at'] = time.time() - TTL - 1
        path.write_text(json.dumps(old))
        self.assertTrue(self.service.saved_summary(self.article)['stale'])
        result = self.service.summarize(self.article, 'a', regenerate=True)
        self.assertFalse(result['cached'])
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.service.saved_summary(self.article)['stale'])

    def test_regeneration_bypasses_fresh_cache_and_failed_attempt_keeps_saved(self):
        self.service.summarize(self.article, 'a')
        self.service.summarize(self.article, 'a', regenerate=True)
        self.assertEqual(len(self.calls), 2)
        def fail(*args):
            raise RuntimeError('failed')
        self.service.generate = fail
        with self.assertRaises(SummaryError):
            self.service.summarize(self.article, 'a', regenerate=True)
        self.assertIsNotNone(self.service.saved_summary(self.article))
        self.assertIsNone(self.service.saved_summary({'url': 'https://example.org/other'}))

    def test_configuration_change_invalidates_cache(self):
        self.service.summarize(self.article, 'a')
        self.service.summarize(self.article, 'b')
        self.assertEqual(len(self.calls), 2)

    def test_empty_model_result_is_not_cached(self):
        self.service.generate = lambda text, url: {'text': '', 'model': 'model', 'provider': 'test'}
        with self.assertRaises(SummaryError):
            self.service.summarize(self.article, 'a')
        self.assertEqual(list(Path(self.tmp.name).glob('*.json')), [])

    def test_duplicate_requests_share_one_generation(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        def generate(text, url):
            self.calls.append(text)
            entered.set()
            release.wait(2)
            return {'text': 'A real result', 'model': 'model', 'provider': 'test'}
        self.service.generate = generate
        results = []
        thread = threading.Thread(target=lambda: results.append(self.service.summarize(self.article, 'a')))
        thread.start()
        self.assertTrue(entered.wait(1))
        second = threading.Thread(target=lambda: results.append(self.service.summarize(self.article, 'a')))
        second.start()
        release.set()
        thread.join(3); second.join(3)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(self.calls), 1)

    def test_cache_content_change_invalidates_result(self):
        self.service.summarize(self.article, 'a')
        self.service.fetch = lambda url: {'text': TEXT + ' Changed.', 'coverage': 'excerpt only', 'source_url': url, 'final_url': url}
        result = self.service.summarize(self.article, 'a')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result['coverage'], 'excerpt only')
