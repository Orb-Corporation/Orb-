'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const tools = require('../language-tools');

test('module completion after use', () => {
    const items = tools.completions('use ma', 6);
    assert.deepEqual(items.map(x => x.label), ['math']);
});

test('member completion is scoped to the imported module', () => {
    const items = tools.completions('fn main() { math.s', 19);
    assert.deepEqual(items.map(x => x.label), ['sin', 'sqrt']);
});

test('local declarations and built-ins are suggested', () => {
    const source = 'fn calculate(value: i64) -> i64 { total := value; return total; }\nfn main() { pri';
    const labels = tools.completions(source, source.length).map(x => x.label);
    assert.ok(labels.includes('calculate'));
    assert.ok(labels.includes('value'));
    assert.ok(labels.includes('total'));
    assert.ok(labels.includes('println'));
    assert.ok(labels.includes('print'));
});

test('hover returns standard-library and local function information', () => {
    const moduleText = 'fn main() { math.sqrt(9.0); }';
    assert.match(tools.hover(moduleText, moduleText.indexOf('sqrt') + 4, 'sqrt'), /math\.sqrt/);
    assert.match(tools.hover('fn greet(name: str) -> str { return name; }', 9, 'greet'), /fn greet\(name: str\) -> str/);
    assert.match(tools.hover('fn main() { println("hi"); }', 20, 'println'), /standard output/i);
});

test('use completion context is detected at the cursor', () => {
    assert.deepEqual(tools.contextAt('use json', 8), { mode: 'module', prefix: 'json' });
});
