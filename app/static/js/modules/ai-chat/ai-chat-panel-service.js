const AI_STREAM_EVENT_TYPES = new Set([
    'thinking_delta',
    'content_delta',
    'done',
    'error',
]);
const AI_CHAT_MINIMUM_WIDTH = 280;
const AI_CHAT_MINIMUM_NOTES_WIDTH = 480;


export function calculateAiChatMaximumWidth(viewportWidth) {
    if (!Number.isFinite(viewportWidth) || viewportWidth <= 0) {
        throw new Error('calculateAiChatMaximumWidth requires positive viewportWidth');
    }
    return Math.max(
        AI_CHAT_MINIMUM_WIDTH,
        Math.floor(viewportWidth - AI_CHAT_MINIMUM_NOTES_WIDTH),
    );
}


export function calculateAiChatPanelWidth({ pointerClientX, viewportWidth }) {
    if (!Number.isFinite(pointerClientX)) {
        throw new Error('calculateAiChatPanelWidth requires finite pointerClientX');
    }
    if (!Number.isFinite(viewportWidth) || viewportWidth <= 0) {
        throw new Error('calculateAiChatPanelWidth requires positive viewportWidth');
    }
    const maximumWidth = calculateAiChatMaximumWidth(viewportWidth);
    const requestedWidth = Math.round(viewportWidth - pointerClientX);
    return Math.max(AI_CHAT_MINIMUM_WIDTH, Math.min(maximumWidth, requestedWidth));
}


function validateAiStreamEvent(event) {
    if (!event || typeof event !== 'object' || Array.isArray(event)) {
        throw new Error('AI stream event must be an object');
    }
    if (typeof event.type !== 'string' || !AI_STREAM_EVENT_TYPES.has(event.type)) {
        throw new Error(`Unknown AI stream event type: ${event.type}`);
    }
    if (
        (event.type === 'thinking_delta' || event.type === 'content_delta')
        && (typeof event.text !== 'string' || event.text.length === 0)
    ) {
        throw new Error(`${event.type} requires non-empty text`);
    }
    if (event.type === 'error' && (typeof event.message !== 'string' || event.message.length === 0)) {
        throw new Error('AI error event requires message');
    }
    return event;
}


export function parseAiChatNdjsonBuffer(buffer) {
    if (typeof buffer !== 'string') {
        throw new Error('parseAiChatNdjsonBuffer requires string buffer');
    }
    const lines = buffer.split('\n');
    const remainder = lines.pop();
    if (typeof remainder !== 'string') {
        throw new Error('AI NDJSON parser remainder missing');
    }
    const events = [];
    for (const line of lines) {
        if (line === '') {
            continue;
        }
        events.push(validateAiStreamEvent(JSON.parse(line)));
    }
    return { events, remainder };
}
