import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSelectedFormattingRemovalPlan } from '../../app/static/js/modules/mode-manager/services/remove-formatting-service.js';

test('selected removal consumes an exact Add Style scope', () => {
    assert.deepEqual(
        buildSelectedFormattingRemovalPlan({
            contentText: 'this {{word}} is red',
            tagBarText: 'foo {{@red}} bar',
            selectionStart: 7,
            selectionEnd: 11,
        }),
        {
            contentText: 'this word is red',
            tagBarText: 'foo bar',
            selectionStart: 5,
            selectionEnd: 9,
            removals: [
                { start: 5, end: 7 },
                { start: 11, end: 13 },
            ],
            insertions: [],
        },
    );
});

test('selected removal splits a scoped style around a partial selection', () => {
    const plan = buildSelectedFormattingRemovalPlan({
        contentText: '{scarlet}',
        tagBarText: '{@red}',
        selectionStart: 3,
        selectionEnd: 6,
    });

    assert.equal(plan.contentText, '{sc}arl{et}');
    assert.equal(plan.tagBarText, '{@red}');
    assert.equal(plan.selectionStart, 4);
    assert.equal(plan.selectionEnd, 7);
});

test('selected removal closes a scoped style before a selected suffix', () => {
    const plan = buildSelectedFormattingRemovalPlan({
        contentText: 'foo {{bar baz}}',
        tagBarText: '{{@red}}',
        selectionStart: 10,
        selectionEnd: 13,
    });

    assert.equal(plan.contentText, 'foo {{bar }}baz');
    assert.equal(plan.tagBarText, '{{@red}}');
    assert.equal(plan.selectionStart, 12);
    assert.equal(plan.selectionEnd, 15);
});

test('selected removal converts a global style into a scope around unselected text', () => {
    const plan = buildSelectedFormattingRemovalPlan({
        contentText: 'red plain',
        tagBarText: '@red foo',
        selectionStart: 4,
        selectionEnd: 9,
    });

    assert.equal(plan.contentText, '{red }plain');
    assert.equal(plan.tagBarText, 'foo {@red}');
    assert.equal(plan.selectionStart, 6);
    assert.equal(plan.selectionEnd, 11);
});

test('selected removal preserves delimiters owned by a surviving ordinary tag', () => {
    const plan = buildSelectedFormattingRemovalPlan({
        contentText: '{red}',
        tagBarText: '{@red project}',
        selectionStart: 1,
        selectionEnd: 4,
    });

    assert.equal(plan.contentText, '{red}');
    assert.equal(plan.tagBarText, '{project}');
    assert.equal(plan.selectionStart, 1);
    assert.equal(plan.selectionEnd, 4);
});

test('selected removal preserves delimiters owned by a separate ordinary wrapper token', () => {
    const plan = buildSelectedFormattingRemovalPlan({
        contentText: '{{red}}',
        tagBarText: '{{@red}} {{project}}',
        selectionStart: 2,
        selectionEnd: 5,
    });

    assert.equal(plan.contentText, '{{red}}');
    assert.equal(plan.tagBarText, '{{project}}');
});

test('selected removal moves a mixed scope style onto the unselected remainder', () => {
    const plan = buildSelectedFormattingRemovalPlan({
        contentText: '{red blue}',
        tagBarText: '{@red project}',
        selectionStart: 5,
        selectionEnd: 9,
    });

    assert.equal(plan.contentText, '{[red ]blue}');
    assert.equal(plan.tagBarText, '{project} [@red]');
});
