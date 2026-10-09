const test = require('node:test');
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
      hooks: { useState: value => [value, () => {}], useEffect: () => {} },
      components: { Button: 'button', Card: 'card', Input: 'input' },
      fetchJSON: async () => ({ items: [] }),
    },
    __HERMES_PLUGINS__: { register: (id, view) => registered[id] = view },
  }};
  const source = fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8');
  vm.runInNewContext(source, context);
  assert.equal(typeof registered['blogwatcher-dashboard'], 'function');
  const text = flatten(registered['blogwatcher-dashboard']());
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
      hooks: { useState: value => { const n = index++; return [n === 0 ? 'sources' : value, next => setters.push([n, next])]; }, useEffect: () => {} },
      components: {}, fetchJSON: async () => { throw new Error('offline'); },
    }, __HERMES_PLUGINS__: { register: (id, view) => registered[id] = view },
  }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../dashboard/dist/index.js'), 'utf8'), context);
  const tree = registered['blogwatcher-dashboard']();
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
