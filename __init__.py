"""Read-only Hermes agent tools for the original Blogwatcher CLI.

Writes belong to the user-clicked dashboard, not to model-supplied confirmation.
"""

import json
from .blogwatcher_core import BlogwatcherCLI, BlogwatcherError


def _call(method, params, keys):
    try:
        kwargs = {key: params[key] for key in keys if key in params}
        result = getattr(BlogwatcherCLI(), method)(**kwargs)
        if method == "articles":
            offset, limit = params.get("offset", 0), params.get("limit", 50)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise BlogwatcherError("Invalid article pagination")
            result = {"items": result[offset:offset + limit], "total": len(result), "offset": offset, "limit": limit}
        return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
    except (BlogwatcherError, TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def register(ctx):
    commands = [
        ("blogwatcher_list_sources", "List subscribed sources in the original Blogwatcher CLI.", "blogs", {}),
        ("blogwatcher_list_articles", "List original Blogwatcher articles. Unread by default; returns up to 50 article IDs and URLs for citation (limit 100).", "articles", {"all_articles": {"type": "boolean"}, "blog": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
    ]
    for name, description, method, fields in commands:
        keys = [key for key in fields if key not in ("offset", "limit")]
        def handler(params, _method=method, _keys=keys, **kwargs):
            return _call(_method, params, _keys)
        ctx.register_tool(
            name=name,
            toolset="blogwatcher_dashboard",
            schema={"name": name, "description": description, "parameters": {"type": "object", "properties": fields, "required": [], "additionalProperties": False}},
            handler=handler,
        )
