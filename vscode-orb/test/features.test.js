'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('../features');

test('module completion is context-aware', () => {
  const items = E.complete('use math; fn main() { math.sq', 32);
  assert.ok(items.some(x => x.label === 'sqrt'));
  assert.ok(!items.some(x => x.label === 'concat'));
});

test('top-level completion includes keywords, standard modules and declarations', () => {
  const source = 'pub fn calculate(x: i64) -> i64 { return x; }\nfn main() { pri';
  const items = E.complete(source, source.length);
  assert.ok(items.some(x => x.label === 'println'));
  assert.ok(items.some(x => x.label === 'calculate'));
  assert.ok(items.some(x => x.label === 'json' && x.kind === 'module'));
});

test('hover explains built-ins, modules and local function signatures', () => {
  assert.match(E.hover('fn main() { println(1); }', 17), /standard output/);
  assert.match(E.hover('use math; fn main() { math.sqrt(4.0); }', 30), /math\.sqrt/);
  assert.match(E.hover('fn add(a: i64, b: i64) -> i64 { return a+b; }', 5), /fn add\(a: i64, b: i64\) -> i64/);
});

test('signature help tracks the active argument', () => {
  const source = 'fn join(a: str, b: str) -> str { return a; }\nfn main() { join("a", ';
  const info = E.signature(source, source.length);
  assert.deepEqual(info.parameters, ['a: str', 'b: str']);
  assert.equal(info.activeParameter, 1);
});
