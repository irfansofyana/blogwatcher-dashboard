"""Profile-local, bounded on-demand summaries; cache only verified successful results."""
import hashlib
import json
import os
import threading
import uuid
import time
from concurrent.futures import Future, TimeoutError
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
        self.inflight = {}

    def saved_summary(self, article):
        """Read existing successful results without publisher access or inference."""
        answers = []
        for path in self.directory.glob('*.json'):
            data = self._read(path, allow_stale=True)
            if data and data.get('source_url') == article.get('url'):
                answers.append(data)
        if not answers:
            return None
        result = max(answers, key=lambda item: item['generated_at'])
        return {**result, 'cached': True, 'stale': time.time() - result['generated_at'] >= TTL}

    def summarize(self, article, configuration, regenerate=False):
        if not article.get('url'):
            raise SummaryError('This article has no permitted website URL', 'unsafe_url')
        identity = (article['url'], configuration, bool(regenerate))
        with self.guard:
            owner = identity not in self.inflight
            record = self.inflight.setdefault(identity, {'future': Future(), 'users': 0})
            record['users'] += 1
            future = record['future']
        try:
            if owner:
                if not self.slots.acquire(blocking=False):
                    future.set_exception(SummaryError('Two summaries are already running. Try again shortly.', 'summary_busy'))
                else:
                    try:
                        future.set_result(self._run(article, configuration, regenerate))
                    except Exception as exc:
                        future.set_exception(exc)
                    finally:
                        self.slots.release()
            try:
                return future.result(timeout=85)
            except TimeoutError as exc:
                raise SummaryError('A summary is still running. The host may have retried; refresh before requesting it again.', 'summary_busy') from exc
        finally:
            with self.guard:
                record['users'] -= 1
                if record['users'] == 0:
                    del self.inflight[identity]

    def _run(self, article, configuration, regenerate=False):
        try:
            content = self.fetch(article['url'])
            retrieved_at = time.time()
            digest = hashlib.sha256(content['text'].encode()).hexdigest()
            key = hashlib.sha256(json.dumps([article['url'], digest, configuration, PROMPT_VERSION]).encode()).hexdigest()
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self.directory / (key + '.json')
            cached = self._read(path)
            if cached and not regenerate:
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
            raise SummaryError('Summary generation failed or timed out. The plugin did not retry; Hermes may have retried or used fallback models, consuming tokens.', 'model_failed') from exc

    def _read(self, path, allow_stale=False):
        try:
            # 16k Unicode characters can require 64k UTF-8 bytes, plus metadata.
            if path.stat().st_size > 128000:
                return None
            data = json.loads(path.read_text())
            if (allow_stale or time.time() - data['generated_at'] < TTL) and isinstance(data['text'], str) and data['text'].strip():
                if not isinstance(data['generated_at'], (int, float)):
                    return None
                return data
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return None

    def _write(self, path, answer):
        temporary = path.with_suffix('.' + uuid.uuid4().hex + '.pending')
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
