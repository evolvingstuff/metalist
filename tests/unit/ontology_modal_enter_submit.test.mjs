import assert from 'node:assert/strict';
import test from 'node:test';


const browserSessionValues = new Map();
globalThis.sessionStorage = {
    getItem(key) {
        return browserSessionValues.has(key) ? browserSessionValues.get(key) : null;
    },
    setItem(key, value) {
        browserSessionValues.set(key, String(value));
    },
};

const { OntologyModal } = await import('../../app/static/js/modules/modals/ontology-modal.js');


function buildKeyboardEvent(key) {
    return {
        key,
        preventDefaultCallCount: 0,
        stopPropagationCallCount: 0,
        stopImmediatePropagationCallCount: 0,
        preventDefault() {
            this.preventDefaultCallCount += 1;
        },
        stopPropagation() {
            this.stopPropagationCallCount += 1;
        },
        stopImmediatePropagation() {
            this.stopImmediatePropagationCallCount += 1;
        },
    };
}


test('ontology relationship dialog Enter submits while suggestions are visible', () => {
    const modal = new OntologyModal();
    modal._dialogState = {
        mode: 'single-tag',
        autoSubmitOnSuggestion: false,
    };
    modal._getDialogElements = () => ({
        suggestions: {
            classList: {
                contains: () => false,
            },
            querySelectorAll: () => [{ dataset: { tag: 'highlighted-suggestion' } }],
        },
    });

    let submitCallCount = 0;
    let applySuggestionCallCount = 0;
    modal._submitDialog = () => {
        submitCallCount += 1;
    };
    modal._applyDialogSuggestion = () => {
        applySuggestionCallCount += 1;
    };

    const event = buildKeyboardEvent('Enter');
    modal._handleDialogKeydown(event);

    assert.equal(submitCallCount, 1);
    assert.equal(applySuggestionCallCount, 0);
    assert.equal(event.preventDefaultCallCount, 1);
    assert.equal(event.stopPropagationCallCount, 1);
    assert.equal(event.stopImmediatePropagationCallCount, 1);
});


test('ontology relationship dialog Enter accepts an arrowed suggestion without submitting', () => {
    const modal = new OntologyModal();
    modal._dialogState = {
        mode: 'single-tag',
        autoSubmitOnSuggestion: false,
    };
    const suggestions = [
        { dataset: { tag: 'first-suggestion' } },
        { dataset: { tag: 'second-suggestion' } },
    ];
    modal._getDialogElements = () => ({
        suggestions: {
            classList: {
                contains: () => false,
            },
            querySelectorAll: () => suggestions,
        },
    });
    modal._updateDialogSuggestionSelection = () => {};

    const appliedSuggestions = [];
    let submitCallCount = 0;
    modal._applyDialogSuggestion = (tag) => {
        appliedSuggestions.push(tag);
    };
    modal._submitDialog = () => {
        submitCallCount += 1;
    };

    modal._handleDialogKeydown(buildKeyboardEvent('ArrowDown'));
    modal._handleDialogKeydown(buildKeyboardEvent('Enter'));

    assert.deepEqual(appliedSuggestions, ['first-suggestion']);
    assert.equal(submitCallCount, 0);
});


test('ontology relationship dialog Enter preserves a pointer-chosen suggestion boundary', () => {
    const modal = new OntologyModal();
    modal._dialogState = {
        mode: 'single-tag',
        autoSubmitOnSuggestion: false,
    };
    const suggestionHandlers = {};
    const suggestionButton = {
        dataset: { tag: 'pointer-suggestion' },
        addEventListener(eventName, handler) {
            suggestionHandlers[eventName] = handler;
        },
    };
    const suggestionsContainer = {
        innerHTML: '',
        classList: {
            add() {},
            remove() {},
            contains: () => false,
        },
        querySelectorAll: () => [suggestionButton],
    };
    modal._getDialogElements = () => ({
        suggestions: suggestionsContainer,
    });
    modal._updateDialogSuggestionSelection = () => {};

    const appliedSuggestions = [];
    let submitCallCount = 0;
    modal._applyDialogSuggestion = (tag) => {
        appliedSuggestions.push(tag);
    };
    modal._submitDialog = () => {
        submitCallCount += 1;
    };

    modal._renderDialogSuggestions(['pointer-suggestion']);
    assert.equal(modal._dialogSelectedIndex, -1);
    assert.equal(typeof suggestionHandlers.mousedown, 'function');
    suggestionHandlers.mousedown({
        preventDefault() {},
        stopPropagation() {},
        stopImmediatePropagation() {},
    });
    modal._handleDialogKeydown(buildKeyboardEvent('Enter'));

    assert.deepEqual(appliedSuggestions, ['pointer-suggestion']);
    assert.equal(submitCallCount, 0);
    assert.equal(modal._dialogPointerSelectionPendingEnter, false);
});


test('ontology relationship dialog retains its submit button', async () => {
    const { readFile } = await import('node:fs/promises');
    const source = await readFile(
        new URL('../../app/static/js/modules/modals/ontology-modal.js', import.meta.url),
        'utf8',
    );

    assert.match(
        source,
        /<button class="ontology-dialog-primary" data-action="dialog-submit">Save<\/button>/,
    );
    assert.match(source, /if \(action === 'dialog-submit'\) \{\s*this\._submitDialog\(\);/);
});
