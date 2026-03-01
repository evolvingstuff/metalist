import assert from 'node:assert/strict';
import test from 'node:test';

import { buildCommandPaletteEndpoints } from '../../app/static/js/modules/command-palette/endpoint-registry.js';

function noop() {}

test('buildCommandPaletteEndpoints includes utility action endpoints', () => {
    const endpoints = buildCommandPaletteEndpoints({
        preferencesStore: {
            getRaw: () => null,
        },
        actions: {
            applyPreference: noop,
            openPasswordManager: noop,
            openOntologyEditor: noop,
            createBackup: noop,
            openBackupRestore: noop,
            logout: noop,
            openRandomPasswordGenerator: noop,
            collapseAll: noop,
            expandAll: noop,
            resetViewFilters: noop,
            resetAllPreferences: noop,
            runMcpClient: noop,
            openKeyboardShortcutsHelp: noop,
        },
    });

    const endpointIds = new Set(endpoints.map((endpoint) => endpoint.id));
    assert.equal(endpointIds.has('action.create_backup'), true);
    assert.equal(endpointIds.has('form.restore_backup'), true);
    assert.equal(endpointIds.has('action.logout'), true);
    assert.equal(endpointIds.has('form.random_password_generator'), true);
    assert.equal(endpointIds.has('action.open_keyboard_shortcuts_help'), true);
    assert.equal(endpointIds.has('action.run_mcp_client'), true);
});
