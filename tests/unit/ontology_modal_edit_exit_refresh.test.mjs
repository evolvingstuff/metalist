import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const CONTEXT_MENU_EVENTS_URL = new URL(
    '../../app/static/js/modules/mode-manager/events/context-menu-events.js',
    import.meta.url,
);
const COMMAND_PALETTE_CONTROLLER_URL = new URL(
    '../../app/static/js/modules/command-palette/command-palette-controller.js',
    import.meta.url,
);


function extractMethod(source, startMarker, endMarker) {
    const start = source.indexOf(startMarker);
    assert.notEqual(start, -1, `${startMarker} must exist`);
    const end = source.indexOf(endMarker, start + startMarker.length);
    assert.notEqual(end, -1, `${endMarker} must follow ${startMarker}`);
    return source.slice(start, end);
}


test('tag context menu fully refreshes an edited note before opening ontology', () => {
    const source = readFileSync(CONTEXT_MENU_EVENTS_URL, 'utf8');
    const method = extractMethod(
        source,
        'async function openOntologyModalWithFocus(tag) {',
        '\nfunction showTagContextMenu(',
    );

    const deselectIndex = method.indexOf('await actionDeselectNote();');
    const openIndex = method.indexOf('ontologyModal.open();');
    assert.notEqual(deselectIndex, -1, 'edited note must use the refreshing deselect action');
    assert.notEqual(openIndex, -1, 'ontology modal must open');
    assert.ok(deselectIndex < openIndex, 'note refresh must finish before ontology opens');
    assert.doesNotMatch(method, /actionSaveAndExitEditingWithoutRefreshing/);
});


test('command palette modal preparation fully refreshes an edited note', () => {
    const source = readFileSync(COMMAND_PALETTE_CONTROLLER_URL, 'utf8');
    const method = extractMethod(
        source,
        '    async _prepareForModalOpen(commandName) {',
        '\n    async _handleOpenRemindersRequest(',
    );

    assert.match(method, /await actionDeselectNote\(\);/);
    assert.doesNotMatch(method, /actionSaveAndExitEditingWithoutRefreshing/);
});
