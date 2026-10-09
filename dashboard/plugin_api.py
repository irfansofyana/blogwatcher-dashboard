"""Authenticated Hermes dashboard routes; all storage changes go through Blogwatcher CLI."""

from pathlib import Path
import sys

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Dashboard modules are imported by path, separately from the agent package.
# Temporarily expose this plugin's root so both entrypoints use the same adapter.
ROOT = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, ROOT)
try:
    from blogwatcher_core import BlogwatcherCLI, BlogwatcherError
    from article_content import ContentError
    from article_summary import SummaryError, profile_service, model_configuration
finally:
    sys.path.remove(ROOT)

router = APIRouter()


def _apply(action, *args, **kwargs):
    try:
        return {"message": getattr(BlogwatcherCLI(), action)(*args, **kwargs)}
    except BlogwatcherError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class AddBody(BaseModel):
    name: str
    url: str
    feed_url: str | None = None
    scrape_selector: str | None = None
    user_agent: str | None = None


class RemoveBody(BaseModel):
    name: str
    confirm: bool = False


class ScanBody(BaseModel):
    blog: str | None = None


class ArticleBody(BaseModel):
    article_id: int = Field(gt=0)


class SummaryBody(ArticleBody):
    consent: bool = False


@router.post("/articles/summary")
def summarize_article(body: SummaryBody):
    if not body.consent:
        raise HTTPException(status_code=400, detail="Confirm sending retrieved article text to your configured Hermes model provider")
    try:
        article = next((a for a in BlogwatcherCLI().articles(all_articles=True) if a['id'] == body.article_id), None)
        if article is None:
            raise HTTPException(status_code=404, detail="Article no longer exists in Blogwatcher")
        return profile_service().summarize(article, model_configuration())
    except BlogwatcherError as exc:
        raise HTTPException(status_code=502, detail={'code': 'cli_failed', 'message': str(exc)}) from exc
    except (ContentError, SummaryError) as exc:
        status = 429 if exc.code == 'summary_busy' else 502
        raise HTTPException(status_code=status, detail={'code': exc.code, 'message': str(exc)}) from exc


class ReadAllBody(BaseModel):
    blog: str | None = None
    confirm: bool = False


@router.get("/health")
def get_health():
    try:
        sources = BlogwatcherCLI().blogs()
        return {"ok": True, "sources": len(sources)}
    except BlogwatcherError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/blogs")
def get_blogs():
    try:
        return {"items": BlogwatcherCLI().blogs()}
    except BlogwatcherError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/articles")
def get_articles(all_articles: bool = False, blog: str | None = None, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    # FastAPI supplies defaults at request time; direct calls in tests pass ints.
    try:
        articles = BlogwatcherCLI().articles(all_articles=all_articles, blog=blog)
        return {"items": articles[offset:offset + limit], "total": len(articles), "offset": offset, "limit": limit}
    except BlogwatcherError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/blogs")
def add_blog(body: AddBody):
    return _apply("add", body.name, body.url, feed_url=body.feed_url, scrape_selector=body.scrape_selector, user_agent=body.user_agent)


@router.post("/blogs/remove")
def remove_blog(body: RemoveBody):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm removal of this source and all its articles")
    return _apply("remove", body.name)


@router.post("/scan")
def scan(body: ScanBody):
    return _apply("scan", body.blog)


@router.post("/articles/read")
def mark_read(body: ArticleBody):
    return _apply("read", body.article_id)


@router.post("/articles/unread")
def mark_unread(body: ArticleBody):
    return _apply("unread", body.article_id)


@router.post("/articles/read-all")
def mark_all_read(body: ReadAllBody):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm marking all articles read")
    return _apply("read_all", body.blog)
