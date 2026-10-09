"""Profile-local, bounded on-demand summaries; cache only verified successful results."""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from article_content import fetch_article, ContentError

PROMPT_VERSION = 'article-overview-v1'
TTL = 7 * 24 * 60 * 60
MAX_CACHE = 50 * 1024 * 1024

class SummaryError(RuntimeError):
    def __init__(self, message, code='summary_failed'):
        super().__init__(message)
        self.code = code


def _generate(text, url):
    try:
        from blogwatcher_dashboard_summary_bridge import summarize_text
    except ImportError as exc:
        raise SummaryError('Hermes summary capability is not loaded. Enable the backend plugin and restart the dashboard.', 'capability_unavailable') from exc
    return summarize_text(text, url)


class SummaryService:
    def __init__(self, directory, fetch=fetch_article, generate=_generate):
        self.directory = Path(directory)
        self.fetch = fetch
        self.generate = generate
        self.slots = threading.BoundedSemaphore(2)
        self.guard = threading.Lock()
        self.locks = {}

    def summarize(self, article, configuration):
        if not article.get('url'):
            raise SummaryError('This article has no permitted website URL', 'unsafe_url')
        identity = (article['url'], configuration)
        with self.guard:
            lock, users = self.locks.get(identity, (threading.Lock(), 0))
            self.locks[identity] = (lock, users + 1)
        try:
            if not lock.acquire(timeout=85):
                raise SummaryError('A summary is still running. Refresh before trying again.', 'summary_busy')
            try:
                if not self.slots.acquire(blocking=False):
                    raise SummaryError('Two summaries are already running. Try again shortly.', 'summary_busy')
                try:
                    return self._run(article, configuration)
                finally:
                    self.slots.release()
            finally:
                lock.release()
        finally:
            with self.guard:
                current, users = self.locks[identity]
                if users == 1:
                    del self.locks[identity]
                else:
                    self.locks[identity] = (current, users - 1)

    def _run(self, article, configuration):
        try:
            content = self.fetch(article['url'])
            retrieved_at = time.time()
            digest = hashlib.sha256(content['text'].encode()).hexdigest()
            key = hashlib.sha256(json.dumps([article['url'], digest, configuration, PROMPT_VERSION]).encode()).hexdigest()
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self.directory / (key + '.json')
            cached = self._read(path)
            if cached:
                return {**cached, 'cached': True}
            result = self.generate(content['text'], content['final_url'])
            if not isinstance(result, dict) or not isinstance(result.get('text'), str) or not result['text'].strip() or len(result['text']) > 16000:
                raise SummaryError('The model returned no usable summary. You can retry explicitly.', 'invalid_model_result')
            answer = {
                'text': result['text'].strip(), 'model': result.get('model', ''), 'provider': result.get('provider', ''),
                'source_url': content['source_url'], 'final_url': content['final_url'], 'coverage': content['coverage'],
                'retrieved_at': retrieved_at, 'generated_at': time.time(), 'cached': False,
            }
            self._write(path, answer)
            return answer
        except (ContentError, SummaryError):
            raise
        except Exception as exc:
            # Do not expose provider messages/tokens/paths to the renderer.
            raise SummaryError('Summary generation failed or timed out. No automatic retry was made; the provider may have consumed tokens.', 'model_failed') from exc

    def _read(self, path):
        try:
            if path.stat().st_size > 24000:
                return None
            data = json.loads(path.read_text())
            if time.time() - data['generated_at'] < TTL and isinstance(data['text'], str) and data['text'].strip():
                return data
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return None

    def _write(self, path, answer):
        temporary = path.with_suffix('.pending')
        try:
            temporary.write_text(json.dumps(answer, ensure_ascii=False))
            temporary.chmod(0o600)
            os.replace(temporary, path)
            files = sorted(self.directory.glob('*.json'), key=lambda p: p.stat().st_mtime)
            size = sum(p.stat().st_size for p in files)
            for file in files:
                if size <= MAX_CACHE and time.time() - file.stat().st_mtime < TTL:
                    continue
                size -= file.stat().st_size
                file.unlink(missing_ok=True)
        except OSError:
            # A valid result is still useful if caching fails; report no false cache hit.
            temporary.unlink(missing_ok=True)


_services = {}
_services_lock = threading.Lock()

def profile_service():
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home())
    with _services_lock:
        key = str(home.resolve())
        if key not in _services:
            _services[key] = SummaryService(home / 'cache' / 'blogwatcher-summaries')
        return _services[key]


def model_configuration():
    from hermes_cli.config import load_config
    return json.dumps(load_config().get('model', {}), sort_keys=True, default=str)
