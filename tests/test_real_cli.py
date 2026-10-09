import os
import shutil
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from blogwatcher_core import BlogwatcherCLI


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RealCLITests(unittest.TestCase):
    def test_original_cli_lifecycle_in_isolated_database(self):
        binary = os.environ.get('BLOGWATCHER_TEST_BIN') or shutil.which('blogwatcher')
        if not binary or not Path(binary).is_file():
            self.skipTest('Original blogwatcher binary not installed')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'feed.xml').write_text('''<?xml version="1.0"?>
<rss version="2.0"><channel><title>Fixture feed</title><link>http://example.org</link><description>Fixture</description>
<item><title>One article</title><link>https://example.org/one</link><guid>https://example.org/one</guid><pubDate>Fri, 09 Oct 2026 12:00:00 GMT</pubDate><description>Preview text</description></item>
</channel></rss>''')
            from functools import partial
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=tmp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            url = f'http://127.0.0.1:{server.server_port}/feed.xml'
            cli = BlogwatcherCLI(binary=binary, database=str(root / 'isolated.db'))
            cli.add('Fixture', url, feed_url=url)
            self.assertEqual(len(cli.blogs()), 1)
            cli.scan('Fixture')
            articles = cli.articles()
            self.assertEqual(len(articles), 1)
            self.assertEqual(articles[0]['title'], 'One article')
            article_id = articles[0]['id']
            cli.read(article_id)
            self.assertEqual(len(cli.articles()), 0)
            cli.unread(article_id)
            self.assertEqual(len(cli.articles()), 1)
            cli.read_all('Fixture')
            self.assertEqual(len(cli.articles()), 0)
            cli.remove('Fixture')
            self.assertEqual(len(cli.blogs()), 0)


if __name__ == '__main__':
    unittest.main()
