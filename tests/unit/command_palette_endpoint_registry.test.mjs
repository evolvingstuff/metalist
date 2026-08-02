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
            openReminders: noop,
            openSoundManager: noop,
            openVersionInfo: noop,
            openOntologyEditor: noop,
            createBackup: noop,
            openBackupRestore: noop,
            logout: noop,
            openRandomPasswordGenerator: noop,
            collapseAll: noop,
            expandAll: noop,
            resetViewFilters: noop,
            resetAllPreferences: noop,
            openKeyboardShortcutsHelp: noop,
            exportCurrentViewAsHtml: noop,
            attachFileToCurrentNote: noop,
            trimUnusedFiles: noop,
            openSwitchNamespace: noop,
            openCreateNamespace: noop,
            openManageNamespacePorts: noop,
            openRenameCurrentNamespace: noop,
            openDeleteCurrentNamespace: noop,
            prioritizeTagToFront: noop,
            prioritizeTagToBack: noop,
            alphabetizeRootNotesAsc: noop,
            alphabetizeRootNotesDesc: noop,
            resetUpdatedAtToCreatedAt: noop,
            getSortMode: () => 'normal',
            setSortMode: noop,
        },
    });

    const endpointIds = new Set(endpoints.map((endpoint) => endpoint.id));
    const attachFileEndpoint = endpoints.find((endpoint) => endpoint.id === 'action.attach_file_to_current_note');
    const calendarEndpoint = endpoints.find((endpoint) => endpoint.id === 'pref.show_rhs_panel');
    const animatedTransitionsEndpoint = endpoints.find((endpoint) => endpoint.id === 'pref.animated_transitions');
    assert.equal(endpointIds.has('action.create_backup'), true);
    assert.equal(endpointIds.has('form.switch_namespace'), true);
    assert.equal(endpointIds.has('form.create_namespace'), true);
    assert.equal(endpointIds.has('form.manage_namespace_ports'), true);
    assert.equal(endpointIds.has('form.rename_current_namespace'), true);
    assert.equal(endpointIds.has('form.delete_current_namespace'), true);
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'form.delete_current_namespace').label,
        'Delete namespace…',
    );
    assert.equal(endpointIds.has('form.restore_backup'), true);
    assert.equal(endpointIds.has('form.session_timeout'), true);
    assert.equal(calendarEndpoint.defaultValue, false);
    assert.equal(animatedTransitionsEndpoint.defaultValue, true);
    assert.equal(animatedTransitionsEndpoint.label, 'Animated transitions');
    assert.equal(endpointIds.has('form.reminders'), true);
    assert.equal(endpointIds.has('form.version_info'), true);
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
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'action.open_keyboard_shortcuts_help').label,
        'Keyboard Shortcuts / Cheatsheet…',
    );
    assert.equal(endpointIds.has('action.run_mcp_client'), false);
    assert.equal(endpointIds.has('view.sort_mode'), false);
    assert.equal(endpointIds.has('view.sort_mode.normal'), true);
    assert.equal(endpointIds.has('view.sort_mode.created'), true);
    assert.equal(endpointIds.has('view.sort_mode.updated'), true);
    assert.equal(endpointIds.has('view.sort_mode.alphabetical'), true);
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'view.sort_mode.alphabetical').label,
        'Sort order: Alphabetical',
    );
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'view.sort_mode.normal').getValue(),
        'Current',
    );
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'view.sort_mode.alphabetical').getValue(),
        '↵',
    );
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'view.sort_mode.alphabetical').closeOnExecute,
        true,
    );
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'action.alphabetize_root_notes_asc').closeOnExecute,
        true,
    );
    assert.equal(endpointIds.has('action.reset_updated_at_to_created_at'), true);
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'action.reset_updated_at_to_created_at').closeOnExecute,
        true,
    );
    assert.equal(
        endpoints.find((endpoint) => endpoint.id === 'action.open_keyboard_shortcuts_help').closeOnExecute,
        undefined,
    );
});
