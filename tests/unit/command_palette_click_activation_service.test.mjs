import assert from 'node:assert/strict';
import test from 'node:test';

import {
    shouldActivateCommandPaletteRowClick,
} from '../../app/static/js/modules/command-palette/click-activation-service.js';

function selectionWithText(text) {
    return {
        toString() {
            return text;
        },
        anchorNode: { id: 'anchor' },
        focusNode: { id: 'focus' },
    };
}

test('command palette row click activates when no text is selected', () => {
    assert.equal(
        shouldActivateCommandPaletteRowClick({
            row: { contains: () => true },
            selection: selectionWithText(''),
        }),
        true,
    );
});

test('command palette row click is ignored after selecting text', () => {
    assert.equal(
        shouldActivateCommandPaletteRowClick({
            row: { contains: () => true },
            selection: selectionWithText('Prioritize tag'),
        }),
        false,
    );
});

test('command palette row click ignores selections outside the clicked row', () => {
    assert.equal(
        shouldActivateCommandPaletteRowClick({
            row: { contains: () => false },
            selection: selectionWithText('existing note selection'),
        }),
        true,
    );
});

test('command palette row click requires selection to expose toString', () => {
    assert.throws(
        () => shouldActivateCommandPaletteRowClick({
            row: { contains: () => true },
            selection: { toString: 3 },
        }),
        /selection must expose toString/,
    );
});
