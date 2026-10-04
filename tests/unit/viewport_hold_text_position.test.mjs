import assert from 'node:assert/strict';
import test from 'node:test';
import { findTextPosition } from '../../app/static/js/modules/mode-manager/services/viewport-hold-service.js';

function anchorAt(text, offset) {
    return {
        textOffset: offset,
        textLength: text.length,
        before: text.slice(Math.max(0, offset - 30), offset),
        after: text.slice(offset, offset + 30),
    };
}

const editText = 'Alpha paragraph one. Beta paragraph two. Gamma paragraph three. Delta paragraph four.';

test('an unchanged text maps exactly to the same position', () => {
    const offset = editText.indexOf('Gamma');
    assert.deepEqual(findTextPosition(editText, anchorAt(editText, offset)), { position: offset, exact: true });
});

test('text added or removed before the anchor shifts the position by the surrounding text', () => {
    const offset = editText.indexOf('Gamma');
    const viewText = 'Title. ' + editText.replace('{{x}}', '');
    assert.deepEqual(findTextPosition(viewText, anchorAt(editText, offset)), { position: offset + 7, exact: true });
});

test('a space typed at the caret and dropped by rendering still matches exactly', () => {
    const typed = editText + ' ';
    const anchor = anchorAt(typed, typed.length);
    assert.deepEqual(findTextPosition(editText, anchor), { position: editText.length, exact: true });
});

test('repeated text picks the occurrence nearest the old position', () => {
    const repeated = 'same words here. same words here. same words here.';
    const offset = repeated.lastIndexOf('same');
    assert.equal(findTextPosition(repeated, anchorAt(repeated, offset)).position, offset);
});

test('text that changed shape falls back to the same proportion, marked approximate', () => {
    const offset = Math.floor(editText.length / 2);
    const rendered = 'x'.repeat(editText.length * 2);
    assert.deepEqual(findTextPosition(rendered, anchorAt(editText, offset)), { position: offset * 2, exact: false });
});

test('an empty note maps to its start without looping', () => {
    assert.deepEqual(findTextPosition('', anchorAt('', 0)), { position: 0, exact: false });
});

test('the position cue follows only significant readjustments of edit-exit holds', async () => {
    const { shouldShowPositionCue } = await import('../../app/static/js/modules/mode-manager/services/viewport-hold-service.js');
    assert.equal(shouldShowPositionCue({ eligible: true, approximate: false, movedPx: 0 }), false);
    assert.equal(shouldShowPositionCue({ eligible: true, approximate: false, movedPx: 40 }), false);
    assert.equal(shouldShowPositionCue({ eligible: true, approximate: false, movedPx: -41 }), true);
    assert.equal(shouldShowPositionCue({ eligible: true, approximate: true, movedPx: 0 }), true);
    // Band shifts while scrolling are never cued.
    assert.equal(shouldShowPositionCue({ eligible: false, approximate: true, movedPx: 500 }), false);
    assert.throws(() => shouldShowPositionCue({ eligible: true, approximate: false }));
});
