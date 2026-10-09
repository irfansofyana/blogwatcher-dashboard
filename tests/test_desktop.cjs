const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function text(n) {
  if (Array.isArray(n)) return n.map(text).join(' ');
  if (n == null || n === false) return '';
  return typeof n === 'object' ? text(n.props?.children) : String(n);
}

test('desktop plugin contributes a Blogwatcher page', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../desktop/plugin.js'), 'utf8');
  const ctx = vm.createContext({ URLSearchParams, console });
  const module = new vm.SourceTextModule(source, { context: ctx });
  const h = (type, props, ...children) => ({ type, props: { ...props, children: children.length === 1 ? children[0] : children } });
  await module.link(name => {
    if (name === 'react') return new vm.SyntheticModule(['createElement', 'useState', 'useEffect'], function () {
      this.setExport('createElement', h);
      this.setExport('useState', value => [value, () => {}]);
      this.setExport('useEffect', () => {});
    }, { context: ctx });
    if (name === '@hermes/plugin-sdk') return new vm.SyntheticModule(['host', 'ROUTES_AREA', 'SIDEBAR_NAV_AREA'], function () {
      this.setExport('host', { navigate: () => {}, composer: {}, state: {} });
      this.setExport('ROUTES_AREA', 'routes');
      this.setExport('SIDEBAR_NAV_AREA', 'sidebarNav');
    }, { context: ctx });
    throw new Error('Unsupported import: ' + name);
  });
  await module.evaluate();
  const contributions = [];
  module.namespace.default.register({ register: value => contributions.push(value), rest: async () => ({ items: [] }) });
  const page = contributions.find(x => x.area === 'routes');
  assert.ok(page);
  assert.equal(page.data.path, '/blogwatcher');
  assert.ok(contributions.some(x => x.area === 'sidebarNav'));
  const element = page.render();
  assert.match(text(element.type(element.props)), /Unread/);
  assert.match(text(element.type(element.props)), /Sources/);
});
