/* Blogwatcher tab for the Hermes web dashboard. No standalone app or chat client. */
(function () {
  'use strict';
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const React = SDK.React;
  const { useState, useEffect, useRef } = SDK.hooks;
  const h = React.createElement;
  const BASE = '/api/plugins/blogwatcher-dashboard';

  function api(route, body) {
    return SDK.fetchJSON(BASE + route, body === undefined ? undefined : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
  }

  function BlogwatcherPage() {
    const [view, setView] = useState('inbox');
    const [mode, setMode] = useState('unread');
    const [blog, setBlog] = useState('');
    const [page, setPage] = useState(0);
    const [articles, setArticles] = useState({ items: [], total: 0 });
    const [sources, setSources] = useState([]);
    const [form, setForm] = useState({ name: '', url: '', feed_url: '', scrape_selector: '', user_agent: '' });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [selected, setSelected] = useState(null);
    const [summary, setSummary] = useState(null);
    const [summaryError, setSummaryError] = useState('');
    const [summarizing, setSummarizing] = useState(false);
    const [loading, setLoading] = useState(true);
    const selection = useRef(0);
    const LIMIT = 50;
    const generation = useRef(0);

    function load() {
      const request = ++generation.current;
      setLoading(true);
      const query = new URLSearchParams({ all_articles: String(mode === 'all'), offset: String(page * LIMIT), limit: String(LIMIT) });
      if (blog) query.set('blog', blog);
      Promise.all([api('/blogs'), api('/articles?' + query.toString())])
        .then(([s, a]) => { if (request !== generation.current) return; setSources(s.items); setArticles(a); setError(''); })
        .catch(e => { if (request === generation.current) setError(e.message || 'Could not load Blogwatcher'); })
        .finally(() => { if (request === generation.current) setLoading(false); });
    }
    useEffect(() => { load(); return () => { generation.current++; }; }, [mode, blog, page]);
    function action(route, body, onSuccess) {
      setBusy(true); setError(''); setNotice('');
      api(route, body).then(result => { if (onSuccess) onSuccess(); setNotice(result.message || 'Done'); load(); })
        .catch(e => setError(e.message || 'Action failed')).finally(() => setBusy(false));
    }
    function confirmAction(message, route, body) {
      if (window.confirm(message)) action(route, { ...body, confirm: true });
    }
    function inspect(article) {
      selection.current++;
      setSelected(article); setSummary(null); setSummaryError(''); setSummarizing(false);
    }
    function summarize() {
      if (!window.confirm('Fetch this article and send its text to your configured Hermes model provider? This may use paid tokens.')) return;
      const request = ++selection.current;
      setSummarizing(true); setSummaryError('');
      api('/articles/summary', { article_id: selected.id, consent: true })
        .then(result => { if (selection.current === request) setSummary(result); })
        .catch(e => { if (selection.current === request) setSummaryError(e.message || 'Could not summarize. No automatic retry was made.'); })
        .finally(() => { if (selection.current === request) setSummarizing(false); });
    }
    const button = (label, onClick, extra = {}) => h('button', { type: 'button', onClick, disabled: busy || extra.disabled, className: 'rounded-md border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50', ...extra }, label);
    const field = (key, label, required = false) => h('label', { key, className: 'flex flex-col gap-1 text-sm' }, label,
      h('input', { className: 'rounded-md border border-border bg-background px-3 py-2', value: form[key], required, maxLength: 1000, onChange: e => setForm({ ...form, [key]: e.target.value }) }));
    const sourceOptions = [h('option', { key: 'all', value: '' }, 'All sources'), ...sources.map(s => h('option', { key: s.name, value: s.name }, s.name))];
    const heading = h('header', { className: 'flex flex-wrap items-center justify-between gap-3' },
      h('div', null, h('h1', { className: 'text-2xl font-semibold' }, 'Blogwatcher'), h('p', { className: 'text-sm text-muted-foreground' }, 'Your original CLI, inside Hermes.')),
      h('div', { className: 'flex gap-2' }, button('Refresh', load), button('Scan now', () => action('/scan', { blog: blog || null })), h('a', { href: '/chat', className: 'rounded-md border border-border px-3 py-2 text-sm hover:bg-muted' }, 'Chat with Hermes')));
    const navigation = h('nav', { className: 'flex gap-2 border-b border-border pb-3' },
      button('Unread', () => { setView('inbox'); setMode('unread'); setPage(0); }),
      button('All articles', () => { setView('inbox'); setMode('all'); setPage(0); }),
      button('Sources', () => setView('sources')));
    const articleView = h('section', { className: 'space-y-3' },
      h('div', { className: 'flex flex-wrap items-center gap-3' },
        h('select', { 'aria-label': 'Filter by source', className: 'rounded-md border border-border bg-background px-3 py-2', value: blog, onChange: e => { setBlog(e.target.value); setPage(0); } }, sourceOptions),
        h('span', { className: 'text-sm text-muted-foreground' }, loading ? 'Loading…' : error ? 'Article count unavailable; displayed data may be stale' : `${articles.total} ${mode === 'unread' ? 'unread' : 'articles'}`),
        button('Mark all read', () => confirmAction(`Mark all ${blog ? 'from ' + blog : 'unread articles'} as read?`, '/articles/read-all', { blog: blog || null }), { disabled: mode !== 'unread' || !articles.total })),
      articles.items.length ? h('ul', { className: 'divide-y divide-border rounded-md border border-border' }, articles.items.map(a =>
        h('li', { key: a.id, className: 'flex flex-wrap items-center justify-between gap-3 p-4' },
          h('div', { className: 'min-w-0 flex-1' }, h('button', { type: 'button', onClick: () => inspect(a), className: 'text-left font-medium underline-offset-4 hover:underline' }, a.title),
            h('div', { className: 'mt-1 text-xs text-muted-foreground' }, `${a.blog} · ${a.published || 'Date unknown'} · #${a.id}`)),
          button(a.status === 'read' ? 'Mark unread' : 'Mark read', () => action(a.status === 'read' ? '/articles/unread' : '/articles/read', { article_id: a.id }))
        ))) : h('p', { className: 'rounded-md border border-border p-6 text-sm text-muted-foreground' }, loading ? 'Loading articles…' : error ? 'Articles could not be loaded. Use Refresh to try again.' : 'No articles in this view.'),
      h('div', { className: 'flex items-center gap-2' }, button('Previous', () => setPage(Math.max(0, page - 1)), { disabled: !page }),
        h('span', { className: 'text-sm' }, `Page ${page + 1}`), button('Next', () => setPage(page + 1), { disabled: (page + 1) * LIMIT >= articles.total })));
    const sourceView = h('section', { className: 'grid gap-5 lg:grid-cols-2' },
      h('div', null, h('h2', { className: 'mb-3 text-lg font-medium' }, `Sources (${sources.length})`),
        h('ul', { className: 'divide-y divide-border rounded-md border border-border' }, sources.map(s =>
          h('li', { key: s.name, className: 'flex items-start justify-between gap-3 p-3' },
            h('div', { className: 'min-w-0' }, h('strong', null, s.name), s.url && h('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer', className: 'block truncate text-xs underline' }, s.url),
              h('p', { className: 'text-xs text-muted-foreground' }, `Feed: ${s.feed || 'Auto-discovery'} · Last scan: ${s.last_scanned || 'Never'}`)),
            button('Remove', () => confirmAction(`Remove ${s.name} and ALL its articles? This cannot be undone.`, '/blogs/remove', { name: s.name })))))),
      h('form', { className: 'flex flex-col gap-3 rounded-md border border-border p-4', onSubmit: e => { e.preventDefault(); action('/blogs', { ...form, feed_url: form.feed_url || null, scrape_selector: form.scrape_selector || null, user_agent: form.user_agent || null }, () => setForm({ name: '', url: '', feed_url: '', scrape_selector: '', user_agent: '' })); } },
        h('h2', { className: 'text-lg font-medium' }, 'Add source'), field('name', 'Name', true), field('url', 'Website URL', true), field('feed_url', 'Feed URL (optional)'), field('scrape_selector', 'Scrape selector (optional)'), field('user_agent', 'User-Agent (optional)'),
        h('button', { type: 'submit', disabled: busy, className: 'rounded-md border border-border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50' }, 'Add source')));
    const detail = selected && h('section', { 'aria-label': 'Article details', className: 'rounded-md border border-border p-4 space-y-3' },
      h('h2', { className: 'text-lg font-semibold' }, selected.title),
      h('p', { className: 'text-sm text-muted-foreground' }, `${selected.blog} · ${selected.published || 'Date unknown'}`),
      h('div', { className: 'flex gap-2' }, button(summarizing ? 'Fetching and summarizing…' : 'Summarize', summarize, { disabled: summarizing || !selected.url }),
        selected.url && h('a', { href: selected.url, target: '_blank', rel: 'noopener noreferrer', className: 'rounded-md border border-border px-3 py-2 text-sm' }, 'Open original'), button('Close', () => inspect(null))),
      summaryError && h('p', { role: 'alert', className: 'text-sm' }, summaryError),
      summary && h('div', null, h('p', { className: 'whitespace-pre-wrap text-sm leading-relaxed' }, summary.text), h('p', { className: 'mt-3 text-xs text-muted-foreground' }, `${summary.coverage} · ${summary.provider}/${summary.model} · ${summary.cached ? 'Cached' : 'Generated'} ${new Date(summary.generated_at * 1000).toLocaleString()}`)));
    return h('main', { className: 'mx-auto flex max-w-5xl flex-col gap-5 p-4' }, heading, navigation, detail,
      error && h('p', { role: 'alert', className: 'rounded-md border border-destructive p-3 text-sm text-destructive' }, error),
      notice && h('p', { role: 'status', className: 'text-sm text-muted-foreground' }, notice),
      view === 'sources' ? sourceView : articleView);
  }
  window.__HERMES_PLUGINS__.register('blogwatcher-dashboard', BlogwatcherPage);
})();
