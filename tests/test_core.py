import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from blogwatcher_core import BlogwatcherCLI, BlogwatcherError, parse_articles, parse_blogs


class ParsingTests(unittest.TestCase):
    def test_articles_are_structured_and_status_preserved(self):
        text = """Unread articles (2):

  [42] [new] Hello <world>
       Blog: Example
       URL: https://example.org/post?a=1
       Published: 2026-10-09

  [43] [read] Other story
       Blog: Another
       URL: https://another.org/2
       Published: 2026-10-08
"""
        articles = parse_articles(text)
        self.assertEqual(articles[0], {"id": 42, "status": "new", "title": "Hello <world>", "blog": "Example", "url": "https://example.org/post?a=1", "published": "2026-10-09"})
        self.assertEqual(articles[1]["status"], "read")

    def test_blogs_are_structured(self):
        text = """Tracked blogs (1):

  My Blog
    URL: https://example.org
    Feed: https://example.org/rss.xml
    Last scanned: 2026-10-09 20:34
"""
        self.assertEqual(parse_blogs(text), [{"name": "My Blog", "url": "https://example.org", "feed": "https://example.org/rss.xml", "last_scanned": "2026-10-09 20:34"}])

    def test_changed_format_is_error_not_empty_inbox(self):
        with self.assertRaises(BlogwatcherError):
            parse_articles("Unread articles (3):\n  Something unexpected\n")

    def test_empty_stdout_fails_closed(self):
        for parser in (parse_articles, parse_blogs):
            with self.assertRaises(BlogwatcherError):
                parser("")

    def test_empty_result_is_not_error(self):
        self.assertEqual(parse_articles("No unread articles.\n"), [])
        self.assertEqual(parse_blogs("No blogs tracked.\n"), [])

    def test_untrusted_article_url_is_not_openable(self):
        text = "Unread articles (1):\n\n  [4] [new] Unsafe link\n       Blog: Example\n       URL: javascript:alert(1)\n       Published: 2026-10-09\n"
        self.assertIsNone(parse_articles(text)[0]["url"])
        self.assertIsNone(parse_articles(text.replace("javascript:alert(1)", "http://[broken"))[0]["url"])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.cli = self.path / "fake-blogwatcher"
        self.log = self.path / "argv.json"
        self.cli.write_text(f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\nPath(os.environ['FAKE_LOG']).write_text(json.dumps(sys.argv[1:]))\nprint('Tracked blogs (0):')\n")
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IXUSR)
        self.previous = os.environ.get("FAKE_LOG")
        os.environ["FAKE_LOG"] = str(self.log)
        self.addCleanup(self.restore_env)

    def restore_env(self):
        if self.previous is None:
            os.environ.pop("FAKE_LOG", None)
        else:
            os.environ["FAKE_LOG"] = self.previous

    def test_source_name_does_not_become_shell_fragment(self):
        client = BlogwatcherCLI(binary=str(self.cli), database=str(self.path / "test.db"))
        client.add("quoted'; touch /tmp/no", "https://example.org", feed_url="https://example.org/feed")
        self.assertEqual(json.loads(self.log.read_text()), ["add", "quoted'; touch /tmp/no", "https://example.org", "--feed-url", "https://example.org/feed"])

    def test_invalid_article_id_rejected_before_execution(self):
        client = BlogwatcherCLI(binary=str(self.cli))
        with self.assertRaises(BlogwatcherError):
            client.read("1; echo pwn")
        self.assertFalse(self.log.exists())

    def test_flag_like_source_name_rejected_before_execution(self):
        client = BlogwatcherCLI(binary=str(self.cli))
        with self.assertRaises(BlogwatcherError):
            client.add("--help", "https://example.org")
        self.assertFalse(self.log.exists())

    def test_missing_binary_is_error(self):
        client = BlogwatcherCLI(binary=str(self.path / "missing"))
        with self.assertRaisesRegex(BlogwatcherError, "not found"):
            client.blogs()

    def test_nonzero_exit_is_error(self):
        self.cli.write_text(f"#!{sys.executable}\nimport sys\nprint('invalid command', file=sys.stderr)\nsys.exit(2)\n")
        with self.assertRaisesRegex(BlogwatcherError, "invalid command"):
            BlogwatcherCLI(binary=str(self.cli)).blogs()


if __name__ == "__main__":
    unittest.main()
