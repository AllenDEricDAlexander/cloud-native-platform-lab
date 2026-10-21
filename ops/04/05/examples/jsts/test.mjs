import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculate} from './dist/calculate.js';
test('kernel handles positive, negative and zero', () => {
    assert.equal(calculate(7), 49);
    assert.equal(calculate(-7), 49);
    assert.equal(calculate(0), 0);
    assert.throws(() => calculate(Infinity));
});
