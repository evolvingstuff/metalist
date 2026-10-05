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
    label: 'Accept 3 pending tag proposals across 2 notes in the current view?',
};

test('a confirmation question carries its id and the exact change to confirm', () => {
    assert.deepEqual(describeConfirmationQuestion(question), {
        questionId: 'question-1',
        label: 'Accept 3 pending tag proposals across 2 notes in the current view?',
    });
});

test('malformed confirmation questions fail loudly', () => {
    assert.throws(() => describeConfirmationQuestion({ ...question, kind: 'tag_scope_confirmation' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, question_id: '' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, label: '  ' }));
    assert.throws(() => describeConfirmationQuestion({ ...question, type: 'bulk_progress' }));
});
