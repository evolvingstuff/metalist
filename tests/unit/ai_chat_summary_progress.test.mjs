import assert from 'node:assert/strict';
import test from 'node:test';

import { placeChatMessageElements } from '../../app/static/js/modules/ai-chat/ai-chat-message-placement.js';
import { renderSummaryBatchPreview } from '../../app/static/js/modules/ai-chat/summary-batch-preview.js';


class FakeDocument {
    createElement(tagName) {
        return new FakeElement(tagName, this);
    }
}


class FakeElement {
    constructor(tagName, ownerDocument) {
        this.tagName = tagName.toUpperCase();
        this.ownerDocument = ownerDocument;
        this.children = [];
        this.parentElement = null;
        this.dataset = {};
        this.className = '';
        this.hidden = false;
        this._textContent = '';
    }

    get textContent() {
        return this._textContent + this.children.map((child) => child.textContent).join('');
    }

    set textContent(value) {
        for (const child of this.children) child.parentElement = null;
        this.children = [];
        this._textContent = String(value);
    }

    _detach(node) {
        if (node.parentElement === null) return;
        const siblings = node.parentElement.children;
        siblings.splice(siblings.indexOf(node), 1);
        node.parentElement = null;
    }

    append(...nodes) {
        for (const node of nodes) {
            this._detach(node);
            node.parentElement = this;
            this.children.push(node);
        }
    }

    insertBefore(node, reference) {
        if (reference === null) {
            this.append(node);
            return node;
        }
        const index = this.children.indexOf(reference);
        if (index === -1) throw new Error('Reference node is not a child');
        this._detach(node);
        node.parentElement = this;
        this.children.splice(this.children.indexOf(reference), 0, node);
        return node;
    }

    replaceChildren(...nodes) {
        for (const child of this.children) child.parentElement = null;
        this.children = [];
        this._textContent = '';
        this.append(...nodes);
    }

    remove() {
        this._detach(this);
    }
}


function element(documentRef, label) {
    const node = documentRef.createElement('article');
    node.dataset.label = label;
    return node;
}


function labels(container) {
    return container.children.map((child) => child.dataset.label);
}


function summaryStack() {
    const documentRef = new FakeDocument();
    const stack = documentRef.createElement('div');
    stack.hidden = true;
    return stack;
}


function cardSummary(stack) {
    return stack.children.map((card) => ({
        batch: card.dataset.summaryBatch,
        status: card.dataset.summaryStatus,
        text: card.textContent,
    }));
}


test('operation panel sits between the current user request and the streaming answer', () => {
    const documentRef = new FakeDocument();
    const container = documentRef.createElement('div');
    const panel = element(documentRef, 'panel');
    // The controller appends a new panel after the rendered conversation.
    container.append(element(documentRef, 'stale'), panel);
    container.children[0].remove();

    const renderedMessages = [
        { messageId: 'old-user', element: element(documentRef, 'old-user') },
        { messageId: 'old-assistant', element: element(documentRef, 'old-assistant') },
        { messageId: 'current-user', element: element(documentRef, 'current-user') },
        { messageId: 'current-assistant', element: element(documentRef, 'current-assistant') },
    ];
    placeChatMessageElements({
        container,
        renderedMessages,
        operationPanel: panel,
        operationAnchorMessageId: 'current-assistant',
    });

    assert.deepEqual(labels(container), [
        'old-user', 'old-assistant', 'current-user', 'panel', 'current-assistant',
    ]);
});


test('operation panel keeps its anchor slot before the answer starts rendering', () => {
    const documentRef = new FakeDocument();
    const container = documentRef.createElement('div');
    const panel = element(documentRef, 'panel');
    container.append(panel);

    placeChatMessageElements({
        container,
        renderedMessages: [
            { messageId: 'current-user', element: element(documentRef, 'current-user') },
            { messageId: 'current-assistant', element: null },
        ],
        operationPanel: panel,
        operationAnchorMessageId: 'current-assistant',
    });
    assert.deepEqual(labels(container), ['current-user', 'panel']);

    // A later render with streamed content keeps the answer below the panel.
    for (const child of [...container.children]) if (child !== panel) child.remove();
    placeChatMessageElements({
        container,
        renderedMessages: [
            { messageId: 'current-user', element: element(documentRef, 'current-user') },
            { messageId: 'current-assistant', element: element(documentRef, 'answer-growing') },
        ],
        operationPanel: panel,
        operationAnchorMessageId: 'current-assistant',
    });
    assert.deepEqual(labels(container), ['current-user', 'panel', 'answer-growing']);
});


test('re-rendering never moves the operation panel so its buttons stay clickable', () => {
    const documentRef = new FakeDocument();
    const container = documentRef.createElement('div');
    const panel = element(documentRef, 'panel');
    container.append(panel);
    let panelMoves = 0;
    const originalAppend = container.append.bind(container);
    const originalInsertBefore = container.insertBefore.bind(container);
    container.append = (...nodes) => {
        if (nodes.includes(panel)) panelMoves += 1;
        originalAppend(...nodes);
    };
    container.insertBefore = (node, reference) => {
        if (node === panel) panelMoves += 1;
        return originalInsertBefore(node, reference);
    };

    for (let render = 0; render < 3; render += 1) {
        for (const child of [...container.children]) if (child !== panel) child.remove();
        placeChatMessageElements({
            container,
            renderedMessages: [
                { messageId: 'user', element: element(documentRef, 'user') },
                { messageId: 'answer', element: element(documentRef, 'answer') },
            ],
            operationPanel: panel,
            operationAnchorMessageId: 'answer',
        });
    }

    assert.equal(panelMoves, 0);
    assert.deepEqual(labels(container), ['user', 'panel', 'answer']);
});


test('message placement without an operation panel preserves conversation order', () => {
    const documentRef = new FakeDocument();
    const container = documentRef.createElement('div');
    placeChatMessageElements({
        container,
        renderedMessages: [
            { messageId: 'a', element: element(documentRef, 'a') },
            { messageId: 'b', element: null },
            { messageId: 'c', element: element(documentRef, 'c') },
        ],
        operationPanel: null,
        operationAnchorMessageId: '',
    });
    assert.deepEqual(labels(container), ['a', 'c']);
});


test('message placement fails loudly when the operation anchor is missing', () => {
    const documentRef = new FakeDocument();
    const container = documentRef.createElement('div');
    const panel = element(documentRef, 'panel');
    assert.throws(() => placeChatMessageElements({
        container,
        renderedMessages: [{ messageId: 'a', element: element(documentRef, 'a') }],
        operationPanel: panel,
        operationAnchorMessageId: 'a',
    }), /already be inside/);
    container.append(panel);
    assert.throws(() => placeChatMessageElements({
        container,
        renderedMessages: [{ messageId: 'a', element: element(documentRef, 'a') }],
        operationPanel: panel,
        operationAnchorMessageId: 'missing',
    }), /anchor/);
    assert.throws(() => placeChatMessageElements({
        container,
        renderedMessages: [],
        operationPanel: panel,
        operationAnchorMessageId: '',
    }), /anchor/);
    assert.throws(() => placeChatMessageElements({
        container,
        renderedMessages: [],
        operationPanel: null,
        operationAnchorMessageId: 'a',
    }), /anchor/);
});


function preview(batchNumber, batchCount, status, fields) {
    return {
        batch_number: batchNumber,
        batch_count: batchCount,
        status,
        finding_count: fields.findingCount,
        latest_text: fields.latestText,
        output_tokens: fields.outputTokens,
    };
}


const NOTHING_YET = { findingCount: 0, latestText: '', outputTokens: 0 };


function cardPart(card, className) {
    const part = card.children.find((child) => child.className === className);
    if (part === undefined) throw new Error(`Card part ${className} is missing`);
    return part;
}


test('an active batch streams its newest text into one compact card', () => {
    const stack = summaryStack();

    renderSummaryBatchPreview(stack, preview(1, 3, 'writing', NOTHING_YET));
    assert.equal(stack.hidden, false);
    const card = stack.children[0];
    assert.equal(card.dataset.summaryStatus, 'writing');
    assert.equal(cardPart(card, 'summary-batch-heading').textContent, 'Batch 1 of 3');
    assert.equal(cardPart(card, 'summary-batch-ticker').textContent, '');
    assert.doesNotMatch(card.textContent, /Writing summary/);

    renderSummaryBatchPreview(stack, preview(1, 3, 'streaming', {
        findingCount: 1, latestText: 'The notes compare', outputTokens: 42,
    }));
    renderSummaryBatchPreview(stack, preview(1, 3, 'streaming', {
        findingCount: 2, latestText: '<b>Second</b> finding grows', outputTokens: 97,
    }));
    assert.equal(stack.children.length, 1);
    assert.equal(stack.children[0], card);
    assert.equal(card.dataset.summaryStatus, 'streaming');
    assert.equal(cardPart(card, 'summary-batch-meta').textContent, '2 findings · 97 tokens');
    // Only the newest text tail is shown, and it stays inert text.
    assert.equal(cardPart(card, 'summary-batch-ticker').textContent, '<b>Second</b> finding grows');
});


test('a completed batch collapses to a single summary line', () => {
    const stack = summaryStack();
    renderSummaryBatchPreview(stack, preview(2, 4, 'writing', NOTHING_YET));
    renderSummaryBatchPreview(stack, preview(2, 4, 'streaming', {
        findingCount: 3, latestText: 'tail of the third finding', outputTokens: 300,
    }));
    renderSummaryBatchPreview(stack, preview(2, 4, 'complete', {
        findingCount: 3, latestText: 'First finding summary', outputTokens: 300,
    }));

    const card = stack.children[0];
    assert.equal(card.dataset.summaryStatus, 'complete');
    assert.equal(card.className, 'summary-batch-preview is-complete');
    assert.equal(card.children.length, 1);
    assert.equal(card.textContent, '✓ Batch 2 of 4 · 3 findings — First finding summary');

    const emptyStack = summaryStack();
    renderSummaryBatchPreview(emptyStack, preview(1, 1, 'writing', NOTHING_YET));
    renderSummaryBatchPreview(emptyStack, preview(1, 1, 'complete', NOTHING_YET));
    assert.equal(emptyStack.children[0].textContent, '✓ Batch 1 of 1 · no relevant findings');
});


test('batch cards stay in batch order when later batches finish first', () => {
    const stack = summaryStack();
    const show = (batchNumber, status) => renderSummaryBatchPreview(
        stack,
        preview(batchNumber, 5, status, NOTHING_YET),
    );

    show(1, 'writing');
    show(1, 'complete');
    show(3, 'writing');
    show(2, 'writing');
    show(5, 'writing');
    show(4, 'writing');
    show(5, 'streaming');
    show(5, 'complete');
    show(3, 'complete');

    assert.deepEqual(cardSummary(stack).map(({ batch, status }) => [batch, status]), [
        ['1', 'complete'],
        ['2', 'writing'],
        ['3', 'complete'],
        ['4', 'writing'],
        ['5', 'complete'],
    ]);
});


test('impossible batch preview transitions fail loudly', () => {
    const stack = summaryStack();
    const show = (batchNumber, batchCount, status, fields) => renderSummaryBatchPreview(
        stack,
        preview(batchNumber, batchCount, status, fields),
    );

    assert.throws(() => show(1, 2, 'complete', NOTHING_YET), /completed before it started/);
    assert.throws(() => show(1, 2, 'streaming', NOTHING_YET), /streamed before it started/);
    show(1, 2, 'writing', NOTHING_YET);
    assert.throws(() => show(1, 2, 'writing', NOTHING_YET), /started more than once/);
    show(1, 2, 'complete', NOTHING_YET);
    assert.throws(() => show(1, 2, 'complete', NOTHING_YET), /completed more than once/);
    assert.throws(() => show(1, 2, 'streaming', NOTHING_YET), /streamed after it completed/);
    assert.throws(() => show(2, 2, 'queued', NOTHING_YET), /status/);
    assert.throws(() => show(2, 2, 'writing', { ...NOTHING_YET, latestText: 'early' }),
        /nothing streamed/);
    assert.throws(() => show(2, 3, 'writing', NOTHING_YET), /batch count/);
    assert.throws(() => show(3, 2, 'writing', NOTHING_YET), /valid batch numbers/);
    assert.throws(() => show(2, 2, 'streaming', { ...NOTHING_YET, outputTokens: -1 }),
        /non-negative/);
});
