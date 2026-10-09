"""Allowlisted adapter for the original Hyaxia/blogwatcher CLI.

No SQLite access. The user-provided binary path and BLOGWATCHER_DB refer to the
same installation that a shell invocation would use.
"""

import os
import re
import shutil
import subprocess
from urllib.parse import urlsplit


class BlogwatcherError(RuntimeError):
    pass


_ARTICLE = re.compile(r"^\s{2}\[(\d+)\] \[(new|read)\] (.+?)\s*$")
_COUNT = re.compile(r"^(?:Unread|All) articles \((\d+)\):$")
_BLOG_COUNT = re.compile(r"^Tracked blogs \((\d+)\):$")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean(text):
    return _ANSI.sub("", text).replace("\r", "")


def parse_articles(text):
    lines = _clean(text).splitlines()
    if not lines:
        raise BlogwatcherError("Empty blogwatcher article output")
    if len(lines) == 1 and lines[0].strip() in ("No unread articles.", "No unread articles!", "No articles found.", "No articles.", "No articles found!"):
        return []
    count = _COUNT.fullmatch(lines[0].strip())
    if not count:
        raise BlogwatcherError("Unsupported blogwatcher article output")
    items = []
    current = None
    for line in lines[1:]:
        if not line.strip():
            continue
        header = _ARTICLE.match(line)
        if header:
            if current:
                _require_article(current, items)
            current = {"id": int(header[1]), "status": header[2], "title": header[3]}
        elif current and line.startswith("       ") and ": " in line:
            key, value = line.strip().split(": ", 1)
            if key in ("Blog", "URL", "Published"):
                current[key.lower()] = value
        else:
            raise BlogwatcherError("Unsupported blogwatcher article output")
    if current:
        _require_article(current, items)
    if len(items) != int(count[1]):
        # The CLI normally prints every listed article. Never silently return
        # a subset when upstream output changed or was truncated.
        raise BlogwatcherError("Blogwatcher article count did not match output")
    return items


def _require_article(article, items):
    if not all(article.get(k) for k in ("title", "blog", "url")):
        raise BlogwatcherError("Incomplete blogwatcher article output")
    try:
        _url(article["url"])
    except BlogwatcherError:
        article["url"] = None
    items.append(article)


def parse_blogs(text):
    lines = _clean(text).splitlines()
    if not lines:
        raise BlogwatcherError("Empty blogwatcher blog output")
    if len(lines) == 1 and lines[0].strip() in ("No blogs tracked.", "No blogs tracked yet.", "No blogs tracked yet. Use 'blogwatcher add' to add one."):
        return []
    count = _BLOG_COUNT.fullmatch(lines[0].strip())
    if not count:
        raise BlogwatcherError("Unsupported blogwatcher blog output")
    items = []
    current = None
    for line in lines[1:]:
        if not line.strip():
            continue
        if line.startswith("  ") and not line.startswith("    "):
            if current:
                _require_blog(current, items)
            current = {"name": line.strip()}
        elif current and line.startswith("    ") and ": " in line:
            key, value = line.strip().split(": ", 1)
            if key in ("URL", "Feed", "Last scanned", "Scrape selector", "User-Agent"):
                current[{"Last scanned": "last_scanned", "Scrape selector": "scrape_selector", "User-Agent": "user_agent"}.get(key, key.lower())] = value
        else:
            raise BlogwatcherError("Unsupported blogwatcher blog output")
    if current:
        _require_blog(current, items)
    if len(items) != int(count[1]):
        raise BlogwatcherError("Blogwatcher blog count did not match output")
    return items


def _require_blog(blog, items):
    if not blog.get("url"):
        raise BlogwatcherError("Incomplete blogwatcher blog output")
    try:
        _url(blog["url"])
    except BlogwatcherError:
        blog["url"] = None
    items.append(blog)


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise BlogwatcherError(f"Invalid {label}")
    value = value.strip()
    if label == "blog name" and value.startswith("-"):
        raise BlogwatcherError("Blog names must not begin with a dash")
    return value


def _url(value):
    value = _text(value, "URL")
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
    except ValueError:
        valid = False
    if not valid:
        raise BlogwatcherError("URL must be an http(s) address without credentials")
    return value


def _id(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d*", str(value)):
        raise BlogwatcherError("Invalid article ID")
    return str(value)


class BlogwatcherCLI:
    def __init__(self, binary=None, database=None):
        self.binary = binary or os.environ.get("BLOGWATCHER_BIN", "blogwatcher")
        self.database = database

    def _run(self, *args, timeout=30):
        binary = self.binary if os.path.isabs(self.binary) else shutil.which(self.binary)
        if not binary or not os.path.isfile(binary) or not os.access(binary, os.X_OK):
            raise BlogwatcherError(f"Blogwatcher CLI not found: {self.binary}")
        env = os.environ.copy()
        if self.database is not None:
            env["BLOGWATCHER_DB"] = self.database
        try:
            result = subprocess.run([binary, *args], shell=False, env=env, capture_output=True, text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired as exc:
            raise BlogwatcherError("Blogwatcher CLI timed out") from exc
        except OSError as exc:
            raise BlogwatcherError(f"Blogwatcher CLI failed to start: {exc}") from exc
        if len(result.stdout) + len(result.stderr) > 16_000_000:
            raise BlogwatcherError("Blogwatcher output too large")
        if result.returncode != 0:
            raise BlogwatcherError(_clean(result.stderr or result.stdout).strip()[:500] or f"Blogwatcher exited {result.returncode}")
        return _clean(result.stdout)

    def blogs(self):
        return parse_blogs(self._run("blogs"))

    def articles(self, all_articles=False, blog=None):
        args = ["articles"]
        if all_articles:
            args.append("--all")
        if blog:
            args += ["--blog", _text(blog, "blog name")]
        return parse_articles(self._run(*args))

    def add(self, name, url, feed_url=None, scrape_selector=None, user_agent=None):
        args = ["add", _text(name, "blog name"), _url(url)]
        if feed_url:
            args += ["--feed-url", _url(feed_url)]
        if scrape_selector:
            args += ["--scrape-selector", _text(scrape_selector, "scrape selector")]
        if user_agent:
            args += ["--user-agent", _text(user_agent, "user agent")]
        return self._run(*args, timeout=60).strip()

    def remove(self, name):
        return self._run("remove", _text(name, "blog name"), "--yes").strip()

    def scan(self, blog=None):
        args = ["scan"] + ([_text(blog, "blog name")] if blog else [])
        return self._run(*args, timeout=180).strip()

    def read(self, article_id):
        return self._run("read", _id(article_id)).strip()

    def unread(self, article_id):
        return self._run("unread", _id(article_id)).strip()

    def read_all(self, blog=None):
        args = ["read-all", "--yes"]
        if blog:
            args += ["--blog", _text(blog, "blog name")]
        return self._run(*args).strip()
