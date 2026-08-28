import assert from 'node:assert/strict';
import test from 'node:test';

import {
    calculateAiChatMaximumWidth,
    calculateAiChatPanelWidth,
    parseAiChatNdjsonBuffer,
} from '../../app/static/js/modules/ai-chat/ai-chat-panel-service.js';


test('chat resizer converts pointer position into clamped right-panel width', () => {
    assert.equal(calculateAiChatPanelWidth({ pointerClientX: 800, viewportWidth: 1200 }), 400);
    assert.equal(calculateAiChatPanelWidth({ pointerClientX: 1100, viewportWidth: 1200 }), 280);
    assert.equal(calculateAiChatPanelWidth({ pointerClientX: 100, viewportWidth: 1200 }), 720);
});


test('chat maximum width preserves the minimum notes area', () => {
    assert.equal(calculateAiChatMaximumWidth(1200), 720);
    assert.equal(calculateAiChatMaximumWidth(2000), 1520);
    assert.equal(calculateAiChatMaximumWidth(760), 280);
});


test('NDJSON parser retains incomplete tail while returning complete stream events', () => {
    const parsed = parseAiChatNdjsonBuffer(
        '{"type":"thinking_delta","text":"hmm"}\n'
        + '{"type":"content_delta","text":"Hi',
    );

    assert.deepEqual(parsed.events, [{ type: 'thinking_delta', text: 'hmm' }]);
    assert.equal(parsed.remainder, '{"type":"content_delta","text":"Hi');

    const completed = parseAiChatNdjsonBuffer(
        `${parsed.remainder}"}\n{"type":"done"}\n`,
    );
    assert.deepEqual(completed.events, [
        { type: 'content_delta', text: 'Hi' },
        { type: 'done' },
    ]);
    assert.equal(completed.remainder, '');
});


test('NDJSON parser fails loudly for unknown event types', () => {
    assert.throws(
        () => parseAiChatNdjsonBuffer('{"type":"mystery"}\n'),
        /Unknown AI stream event type/,
    );
});
