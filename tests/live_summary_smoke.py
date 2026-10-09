"""Opt-in live summary through the production API in an isolated plugin host.
Uses Hermes-owned auth, read-only original CLI, and a public subscribed article.
Run with HERMES_BRIDGE_LIVE=1 and the Hermes runtime on PYTHONPATH.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path


def main():
    if os.environ.get('HERMES_BRIDGE_LIVE') != '1':
        raise SystemExit('Set HERMES_BRIDGE_LIVE=1 to authorize one paid live smoke test')
    from hermes_constants import get_hermes_home
    from hermes_cli.plugins import PluginManager, PluginManifest, PluginContext
    from blogwatcher_core import BlogwatcherCLI
    root = Path(__file__).resolve().parents[1]
    items = BlogwatcherCLI().articles(all_articles=True)
    article = next(a for a in items if a['blog'] == 'Simon Willison')
    home = str(get_hermes_home())
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'), prefix='blogwatcher-live-') as tmp:
        package = Path(tmp) / 'blogwatcher-dashboard'
        shutil.copytree(root, package, ignore=shutil.ignore_patterns('.git', '__pycache__', '.superpowers'))
        manager = PluginManager(scope_key=home)
        host = manager._plugin_host()
        manifest = PluginManifest(name='blogwatcher-dashboard', version='0.2.0', path=str(package), source='user')
        try:
            host.load(manifest, PluginContext(manifest, manager), module_name=manager._directory_module_name(manifest), entrypoint=False)
            payload = json.dumps({'article_id': article['id'], 'consent': True}).encode()
            result = host.asgi_request('blogwatcher-dashboard', str(package / 'dashboard'), 'plugin_api.py', 'POST', '/articles/summary', '', [('Content-Type', 'application/json')], payload)
            answer = json.loads(result['body'])
            if result['status'] != 200:
                raise RuntimeError(f'HTTP {result["status"]}: {answer}')
            assert answer['text'].strip()
            print(json.dumps({'status': result['status'], 'provider': answer['provider'], 'model': answer['model'], 'coverage': answer['coverage'], 'cached': answer['cached'], 'source_url': answer['source_url'], 'text': answer['text']}, ensure_ascii=False))
        finally:
            manager.unload()
            process = host._proc
            host.shutdown()
            if process:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream and not stream.closed:
                        stream.close()


if __name__ == '__main__':
    main()
