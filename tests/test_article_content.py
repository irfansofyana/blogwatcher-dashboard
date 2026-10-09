import unittest
from unittest.mock import patch
from article_content import ContentError, public_target, extract_text, _fetch_article

class ContentTests(unittest.TestCase):
    def test_private_and_mapped_destinations_are_blocked(self):
        for address in ['127.0.0.1', '169.254.169.254', '10.0.0.1', '::1', '::ffff:127.0.0.1']:
            with self.subTest(address=address), self.assertRaises(ContentError):
                public_target('https://example.org/story', addresses=[address])

    def test_public_ip_is_selected_and_host_preserved(self):
        self.assertEqual(public_target('https://example.org/story', addresses=['93.184.216.34']), ('example.org', 443, '93.184.216.34'))

    def test_ipv4_is_preferred_when_ipv6_connectivity_is_unavailable(self):
        target = public_target('https://example.org/story', addresses=['2606:4700::1111', '93.184.216.34'])
        self.assertEqual(target[2], '93.184.216.34')

    def test_credentials_and_nonstandard_ports_blocked(self):
        for url in ['file:///etc/passwd', 'http://user:pass@example.org', 'https://example.org:8080', 'http://[broken']:
            with self.assertRaises(ContentError):
                public_target(url, addresses=['93.184.216.34'])

    def test_article_extraction_ignores_scripts_and_navigation(self):
        body = '<nav>Ignore nav</nav><article><h1>Title</h1><p>' + ('Reliable systems need bounded work. ' * 20) + '</p><script>ignore script</script></article>'
        result = extract_text(body)
        self.assertIn('Reliable systems', result['text'])
        self.assertNotIn('ignore script', result['text'])
        self.assertNotIn('Ignore nav', result['text'])
        self.assertEqual(result['coverage'], 'extracted article text')

    def test_insufficient_text_is_not_a_summary_input(self):
        with self.assertRaises(ContentError):
            extract_text('<html><title>A headline</title><p>Log in</p></html>')

    def test_long_input_is_labeled_excerpt(self):
        result = extract_text('<article><p>' + ('word ' * 10000) + '</p></article>')
        self.assertLessEqual(len(result['text']), 30000)
        self.assertEqual(result['coverage'], 'excerpt only')

    def test_worker_deadline_interrupts_slow_headers(self):
        import sys, time
        from article_content import run_fetch_worker
        # The worker is stuck receiving headers trickled faster than a socket timeout.
        code = '''import socket,threading,time,http.client
left,right=socket.socketpair()
def trickle():
 right.sendall(b"HTTP/1.1 200 OK\\r\\n")
 for i in range(100):
  time.sleep(.04)
  right.sendall(b"X-Trickle: yes\\r\\n")
threading.Thread(target=trickle,daemon=True).start()
connection=http.client.HTTPConnection("example.org")
connection.sock=left
left.settimeout(.15)
connection.request("GET", "/")
connection.getresponse()
'''
        started = time.monotonic()
        with self.assertRaises(ContentError) as error:
            run_fetch_worker([sys.executable, '-c', code], timeout=.15)
        self.assertEqual(error.exception.code, 'fetch_timeout')
        self.assertLess(time.monotonic() - started, 1)

    def test_redirect_to_private_network_is_blocked_before_second_connection(self):
        connections = []
        class Response:
            status = 302
            def getheader(self, name, default=None):
                return 'http://169.254.169.254/latest/' if name == 'Location' else default
        class Connection:
            sock = None
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        def factory(*args):
            connections.append(args)
            return Connection()
        def resolve(host, *args):
            return ['169.254.169.254'] if host == '169.254.169.254' else ['93.184.216.34']
        with patch('article_content._resolve', resolve), self.assertRaises(ContentError):
            _fetch_article('https://example.org/post', connection_factory=factory)
        self.assertEqual(len(connections), 1)
