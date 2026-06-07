function requireAction(actions, key) {
    if (!actions || typeof actions !== 'object') {
        throw new Error('Endpoint registry requires actions object');
    }
    const fn = actions[key];
    if (typeof fn !== 'function') {
        throw new Error(`Endpoint registry missing action: ${key}`);
    }
    return fn;
}

export function buildCommandPaletteEndpoints(deps) {
    if (!deps || typeof deps !== 'object') {
        throw new Error('buildCommandPaletteEndpoints requires deps object');
    }

    const preferencesStore = deps.preferencesStore;
    if (!preferencesStore || typeof preferencesStore.getRaw !== 'function') {
        throw new Error('buildCommandPaletteEndpoints requires preferencesStore');
    }

    const actions = deps.actions;
    const applyPreference = requireAction(actions, 'applyPreference');
    const openPasswordManager = requireAction(actions, 'openPasswordManager');
    const openSessionTimeoutSettings = requireAction(actions, 'openSessionTimeoutSettings');
    const createBackup = requireAction(actions, 'createBackup');
    const openBackupRestore = requireAction(actions, 'openBackupRestore');
    const logout = requireAction(actions, 'logout');
    const openRandomPasswordGenerator = requireAction(actions, 'openRandomPasswordGenerator');
    const collapseAll = requireAction(actions, 'collapseAll');
    const expandAll = requireAction(actions, 'expandAll');
    const resetViewFilters = requireAction(actions, 'resetViewFilters');
    const resetAllPreferences = requireAction(actions, 'resetAllPreferences');
    const openOntologyEditor = requireAction(actions, 'openOntologyEditor');
    const runMcpClient = requireAction(actions, 'runMcpClient');
    const openKeyboardShortcutsHelp = requireAction(actions, 'openKeyboardShortcutsHelp');
    const attachFileToCurrentNote = requireAction(actions, 'attachFileToCurrentNote');
    const trimUnusedFiles = requireAction(actions, 'trimUnusedFiles');
    const exportCurrentViewAsHtml = requireAction(actions, 'exportCurrentViewAsHtml');
    const openSwitchNamespace = requireAction(actions, 'openSwitchNamespace');
    const openCreateNamespace = requireAction(actions, 'openCreateNamespace');
    const openManageNamespacePorts = requireAction(actions, 'openManageNamespacePorts');
    const openDeleteCurrentNamespace = requireAction(actions, 'openDeleteCurrentNamespace');
    const prioritizeTagToFront = requireAction(actions, 'prioritizeTagToFront');
    const prioritizeTagToBack = requireAction(actions, 'prioritizeTagToBack');
    const alphabetizeRootNotesAsc = requireAction(actions, 'alphabetizeRootNotesAsc');
    const alphabetizeRootNotesDesc = requireAction(actions, 'alphabetizeRootNotesDesc');
    const resetUpdatedAtToCreatedAt = requireAction(actions, 'resetUpdatedAtToCreatedAt');
    const openReminders = requireAction(actions, 'openReminders');
    const getSortMode = requireAction(actions, 'getSortMode');
    const setSortMode = requireAction(actions, 'setSortMode');

    const defaults = {
        showBacklinks: true,
        showNoteTags: false,
        showTabUi: false,
        showRhsPanel: true,
        showPerfOverlay: false,
        theme: 'system',
    };
    const sortModeActionValue = (sortMode) => (getSortMode() === sortMode ? 'Current' : '↵');

    return [
        {
            id: 'pref.show_backlinks',
            kind: 'boolean',
            label: 'Show backlinks',
            persistenceKey: 'pref.show_backlinks',
            defaultValue: defaults.showBacklinks,
            apply: (next) => applyPreference('pref.show_backlinks', next),
        },
        {
            id: 'pref.show_note_tags',
            kind: 'boolean',
            label: 'Show tags in list',
            persistenceKey: 'pref.show_note_tags',
            defaultValue: defaults.showNoteTags,
            apply: (next) => applyPreference('pref.show_note_tags', next),
        },
        {
            id: 'pref.show_tab_ui',
            kind: 'boolean',
            label: 'Toggle tabs',
            persistenceKey: 'pref.show_tab_ui',
            defaultValue: defaults.showTabUi,
            apply: (next) => applyPreference('pref.show_tab_ui', next),
        },
        {
            id: 'pref.show_rhs_panel',
            kind: 'boolean',
            label: 'Toggle calendar view',
            persistenceKey: 'pref.show_rhs_panel',
            defaultValue: defaults.showRhsPanel,
            apply: (next) => applyPreference('pref.show_rhs_panel', next),
        },
        {
            id: 'pref.show_perf_overlay',
            kind: 'boolean',
            label: 'Toggle perf overlay',
            persistenceKey: 'pref.show_perf_overlay',
            defaultValue: defaults.showPerfOverlay,
            apply: (next) => applyPreference('pref.show_perf_overlay', next),
        },
        {
            id: 'view.sort_mode.normal',
            kind: 'action',
            label: 'Sort order: Normal',
            getValue: () => sortModeActionValue('normal'),
            closeOnExecute: true,
            execute: async () => setSortMode('normal'),
        },
        {
            id: 'view.sort_mode.created',
            kind: 'action',
            label: 'Sort order: Datetime created',
            getValue: () => sortModeActionValue('created'),
            closeOnExecute: true,
            execute: async () => setSortMode('created'),
        },
        {
            id: 'view.sort_mode.updated',
            kind: 'action',
            label: 'Sort order: Datetime last updated',
            getValue: () => sortModeActionValue('updated'),
            closeOnExecute: true,
            execute: async () => setSortMode('updated'),
        },
        {
            id: 'view.sort_mode.alphabetical',
            kind: 'action',
            label: 'Sort order: Alphabetical',
            getValue: () => sortModeActionValue('alphabetical'),
            closeOnExecute: true,
            execute: async () => setSortMode('alphabetical'),
        },
        {
            id: 'pref.theme',
            kind: 'select',
            label: 'Theme',
            persistenceKey: 'pref.theme',
            defaultValue: defaults.theme,
            options: [
                { value: 'system', label: 'System' },
                { value: 'light', label: 'Light' },
                { value: 'dark', label: 'Dark' },
            ],
            apply: (next) => applyPreference('pref.theme', next),
        },
        {
            id: 'action.expand_all',
            kind: 'action',
            label: 'Expand all collapsed notes (current view)',
            closeOnExecute: true,
            execute: async () => expandAll(),
        },
        {
            id: 'action.collapse_all',
            kind: 'action',
            label: 'Collapse all notes (current view)',
            closeOnExecute: true,
            execute: async () => collapseAll(),
        },
        {
            id: 'action.reset_view_filters',
            kind: 'action',
            label: 'Reset current view filters',
            closeOnExecute: true,
            execute: async () => resetViewFilters(),
        },
        {
            id: 'action.reset_all_preferences',
            kind: 'action',
            label: 'Reset all preferences',
            execute: async () => resetAllPreferences(),
        },
        {
            id: 'form.change_password',
            kind: 'form',
            label: 'Change password…',
            execute: async () => openPasswordManager(),
        },
        {
            id: 'form.password_protection',
            kind: 'form',
            label: 'Enable/disable password protection…',
            execute: async () => openPasswordManager(),
        },
        {
            id: 'form.session_timeout',
            kind: 'form',
            label: 'Session idle timeout…',
            execute: async () => openSessionTimeoutSettings(),
        },
        {
            id: 'form.reminders',
            kind: 'form',
            label: 'Reminders…',
            execute: async () => openReminders(),
        },
        {
            id: 'form.switch_namespace',
            kind: 'form',
            label: 'Switch namespace…',
            execute: async () => openSwitchNamespace(),
        },
        {
            id: 'form.create_namespace',
            kind: 'form',
            label: 'Create namespace…',
            execute: async () => openCreateNamespace(),
        },
        {
            id: 'form.manage_namespace_ports',
            kind: 'form',
            label: 'Manage namespace ports…',
            execute: async () => openManageNamespacePorts(),
        },
        {
            id: 'form.delete_current_namespace',
            kind: 'form',
            label: 'Delete namespace…',
            execute: async () => openDeleteCurrentNamespace(),
        },
        {
            id: 'action.create_backup',
            kind: 'action',
            label: 'Create backup now',
            execute: async () => createBackup(),
        },
        {
            id: 'form.restore_backup',
            kind: 'form',
            label: 'Restore from backup…',
            execute: async () => openBackupRestore(),
        },
        {
            id: 'action.logout',
            kind: 'action',
            label: 'Logout',
            execute: async () => logout(),
        },
        {
            id: 'form.random_password_generator',
            kind: 'form',
            label: 'Generate random password…',
            execute: async () => openRandomPasswordGenerator(),
        },
        {
            id: 'action.edit_tag_relationships',
            kind: 'action',
            label: 'Edit tag relationships…',
            execute: async () => openOntologyEditor(),
        },
        {
            id: 'action.export_html',
            kind: 'action',
            label: 'Export as HTML',
            execute: async () => exportCurrentViewAsHtml(),
        },
        {
            id: 'action.attach_file_to_current_note',
            kind: 'action',
            label: 'Attach file…',
            closeOnExecute: true,
            execute: async () => attachFileToCurrentNote(),
        },
        {
            id: 'action.trim_unused_files',
            kind: 'action',
            label: 'Trim unused files',
            closeOnExecute: true,
            execute: async () => trimUnusedFiles(),
        },
        {
            id: 'action.prioritize_tag_front',
            kind: 'action',
            label: 'Prioritize tag to front (global)…',
            closeOnExecute: true,
            execute: async () => prioritizeTagToFront(),
        },
        {
            id: 'action.prioritize_tag_back',
            kind: 'action',
            label: 'Prioritize tag to back (global)…',
            closeOnExecute: true,
            execute: async () => prioritizeTagToBack(),
        },
        {
            id: 'action.alphabetize_root_notes_asc',
            kind: 'action',
            label: 'Alphabetize root notes A-Z (current view)…',
            closeOnExecute: true,
            execute: async () => alphabetizeRootNotesAsc(),
        },
        {
            id: 'action.alphabetize_root_notes_desc',
            kind: 'action',
            label: 'Alphabetize root notes Z-A (current view)…',
            closeOnExecute: true,
            execute: async () => alphabetizeRootNotesDesc(),
        },
        {
            id: 'action.reset_updated_at_to_created_at',
            kind: 'action',
            label: 'Repair: reset updated time to created time (current view)…',
            closeOnExecute: true,
            execute: async () => resetUpdatedAtToCreatedAt(),
        },
        {
            id: 'action.open_keyboard_shortcuts_help',
            kind: 'action',
            label: 'Keyboard shortcuts help…',
            execute: async () => openKeyboardShortcutsHelp(),
        },
        {
            id: 'action.run_mcp_client',
            kind: 'action',
            label: 'Run MCP Client v2 (new tab)',
            execute: async () => runMcpClient(),
        },
    ];
}
