import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { reorderTabOrderToHoveredSlot } from '../../app/static/js/modules/mode-manager/services/tab-drag-service.js';

const KEYBOARD_EVENTS_URL = new URL(
    '../../app/static/js/modules/mode-manager/events/keyboard-events.js',
    import.meta.url,
);
const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);

test('dragging A over B moves A into the B slot', () => {
    assert.deepEqual(
        reorderTabOrderToHoveredSlot(['A', 'B', 'C'], 'A', 'B'),
        ['B', 'A', 'C'],
    );
});

test('dragging C over A after the first move moves C into the A slot', () => {
    assert.deepEqual(
        reorderTabOrderToHoveredSlot(['B', 'A', 'C'], 'C', 'A'),
        ['B', 'C', 'A'],
    );
});

test('tab drop ordering rejects unknown and same-tab targets', () => {
    assert.throws(
        () => reorderTabOrderToHoveredSlot(['A', 'B'], 'missing', 'B'),
        /missing draggedTabId/,
    );
    assert.throws(
        () => reorderTabOrderToHoveredSlot(['A', 'B'], 'A', 'missing'),
        /missing hoveredTabId/,
    );
    assert.throws(
        () => reorderTabOrderToHoveredSlot(['A', 'B'], 'A', 'A'),
        /different tabs/,
    );
});

test('tab UI uses native dragging without arrow reorder controls or a hover grab cursor', async () => {
    const [eventsSource, cssSource] = await Promise.all([
        readFile(KEYBOARD_EVENTS_URL, 'utf8'),
        readFile(MAIN_CSS_URL, 'utf8'),
    ]);

    assert.doesNotMatch(eventsSource, /move-up-context|move-down-context/);
    assert.match(eventsSource, /CommandGate\.run\('tab\.drag_reorder'/);
    assert.match(eventsSource, /draggable="true"/);
    assert.doesNotMatch(cssSource, /\.tab-context-item\s*\{[^}]*cursor:\s*grab;/s);
    assert.match(cssSource, /body\.tab-drag-active[\s\S]*cursor:\s*grabbing\s*!important;/);
});
