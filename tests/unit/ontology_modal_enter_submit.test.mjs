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


function buildEnterEvent() {
    return {
        key: 'Enter',
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

    const event = buildEnterEvent();
    modal._handleDialogKeydown(event);

    assert.equal(submitCallCount, 1);
    assert.equal(applySuggestionCallCount, 0);
    assert.equal(event.preventDefaultCallCount, 1);
    assert.equal(event.stopPropagationCallCount, 1);
    assert.equal(event.stopImmediatePropagationCallCount, 1);
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
