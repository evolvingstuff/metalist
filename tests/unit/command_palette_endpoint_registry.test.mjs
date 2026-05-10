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
            openSessionTimeoutSettings: noop,
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
            exportCurrentViewAsHtml: noop,
            attachFileToCurrentNote: noop,
            trimUnusedFiles: noop,
            openNamespaceSwitcher: noop,
            openDeleteCurrentNamespace: noop,
            prioritizeTagToFront: noop,
            prioritizeTagToBack: noop,
            alphabetizeRootNotesAsc: noop,
            alphabetizeRootNotesDesc: noop,
            getSortMode: () => 'normal',
            setSortMode: noop,
        },
    });

    const endpointIds = new Set(endpoints.map((endpoint) => endpoint.id));
    const attachFileEndpoint = endpoints.find((endpoint) => endpoint.id === 'action.attach_file_to_current_note');
    assert.equal(endpointIds.has('action.create_backup'), true);
    assert.equal(endpointIds.has('form.switch_namespace'), true);
    assert.equal(endpointIds.has('form.delete_current_namespace'), true);
    assert.equal(endpointIds.has('form.restore_backup'), true);
    assert.equal(endpointIds.has('form.session_timeout'), true);
    assert.equal(endpointIds.has('action.logout'), true);
    assert.equal(endpointIds.has('form.random_password_generator'), true);
    assert.equal(endpointIds.has('pref.auto_collapse_long_notes'), false);
    assert.equal(endpointIds.has('action.export_html'), true);
    assert.equal(endpointIds.has('action.attach_file_to_current_note'), true);
    assert.equal(attachFileEndpoint.label, 'Attach file…');
    assert.equal(endpointIds.has('action.trim_unused_files'), true);
    assert.equal(endpointIds.has('action.prioritize_tag_front'), true);
    assert.equal(endpointIds.has('action.prioritize_tag_back'), true);
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'action.prioritize_tag_front').label,
        'Prioritize tag to front (global)…',
    );
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'action.prioritize_tag_back').label,
        'Prioritize tag to back (global)…',
    );
    assert.equal(endpointIds.has('action.open_keyboard_shortcuts_help'), true);
    assert.equal(endpointIds.has('action.run_mcp_client'), true);
    assert.equal(endpointIds.has('view.sort_mode'), true);
});
