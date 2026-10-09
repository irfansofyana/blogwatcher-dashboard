import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_package():
    spec = importlib.util.spec_from_file_location("blogwatcher_dashboard_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ToolTests(unittest.TestCase):
    def test_tools_have_narrow_names_and_delegate_to_cli(self):
        module = load_package()
        captured = {}
        class Context:
            def register_tool(self, **kwargs):
                captured[kwargs["name"]] = kwargs
        module.register(Context())
        self.assertIn("blogwatcher_list_articles", captured)
        self.assertEqual(set(captured), {"blogwatcher_list_articles", "blogwatcher_list_sources"})
        self.assertNotIn("blogwatcher_run_command", captured)
        with patch.object(module, "BlogwatcherCLI") as factory:
            factory.return_value.articles.return_value = [{"id": 1, "title": "Hello"}]
            result = captured["blogwatcher_list_articles"]["handler"]({"all_articles": False})
            self.assertIn('"Hello"', result)


    def test_agent_article_results_are_bounded(self):
        module = load_package()
        captured = {}
        class Context:
            def register_tool(self, **kwargs):
                captured[kwargs["name"]] = kwargs
        module.register(Context())
        with patch.object(module, "BlogwatcherCLI") as factory:
            factory.return_value.articles.return_value = [{"id": i} for i in range(200)]
            import json
            result = json.loads(captured["blogwatcher_list_articles"]["handler"]({"limit": 10}))
            self.assertEqual(len(result["result"]["items"]), 10)
            self.assertEqual(result["result"]["total"], 200)


class ApiTests(unittest.TestCase):
    def test_saved_summary_http_lookup_and_explicit_regenerate(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from dashboard.plugin_api import router
        app = FastAPI(); app.include_router(router)
        client = TestClient(app)
        article = {'id': 1, 'url': 'https://example.org/one'}
        with patch('dashboard.plugin_api.BlogwatcherCLI') as cli, patch('dashboard.plugin_api.profile_service') as service, patch('dashboard.plugin_api.model_configuration', return_value='a'):
            cli.return_value.articles.return_value = [article]
            service.return_value.saved_summary.return_value = {'text': 'Saved', 'cached': True}
            response = client.get('/articles/1/summary')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['summary']['text'], 'Saved')
            service.return_value.summarize.assert_not_called()
            service.return_value.summarize.return_value = {'text': 'Fresh'}
            response = client.post('/articles/summary', json={'article_id': 1, 'consent': True, 'regenerate': True})
            self.assertEqual(response.status_code, 200)
            service.return_value.summarize.assert_called_once_with(article, 'a', regenerate=True)
            self.assertEqual(client.get('/articles/2/summary').status_code, 404)

    def test_summary_requires_consent_before_lookup(self):
        from fastapi import HTTPException
        from dashboard.plugin_api import SummaryBody, summarize_article
        with patch('dashboard.plugin_api.BlogwatcherCLI') as cli:
            with self.assertRaises(HTTPException) as error:
                summarize_article(SummaryBody(article_id=1, consent=False))
            self.assertEqual(error.exception.status_code, 400)
            cli.assert_not_called()

    def test_removed_article_cannot_be_summarized(self):
        from fastapi import HTTPException
        from dashboard.plugin_api import SummaryBody, summarize_article
        with patch('dashboard.plugin_api.BlogwatcherCLI') as cli:
            cli.return_value.articles.return_value = []
            with self.assertRaises(HTTPException) as error:
                summarize_article(SummaryBody(article_id=1, consent=True))
            self.assertEqual(error.exception.status_code, 404)

    def test_api_routes_provide_inbox_and_mutations(self):
        from dashboard.plugin_api import router
        paths = {(r.path, method) for r in router.routes for method in r.methods}
        for route in [('/articles', 'GET'), ('/blogs', 'GET'), ('/blogs', 'POST'), ('/blogs/remove', 'POST'), ('/scan', 'POST'), ('/articles/read', 'POST'), ('/articles/unread', 'POST'), ('/articles/read-all', 'POST')]:
            self.assertIn(route, paths)

    def test_remove_needs_confirmation(self):
        from fastapi import HTTPException
        from dashboard.plugin_api import RemoveBody, remove_blog
        with patch("dashboard.plugin_api.BlogwatcherCLI") as factory:
            with self.assertRaises(HTTPException) as err:
                remove_blog(RemoveBody(name="Example", confirm=False))
            self.assertEqual(err.exception.status_code, 400)
            factory.assert_not_called()

    def test_articles_are_paginated_after_cli_read(self):
        from dashboard.plugin_api import get_articles
        with patch("dashboard.plugin_api.BlogwatcherCLI") as factory:
            factory.return_value.articles.return_value = [{"id": i} for i in range(10)]
            result = get_articles(all_articles=False, blog=None, offset=3, limit=2)
            self.assertEqual(result, {"items": [{"id": 3}, {"id": 4}], "total": 10, "offset": 3, "limit": 2})


if __name__ == "__main__":
    unittest.main()
