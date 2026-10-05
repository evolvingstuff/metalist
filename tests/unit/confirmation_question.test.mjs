import assert from 'node:assert/strict';
import test from 'node:test';

import {
    CONFIRMATION_QUESTION_KIND,
    describeConfirmationQuestion,
} from '../../app/static/js/modules/ai-chat/confirmation-question.js';

const question = {
    type: 'bulk_question',
    kind: CONFIRMATION_QUESTION_KIND,
    question_id: 'question-1',
    label: 'Open these web addresses?',
    items: ['https://collector.example/?d=project'],
};

test('a confirmation question carries its id and the exact change to confirm', () => {
    assert.deepEqual(describeConfirmationQuestion(question), {
        questionId: 'question-1',
        label: 'Open these web addresses?',
        items: ['https://collector.example/?d=project'],
    });
    assert.deepEqual(describeConfirmationQuestion({ ...question, items: [] }).items, []);
});

test('malformed confirmation questions fail loudly', () => {
    assert.throws(() => describeConfirmationQuestion({ ...question, kind: 'tag_scope_confirmation' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, question_id: '' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, label: '  ' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, type: 'bulk_progress' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, items: undefined }));
    assert.throws(() => describeConfirmationQuestion({ ...question, items: [''] }));
});
