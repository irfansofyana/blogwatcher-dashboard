const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const tick = () => new Promise(resolve => setImmediate(resolve));
function nodes(n) {
  if (Array.isArray(n)) return n.flatMap(nodes);
  if (!n || typeof n !== 'object') return [];
  return [n, ...nodes(n.props.children)];
}
function text(n) {
  if (Array.isArray(n)) return n.map(text).join(' ');
  if (n == null || n === false) return '';
  return typeof n === 'object' ? text(n.props.children) : String(n);
}
async function harness(desktop) {
  const state = [], refs = [], calls = [], confirmations = [];
  let i = 0, r = 0, component, props;
  const article = id => ({ id, title: 'Article ' + id, blog: 'Source', url: 'https://example.org/' + id, status: 'new' });
  state[4] = { items: [article(1), article(2)], total: 2 };
  const hooks = {
    createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
    useState: initial => { const n = i++; if (!(n in state)) state[n] = initial; return [state[n], value => { state[n] = typeof value === 'function' ? value(state[n]) : value; }]; },
    useRef: initial => { const n = r++; return refs[n] ||= { current: initial }; },
    useEffect: () => {},
  };
  const request = (route, opts) => new Promise((resolve, reject) => calls.push({ route, opts, resolve, reject }));
  const window = { confirm: message => { confirmations.push(message); return window.accept; }, accept: true };
  const context = vm.createContext({ window, URLSearchParams, console });
  if (desktop) {
    const module = new vm.SourceTextModule(fs.readFileSync(path.join(__dirname, '../desktop/plugin.js'), 'utf8'), { context });
    await module.link(name => {
      const exports = name === 'react' ? hooks : name === '@hermes/plugin-sdk' ? { host: { navigate() {} }, ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'nav' } : null;
      assert.ok(exports, 'Unsupported import: ' + name);
      return new vm.SyntheticModule(Object.keys(exports), function () { for (const [key, value] of Object.entries(exports)) this.setExport(key, value); }, { context });
    });
    await module.evaluate();
    module.namespace.default.register({ rest: request, os: { openExternal() {} }, register: c => { if (c.area === 'routes') { const el = c.render(); component = el.type; props = el.props; } } });
  } else {
    window.__HERMES_PLUGIN_SDK__ = { React: hooks, hooks, fetchJSON: (url, opts) => request(url.replace('/api/plugins/hermes-blogwatcher', ''), opts) };
    window.__HERMES_PLUGINS__ = { register: (id, fn) => { component = fn; } };
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8'), context);
  }
  const render = () => { i = 0; r = 0; return component(props); };
  const button = label => nodes(render()).find(n => n.type === 'button' && text(n) === label);
  const click = label => { const b = button(label); assert.ok(b, label); b.props.onClick(); };
  const body = c => desktop ? JSON.parse(JSON.stringify(c.opts.body)) : JSON.parse(c.opts.body);
  return { render, button, click, calls, confirmations, window, body };
}
function suite(desktop) {
  test('saved Markdown produces safe semantic element trees', async () => {
    const h = await harness(desktop);
    h.click('Article 1');
    const source = '# Heading\n\nParagraph with **bold** and `code <img onerror=evil>`\ncontinued.\n\n- first\n- second **item**\n\n1. one\n2. two\n\n<script>evil()</script>\n<img src=x onerror=evil()>\n[jump](javascript:evil())';
    h.calls[0].resolve({ summary: { text: source, generated_at: 1, cached: true } }); await tick();
    const tree = h.render(), all = nodes(tree);
    assert.ok(all.some(n => n.type === 'h1' && text(n) === 'Heading'));
    assert.ok(all.some(n => n.type === 'p' && /Paragraph with/.test(text(n))));
    assert.ok(all.some(n => n.type === 'strong' && text(n) === 'bold'));
    assert.ok(all.some(n => n.type === 'code' && text(n) === 'code <img onerror=evil>'));
    assert.ok(all.some(n => n.type === 'ul' && nodes(n).filter(x => x.type === 'li').length === 2));
    assert.ok(all.some(n => n.type === 'ol' && nodes(n).filter(x => x.type === 'li').length === 2));
    assert.ok(all.every(n => !n.props.dangerouslySetInnerHTML && !['script', 'img'].includes(n.type)));
    assert.ok(!all.some(n => n.props.href?.startsWith('javascript:')));
    assert.match(text(tree), /<script>evil\(\)<\/script>/);
    assert.ok(h.button('Regenerate'));
  });
  test('multiple rows keep independent summaries and concurrent regeneration', async () => {
    const h = await harness(desktop);
    const row = id => nodes(h.render()).find(n => n.type === 'li' && n.props.key === id);
    const inRow = (id, label) => nodes(row(id)).find(n => n.type === 'button' && text(n) === label);
    h.click('Article 1'); h.click('Article 2');
    assert.equal(nodes(h.render()).filter(n => n.props['aria-label'] === 'Article details').length, 2);
    h.calls[1].resolve({ summary: { text: 'Saved second', generated_at: 1 } });
    h.calls[0].resolve({ summary: { text: 'Saved first', generated_at: 1, stale: true } }); await tick();
    assert.match(text(row(1)), /Saved first/); assert.match(text(row(2)), /Saved second/);
    const first = inRow(1, 'Regenerate');
    first.props.onClick(); first.props.onClick();
    inRow(2, 'Regenerate').props.onClick();
    assert.equal(h.calls.length, 4, 'one generation per row even before rerender');
    assert.deepEqual(h.body(h.calls[2]), { article_id: 1, consent: true, regenerate: true });
    assert.deepEqual(h.body(h.calls[3]), { article_id: 2, consent: true, regenerate: true });
    assert.match(h.confirmations[0], /retry.*fallback.*cost/);
    assert.match(text(row(1)), /Saved first/); assert.match(text(row(2)), /Saved second/);
    h.calls[2].reject(new Error('Provider busy')); await tick();
    assert.match(text(row(1)), /Saved first/); assert.match(text(row(1)), /Provider busy/);
    inRow(1, 'Close').props.onClick();
    assert.match(text(row(2)), /Saved second/);
    h.calls[3].resolve({ text: 'Fresh second', generated_at: 2 }); await tick();
    assert.match(text(row(2)), /Fresh second/);
    assert.equal(nodes(row(1)).filter(n => n.props['aria-label'] === 'Article details').length, 0);
  });
  test('closed and reopened rows ignore late cache and generation responses', async () => {
    const h = await harness(desktop);
    h.click('Article 1'); h.click('Article 1'); h.click('Article 1');
    h.calls[0].resolve({ summary: { text: 'Late cache', generated_at: 1 } }); await tick();
    assert.doesNotMatch(text(h.render()), /Late cache/);
    assert.ok(h.button('Loading saved summary…'));
    h.calls[1].resolve({ summary: null }); await tick();
    const summarize = h.button('Summarize');
    h.window.accept = false; summarize.props.onClick();
    assert.equal(h.calls.length, 2, 'declining consent must not post');
    h.window.accept = true; summarize.props.onClick(); summarize.props.onClick();
    assert.equal(h.calls.length, 3);
    assert.deepEqual(h.body(h.calls[2]), { article_id: 1, consent: true, regenerate: false });
    h.click('Close'); h.click('Article 1');
    assert.equal(h.calls[3].route, '/articles/1/summary');
    h.calls[3].resolve({ summary: { text: 'Current cache', generated_at: 3 } }); await tick();
    h.calls[2].resolve({ text: 'Old generation', generated_at: 2 }); await tick();
    assert.match(text(h.render()), /Current cache/); assert.doesNotMatch(text(h.render()), /Old generation/);
  });
  test('cache failures do not generate automatically', async () => {
    const h = await harness(desktop);
    h.click('Article 1');
    h.calls[0].reject(new Error('Cache offline')); await tick();
    assert.equal(h.calls.length, 1);
    assert.match(text(h.render()), /Cache offline/);
    assert.ok(h.button('Summarize'));
  });
  test('stale saved summary is identified without automatically regenerating', async () => {
    const h = await harness(desktop);
    h.click('Article 1');
    h.calls[0].resolve({ summary: { text: 'Saved', stale: true, cached: true, generated_at: 1 } }); await tick();
    assert.match(text(h.render()), /Stale/);
    assert.equal(h.calls.length, 1);
  });
  test('opening performs only a saved-summary GET and expands inside its row', async () => {
    const h = await harness(desktop);
    h.click('Article 1');
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].route, '/articles/1/summary');
    assert.ok(!h.calls[0].opts?.method || h.calls[0].opts.method === 'GET');
    const row = nodes(h.render()).find(n => n.type === 'li' && n.props.key === 1);
    assert.ok(nodes(row).some(n => n.props['aria-label'] === 'Article details'));
    assert.equal(h.button('Loading saved summary…').props.disabled, true);
    h.calls[0].resolve({ summary: null }); await tick();
    assert.equal(h.button('Summarize').props.disabled, false);
    h.click('Article 1');
    assert.equal(nodes(h.render()).filter(n => n.props['aria-label'] === 'Article details').length, 0);
    assert.equal(h.calls.length, 1);
  });
}
module.exports = { suite, harness, nodes, text, tick };
