/* Native Hermes Desktop page. The Python plugin owns all CLI operations. */
import { host, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk';
import { createElement as h, useState, useEffect, useRef } from 'react';

// Deliberately small Markdown subset. Raw HTML and links remain text nodes.
function summaryMarkdown(text) {
  function inline(value) {
    return value.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g).map((part, key) =>
      part.startsWith('`') && part.endsWith('`') ? h('code', { key, className: 'rounded border border-(--ui-stroke-secondary) px-1 font-mono text-xs' }, part.slice(1, -1)) :
      part.startsWith('**') && part.endsWith('**') ? h('strong', { key }, inline(part.slice(2, -2))) : part);
  }
  const blocks = [], lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  let index = 0;
  const list = line => /^\s*([-+*]|\d+[.)])\s+(.+)$/.exec(line);
  const heading = line => /^(#{1,6})\s+(.+)$/.exec(line);
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    const title = heading(line), item = list(line), key = index;
    if (title) {
      blocks.push(h('h' + title[1].length, { key, className: 'font-semibold leading-snug' }, inline(title[2])));
      index++;
    } else if (item) {
      const ordered = /^\d/.test(item[1]), items = [];
      while (index < lines.length) {
        const next = list(lines[index]);
        if (!next || /^\d/.test(next[1]) !== ordered) break;
        items.push(h('li', { key: index }, inline(next[2]))); index++;
      }
      blocks.push(h(ordered ? 'ol' : 'ul', { key, start: ordered ? parseInt(item[1], 10) : undefined, className: ordered ? 'list-decimal pl-5 space-y-1' : 'list-disc pl-5 space-y-1' }, items));
    } else {
      const paragraph = [];
      while (index < lines.length && lines[index].trim() && !heading(lines[index]) && !list(lines[index])) paragraph.push(lines[index++]);
      blocks.push(h('p', { key }, inline(paragraph.join('\n'))));
    }
  }
  return h('div', { className: 'space-y-3 text-sm leading-relaxed break-words' }, blocks);
}

function BlogwatcherPage({ ctx }) {
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
  const [details, setDetails] = useState({});
  const rows = useRef({});
  const [loading, setLoading] = useState(true);
  const LIMIT = 50;
  const generation = useRef(0);

  function load() {
    const request = ++generation.current;
    setLoading(true);
    const query = new URLSearchParams({ all_articles: String(mode === 'all'), offset: String(page * LIMIT), limit: String(LIMIT) });
    if (blog) query.set('blog', blog);
    Promise.all([ctx.rest('/blogs'), ctx.rest('/articles?' + query.toString())])
      .then(([s, a]) => { if (request !== generation.current) return; setSources(s.items); setArticles(a); setError(''); })
      .catch(e => { if (request === generation.current) setError(e.message || 'Could not load Blogwatcher'); })
      .finally(() => { if (request === generation.current) setLoading(false); });
  }
  useEffect(() => { load(); return () => { generation.current++; }; }, [mode, blog, page]);
  function action(route, body, onSuccess) {
    setBusy(true); setError(''); setNotice('');
    ctx.rest(route, { method: 'POST', body, timeoutMs: route === '/scan' ? 195000 : route === '/blogs' ? 75000 : 45000 })
      .then(result => { if (onSuccess) onSuccess(); setNotice(result.message || 'Done'); load(); })
      .catch(e => setError(`${e.message || 'Request failed'}. The CLI may still have completed this action; refresh before retrying.`)).finally(() => setBusy(false));
  }
  function confirmAction(message, route, body) {
    // Native confirm is explicit and keeps destructive actions out of a single tap.
    if (window.confirm(message)) action(route, { ...body, confirm: true });
  }
  function updateRow(id, row, changes) {
    // Row identity is its request-generation token; close/reopen invalidates old work.
    if (rows.current[id] !== row) return;
    Object.assign(row, changes);
    setDetails(previous => ({ ...previous, [id]: { ...row } }));
  }
  function inspect(article) {
    const id = article.id;
    if (rows.current[id]) {
      delete rows.current[id];
      setDetails(previous => { const next = { ...previous }; delete next[id]; return next; });
      return;
    }
    const row = { summary: null, error: '', loading: true, inflight: false };
    rows.current[id] = row;
    updateRow(id, row, {});
    ctx.rest('/articles/' + article.id + '/summary')
      .then(result => updateRow(id, row, { summary: result.summary }))
      .catch(e => updateRow(id, row, { error: e.message || 'Could not load saved summary.' }))
      .finally(() => updateRow(id, row, { loading: false }));
  }
  function summarize(article) {
    const row = rows.current[article.id];
    if (!row || row.loading || row.inflight) return;
    if (!window.confirm('Fetch this article and send its text to Hermes? Its configured model provider may retry or use fallback models, which can consume additional tokens and incur additional cost.')) return;
    updateRow(article.id, row, { inflight: true, error: '' });
    ctx.rest('/articles/summary', { method: 'POST', body: { article_id: article.id, consent: true, regenerate: !!row.summary }, timeoutMs: 175000 })
      .then(result => updateRow(article.id, row, { summary: result }))
      .catch(e => updateRow(article.id, row, { error: e.message || 'Summary request failed. Hermes may still be processing or retrying; wait before requesting another summary.' }))
      .finally(() => updateRow(article.id, row, { inflight: false }));
  }
  const button = (label, onClick, extra = {}) => h('button', { type: 'button', onClick, disabled: busy || extra.disabled, className: 'rounded-md border border-(--ui-stroke-secondary) px-3 py-2 text-sm hover:opacity-70 disabled:opacity-50', ...extra }, label);
  const field = (key, label, required = false) => h('label', { key, className: 'flex flex-col gap-1 text-sm' }, label,
    h('input', { className: 'rounded-md border border-(--ui-stroke-secondary) bg-transparent px-3 py-2', value: form[key], required, maxLength: 1000, onChange: e => setForm({ ...form, [key]: e.target.value }) }));
  const sourceOptions = [h('option', { key: 'all', value: '' }, 'All sources'), ...sources.map(s => h('option', { key: s.name, value: s.name }, s.name))];
  const heading = h('header', { className: 'flex flex-wrap items-center justify-between gap-3' },
    h('div', null, h('h1', { className: 'text-2xl font-semibold' }, 'Blogwatcher'), h('p', { className: 'text-sm text-(--ui-text-secondary)' }, 'Your original CLI, inside Hermes.')),
    h('div', { className: 'flex gap-2' }, button('Refresh', load), button('Scan now', () => action('/scan', { blog: blog || null })), button('Chat with Hermes', () => host.navigate('/'))));
  const navigation = h('nav', { className: 'flex gap-2 border-b border-(--ui-stroke-secondary) pb-3' },
    button('Unread', () => { setView('inbox'); setMode('unread'); setPage(0); }),
    button('All articles', () => { setView('inbox'); setMode('all'); setPage(0); }),
    button('Sources', () => setView('sources')));
  const detail = (selected, row) => h('section', { 'aria-label': 'Article details', className: 'w-full rounded-md border border-(--ui-stroke-secondary) p-4 space-y-3' },
    h('h2', { className: 'text-lg font-semibold' }, selected.title),
    h('p', { className: 'text-sm text-(--ui-text-secondary)' }, `${selected.blog} · ${selected.published || 'Date unknown'}`),
    h('div', { className: 'flex gap-2' }, button(row.loading ? 'Loading saved summary…' : row.inflight ? 'Fetching and summarizing…' : row.summary ? 'Regenerate' : 'Summarize', () => summarize(selected), { disabled: row.loading || row.inflight || !selected.url }),
      selected.url && button('Open original', () => ctx.os.openExternal(selected.url)), button('Close', () => inspect(selected))),
    row.error && h('p', { role: 'alert', className: 'text-sm' }, row.error),
    row.summary && h('div', null, summaryMarkdown(row.summary.text), h('p', { className: 'mt-3 text-xs text-(--ui-text-secondary)' }, `${row.summary.coverage} · ${row.summary.provider}/${row.summary.model} · ${row.summary.stale ? 'Stale saved summary · ' : ''}${row.summary.cached ? 'Cached' : 'Generated'} ${new Date(row.summary.generated_at * 1000).toLocaleString()}`)));
  const articleView = h('section', { className: 'space-y-3' },
    h('div', { className: 'flex flex-wrap items-center gap-3' },
      h('select', { 'aria-label': 'Filter by source', className: 'rounded-md border border-(--ui-stroke-secondary) px-3 py-2', value: blog, onChange: e => { setBlog(e.target.value); setPage(0); } }, sourceOptions),
      h('span', { className: 'text-sm text-(--ui-text-secondary)' }, loading ? 'Loading…' : error ? 'Article count unavailable; displayed data may be stale' : `${articles.total} ${mode === 'unread' ? 'unread' : 'articles'}`),
      button('Mark all read', () => confirmAction(`Mark all ${blog ? 'from ' + blog : 'unread articles'} as read?`, '/articles/read-all', { blog: blog || null }), { disabled: mode !== 'unread' || !articles.total })),
    articles.items.length ? h('ul', { className: 'divide-y divide-(--ui-stroke-secondary) rounded-md border border-(--ui-stroke-secondary)' }, articles.items.map(a =>
      h('li', { key: a.id, className: 'flex flex-wrap items-center justify-between gap-3 p-4' },
        h('div', { className: 'min-w-0 flex-1' }, h('button', { type: 'button', onClick: () => inspect(a), 'aria-expanded': !!details[a.id], className: 'text-left font-medium hover:underline' }, a.title),
          h('div', { className: 'mt-1 text-xs text-(--ui-text-secondary)' }, `${a.blog} · ${a.published || 'Date unknown'} · #${a.id}`)),
        button(a.status === 'read' ? 'Mark unread' : 'Mark read', () => action(a.status === 'read' ? '/articles/unread' : '/articles/read', { article_id: a.id })),
        details[a.id] && detail(a, details[a.id])
      ))) : h('p', { className: 'rounded-md border border-(--ui-stroke-secondary) p-6 text-sm text-(--ui-text-secondary)' }, loading ? 'Loading articles…' : error ? 'Articles could not be loaded. Use Refresh to try again.' : 'No articles in this view.'),
    h('div', { className: 'flex items-center gap-2' }, button('Previous', () => setPage(Math.max(0, page - 1)), { disabled: !page }),
      h('span', { className: 'text-sm' }, `Page ${page + 1}`), button('Next', () => setPage(page + 1), { disabled: (page + 1) * LIMIT >= articles.total })));
  const sourceView = h('section', { className: 'grid gap-5 lg:grid-cols-2' },
    h('div', null, h('h2', { className: 'mb-3 text-lg font-medium' }, `Sources (${sources.length})`),
      h('ul', { className: 'divide-y divide-(--ui-stroke-secondary) rounded-md border border-(--ui-stroke-secondary)' }, sources.map(s =>
        h('li', { key: s.name, className: 'flex items-start justify-between gap-3 p-3' },
          h('div', { className: 'min-w-0' }, h('strong', null, s.name), s.url && button(s.url, () => ctx.os.openExternal(s.url)),
            h('p', { className: 'text-xs text-(--ui-text-secondary)' }, `Feed: ${s.feed || 'Auto-discovery'} · Last scan: ${s.last_scanned || 'Never'}`)),
          button('Remove', () => confirmAction(`Remove ${s.name} and ALL its articles? This cannot be undone.`, '/blogs/remove', { name: s.name })))))),
    h('form', { className: 'flex flex-col gap-3 rounded-md border border-(--ui-stroke-secondary) p-4', onSubmit: e => { e.preventDefault(); action('/blogs', { ...form, feed_url: form.feed_url || null, scrape_selector: form.scrape_selector || null, user_agent: form.user_agent || null }, () => setForm({ name: '', url: '', feed_url: '', scrape_selector: '', user_agent: '' })); } },
      h('h2', { className: 'text-lg font-medium' }, 'Add source'), field('name', 'Name', true), field('url', 'Website URL', true), field('feed_url', 'Feed URL (optional)'), field('scrape_selector', 'Scrape selector (optional)'), field('user_agent', 'User-Agent (optional)'),
      h('button', { type: 'submit', disabled: busy, className: 'rounded-md border border-(--ui-stroke-secondary) px-3 py-2 text-sm disabled:opacity-50' }, 'Add source')));
  return h('main', { className: 'flex h-full flex-col gap-5 overflow-auto p-4' }, heading, navigation,
    error && h('p', { role: 'alert', className: 'text-sm text-(--ui-accent)' }, error),
    notice && h('p', { role: 'status', className: 'text-sm text-(--ui-text-secondary)' }, notice),
    view === 'sources' ? sourceView : articleView);
}

export default {
  id: 'blogwatcher-dashboard', name: 'Blogwatcher', defaultEnabled: false,
  register(ctx) {
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/blogwatcher' }, render: () => h(BlogwatcherPage, { ctx }) });
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/blogwatcher', label: 'Blogwatcher', codicon: 'rss' } });
  }
};
