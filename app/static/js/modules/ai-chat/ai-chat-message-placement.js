/**
 * Place rendered chat messages and the active operation card in conversation order.
 *
 * The operation card (for example a complete-scope summary's progress stack) belongs
 * to the assistant turn it is producing, so it sits immediately before that
 * assistant message: earlier conversation and the current request stay above it,
 * and the streamed answer grows below it.
 *
 * @param {object} options
 * @param {Element} options.container Messages container holding no message elements;
 *     an active operation panel must already be inside it and stays in place.
 * @param {Array<{messageId: string, element: Element|null}>} options.renderedMessages
 *     Every message in order; `element` is null when the message renders nothing yet.
 * @param {Element|null} options.operationPanel
 * @param {string} options.operationAnchorMessageId Empty exactly when there is no panel.
 */
export function placeChatMessageElements({
    container,
    renderedMessages,
    operationPanel,
    operationAnchorMessageId,
}) {
    if (container === null || typeof container !== 'object') {
        throw new TypeError('Chat message placement requires a container');
    }
    if (!Array.isArray(renderedMessages)) {
        throw new TypeError('Chat message placement requires rendered messages');
    }
    if (typeof operationAnchorMessageId !== 'string') {
        throw new TypeError('Chat operation anchor message ID must be a string');
    }
    if (operationPanel === null && operationAnchorMessageId !== '') {
        throw new Error('Chat operation anchor was set without an operation panel');
    }
    if (operationPanel !== null && operationAnchorMessageId === '') {
        throw new Error('Chat operation panel requires an anchor message ID');
    }
    if (operationPanel !== null && operationPanel.parentElement !== container) {
        throw new Error('Chat operation panel must already be inside the messages container');
    }
    // The panel never moves: moving it would interrupt clicks on its controls while
    // progress events re-render the conversation many times per second.
    let hasPlacedPanel = false;
    for (const { messageId, element } of renderedMessages) {
        if (typeof messageId !== 'string' || messageId === '') {
            throw new TypeError('Rendered chat messages require IDs');
        }
        if (operationPanel !== null && messageId === operationAnchorMessageId) {
            if (hasPlacedPanel) {
                throw new Error(`Chat operation anchor ${messageId} appears more than once`);
            }
            hasPlacedPanel = true;
        }
        if (element === null) continue;
        if (operationPanel !== null && !hasPlacedPanel) {
            container.insertBefore(element, operationPanel);
        } else {
            container.append(element);
        }
    }
    if (operationPanel !== null && !hasPlacedPanel) {
        throw new Error(
            `Chat operation anchor ${operationAnchorMessageId} is not among rendered messages`,
        );
    }
}
