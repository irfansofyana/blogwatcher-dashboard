"""Bounded public-web retrieval. Connections pin vetted IPs, never re-resolve hosts."""
import http.client
import ipaddress
import json
import socket
import ssl
import subprocess
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin

MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 30000
FETCH_SECONDS = 20

class ContentError(RuntimeError):
    def __init__(self, message, code='content_unavailable'):
        super().__init__(message)
        self.code = code


def _resolve(host, port, timeout):
    # DNS has no portable socket deadline; a disposable resolver process bounds it.
    code = 'import socket,json,sys; print(json.dumps(list({x[4][0] for x in socket.getaddrinfo(sys.argv[1],int(sys.argv[2]),type=socket.SOCK_STREAM)})))'
    try:
        result = subprocess.run([sys.executable, '-c', code, host, str(port)], capture_output=True, text=True, timeout=max(.1, timeout), check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError) as exc:
        raise ContentError('Could not resolve the article host', 'fetch_failed') from exc


def public_target(url, addresses=None, timeout=5.0):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if parsed.scheme not in ('http', 'https') or not host or parsed.username or parsed.password or port not in (80, 443):
            raise ValueError('Invalid URL')
        if any(ord(c) < 32 for c in url):
            raise ValueError('Control characters')
        addresses = addresses if addresses is not None else _resolve(host, port, timeout)
        if not addresses:
            raise ValueError('No addresses')
        for value in addresses:
            ip = ipaddress.ip_address(value)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if not ip.is_global or ip.is_multicast:
                raise ValueError('Not public')
        addresses = sorted(addresses, key=lambda value: ipaddress.ip_address(value).version)
        return host, port, addresses[0]
    except ValueError as exc:
        raise ContentError('Article URL is not a permitted public HTTP(S) destination', 'unsafe_url') from exc


class _ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.all_text = []
        self.article_text = []

    def handle_starttag(self, tag, attrs):
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            pos = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[pos:]

    def handle_data(self, data):
        if any(x in self.stack for x in ('script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'head')):
            return
        if data.strip():
            self.all_text.append(data.strip())
            if 'article' in self.stack or 'main' in self.stack:
                self.article_text.append(data.strip())


def extract_text(body, plain=False):
    semantic = False
    if plain:
        text = ' '.join(body.split())
    else:
        parser = _ArticleParser()
        parser.feed(body)
        semantic = bool(parser.article_text)
        # Prefer semantic content; fallback is explicitly weaker coverage.
        text = ' '.join(parser.article_text or parser.all_text)
    if len(text) < 400 or len(text.split()) < 60:
        raise ContentError('Not enough readable article text; open the original website')
    coverage = 'excerpt only' if len(text) > MAX_TEXT or (not plain and not semantic) else 'extracted article text'
    return {'text': text[:MAX_TEXT], 'coverage': coverage}


def fetch_article(url, connection_factory=None):
    deadline = time.monotonic() + FETCH_SECONDS
    original = url
    for hop in range(4):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ContentError('Article retrieval timed out', 'fetch_timeout')
        host, port, ip = public_target(url, timeout=min(5, remaining))
        parsed = urlsplit(url)
        remaining = deadline - time.monotonic()
        conn = connection_factory(host, port, ip, parsed.scheme, remaining) if connection_factory else http.client.HTTPConnection(host, port, timeout=max(.1, remaining))
        try:
            if connection_factory is None:
                conn.sock = socket.create_connection((ip, port), timeout=max(.1, remaining))
                if parsed.scheme == 'https':
                    conn.sock = ssl.create_default_context().wrap_socket(conn.sock, server_hostname=host)
            path = parsed.path or '/'
            if parsed.query:
                path += '?' + parsed.query
            conn.request('GET', path, headers={'User-Agent': 'Blogwatcher-Hermes/0.2', 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location or hop == 3:
                    raise ContentError('Too many or invalid article redirects', 'fetch_failed')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ContentError(f'Publisher returned HTTP {response.status}; open the original website', 'fetch_failed')
            kind = response.getheader('Content-Type', '').split(';')[0].strip().lower()
            if kind not in ('text/html', 'application/xhtml+xml', 'text/plain'):
                raise ContentError('Publisher did not return readable HTML or text')
            if response.getheader('Content-Encoding', 'identity').lower() not in ('identity', ''):
                raise ContentError('Publisher returned unsupported compressed content')
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ContentError('Article retrieval timed out', 'fetch_timeout')
                if conn.sock:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ContentError('Article response exceeded the size limit', 'content_too_large')
                chunks.append(chunk)
            raw = b''.join(chunks).decode('utf-8', errors='replace')
            lower = raw[:15000].lower()
            if any(marker in lower for marker in ('cf-chl-', 'verify you are human', 'enable javascript and cookies to continue', 'just a moment...')):
                raise ContentError('Publisher blocked automated reading; open the original website', 'publisher_blocked')
            result = extract_text(raw, plain=kind == 'text/plain')
            return {**result, 'source_url': original, 'final_url': url}
        except ContentError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise ContentError('Could not retrieve the article; try again or open the original', 'fetch_failed') from exc
        finally:
            conn.close()
    raise ContentError('Could not retrieve article')
