import assert from 'node:assert/strict';
import test from 'node:test';

import { isValidTagToken } from '../../app/static/js/modules/tag-token.js';


test('isValidTagToken reserves exact uppercase OR only', () => {
    assert.equal(isValidTagToken('OR'), false);
    assert.equal(isValidTagToken('or'), true);
    assert.equal(isValidTagToken('Or'), true);
});
