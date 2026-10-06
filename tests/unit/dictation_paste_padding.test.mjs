import assert from 'node:assert/strict';
import test from 'node:test';

import { padForInsertion } from '../../app/static/js/modules/mode-manager/services/dictation-paste-padding.js';

test('pasted tags never run into the tags around them', () => {
    assert.equal(padForInsertion('neural-network', 'python', ''), ' neural-network');
    assert.equal(padForInsertion('neural-network', '', 'python'), 'neural-network ');
    assert.equal(padForInsertion('neural-network', 'a', 'b'), ' neural-network ');
    assert.equal(padForInsertion('neural-network', 'python ', ' GPT'), 'neural-network');
    assert.equal(padForInsertion('neural-network', '', ''), 'neural-network');
});

test('a paste that cleans up to nothing inserts nothing', () => {
    assert.equal(padForInsertion('', 'python', 'GPT'), '');
});
