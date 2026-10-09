const test = require('node:test');
require('./ui_harness.cjs').suite(false);
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function flatten(node) {
  if (node == null || node === false) return '';
  if (Array.isArray(node)) return node.map(flatten).join(' ');
  if (typeof node !== 'object') return String(node);
  return flatten(node.children || node.props?.children);
}

test('web plugin registers a native tab and its initial inbox shell', () => {
  const registered = {};
  const context = { window: {
    __HERMES_PLUGIN_SDK__: {
      React: { createElement: (type, props, ...children) => ({ type, props, children }) },
      hooks: { useState: value => [value, () => {}], useEffect: () => {}, useRef: value => ({ current: value }) },
      components: { Button: 'button', Card: 'card', Input: 'input' },
      fetchJSON: async () => ({ items: [] }),
    },
    __HERMES_PLUGINS__: { register: (id, view) => registered[id] = view },
  }};
  const source = fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8');
  vm.runInNewContext(source, context);
  assert.equal(typeof registered['hermes-blogwatcher'], 'function');
  const text = flatten(registered['hermes-blogwatcher']());
  assert.match(text, /Unread/);
  assert.match(text, /Sources/);
  assert.match(text, /Scan now/);
});

test('source form keeps the draft until add succeeds', () => {
  const registered = {};
  const setters = [];
  let index = 0;
  const context = { window: {
    __HERMES_PLUGIN_SDK__: {
      React: { createElement: (type, props, ...children) => ({ type, props, children }) },
      hooks: { useState: value => { const n = index++; return [n === 0 ? 'sources' : value, next => setters.push([n, next])]; }, useEffect: () => {}, useRef: value => ({ current: value }) },
      components: {}, fetchJSON: async () => { throw new Error('offline'); },
    }, __HERMES_PLUGINS__: { register: (id, view) => registered[id] = view },
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8'), context);
  const tree = registered['hermes-blogwatcher']();
  function find(node, type) {
    if (node == null) return null;
    if (Array.isArray(node)) return node.map(x => find(x, type)).find(Boolean);
    if (typeof node !== 'object') return null;
    return node.type === type ? node : find(node.children, type);
  }
  const form = find(tree, 'form');
  assert.ok(form);
  form.props.onSubmit({ preventDefault() {} });
  assert.equal(setters.filter(([n]) => n === 6).length, 0, 'form must not clear before the API succeeds');
});

test('title opens details without inference or read mutations', () => {
  let view, index = 0;
  const calls = [], changes = [];
  const article = {id: 1, title: 'Article title', blog: 'Source', url: 'https://example.org', status: 'new'};
  const context = { window: {
    __HERMES_PLUGIN_SDK__: {
      React: {createElement: (type, props, ...children) => ({type, props, children})},
      hooks: {useState: value => {const n = index++; return [n === 4 ? {items: [article], total: 1} : value, next => changes.push(next)];}, useEffect: () => {}, useRef: value => ({current: value})},
      fetchJSON: (...args) => {calls.push(args); return Promise.resolve({});},
    }, __HERMES_PLUGINS__: {register: (id, fn) => {view = fn;}},
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8'), context);
  function find(n) {
    if (Array.isArray(n)) return n.map(find).find(Boolean);
    if (!n || typeof n !== 'object') return null;
    return n.type === 'button' && flatten(n) === 'Article title' ? n : find(n.children);
  }
  const title = find(view());
  assert.ok(title, 'article title must open a detail panel');
  title.props.onClick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], '/api/plugins/hermes-blogwatcher/articles/1/summary');
  assert.ok(changes.length > 0);
});

test('superseded loads cannot overwrite current results', async () => {
  let view, effect, index = 0;
  const setters = [], pending = [], generation = { current: 0 };
  const context = { URLSearchParams, window: {
    __HERMES_PLUGIN_SDK__: {
      React: { createElement: (type, props, ...children) => ({ type, props, children }) },
      hooks: {
        useState: value => { const n = index++; return [value, next => setters.push([n, next])]; },
        useEffect: fn => { effect = fn; }, useRef: () => generation,
      },
      fetchJSON: () => new Promise(resolve => pending.push(resolve)),
    }, __HERMES_PLUGINS__: { register: (id, fn) => { view = fn; } },
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8'), context);
  view(); const cleanup = effect(); if (cleanup) cleanup();
  index = 0; view(); effect();
  pending[2]({ items: [] }); pending[3]({ items: ['new'], total: 1 });
  await new Promise(resolve => setImmediate(resolve));
  pending[0]({ items: [] }); pending[1]({ items: ['old'], total: 1 });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(setters.filter(([n]) => n === 4).map(([,value]) => value.items[0]), ['new']);
});
