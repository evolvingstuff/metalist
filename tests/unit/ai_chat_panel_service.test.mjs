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
        '{"type":"action_status","action":"search_notes","status":"started","label":"Searching notes"}\n'
        + '{"type":"thinking_delta","text":"hmm","rendered_text":"<p>hmm</p>"}\n'
        + '{"type":"content_delta","text":"Hi","rendered_text":"<p>Hi',
    );

    assert.deepEqual(parsed.events, [
        {
            type: 'action_status',
            action: 'search_notes',
            status: 'started',
            label: 'Searching notes',
        },
        {
            type: 'thinking_delta',
            text: 'hmm',
            rendered_text: '<p>hmm</p>',
        },
    ]);
    assert.equal(
        parsed.remainder,
        '{"type":"content_delta","text":"Hi","rendered_text":"<p>Hi',
    );

    const completed = parseAiChatNdjsonBuffer(
        `${parsed.remainder}</p>"}\n{"type":"done"}\n`,
    );
    assert.deepEqual(completed.events, [
        { type: 'content_delta', text: 'Hi', rendered_text: '<p>Hi</p>' },
        { type: 'done' },
    ]);
    assert.equal(completed.remainder, '');
});


test('NDJSON parser rejects malformed action status events', () => {
    assert.throws(
        () => parseAiChatNdjsonBuffer(
            '{"type":"action_status","action":"search_notes","status":"started"}\n',
        ),
        /action_status requires label/,
    );
    assert.throws(
        () => parseAiChatNdjsonBuffer(
            '{"type":"action_status","action":"search_notes","status":"waiting","label":"Searching notes"}\n',
        ),
        /action_status status is invalid/,
    );
});


test('NDJSON parser fails loudly for unknown event types', () => {
    assert.throws(
        () => parseAiChatNdjsonBuffer('{"type":"mystery"}\n'),
        /Unknown AI stream event type/,
    );
});


test('NDJSON parser requires rendered snapshots for streamed text', () => {
    assert.throws(
        () => parseAiChatNdjsonBuffer('{"type":"thinking_delta","text":"hmm"}\n'),
        /thinking_delta requires rendered_text/,
    );
    assert.throws(
        () => parseAiChatNdjsonBuffer('{"type":"content_delta","text":"hello"}\n'),
        /content_delta requires rendered_text/,
    );
});
