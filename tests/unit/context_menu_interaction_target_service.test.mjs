import assert from 'node:assert/strict';
import test from 'node:test';

import { isContextMenuInteractionTarget } from '../../app/static/js/modules/context-menu/context-menu-target-service.js';

test('isContextMenuInteractionTarget recognizes both the root menu and its flyout', () => {
    const rootMenuItem = {
        closest: (selector) => selector === '.context-menu' ? { id: 'context-menu' } : null,
    };
    const flyoutMenuItem = {
        closest: (selector) => selector === '.context-menu' ? { id: 'context-submenu' } : null,
    };

    assert.equal(isContextMenuInteractionTarget(rootMenuItem), true);
    assert.equal(isContextMenuInteractionTarget(flyoutMenuItem), true);
});

test('isContextMenuInteractionTarget rejects clicks outside every context menu', () => {
    const noteContent = {
        closest: () => null,
    };

    assert.equal(isContextMenuInteractionTarget(noteContent), false);
});
