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
    const createBackup = requireAction(actions, 'createBackup');
    const openBackupRestore = requireAction(actions, 'openBackupRestore');
    const logout = requireAction(actions, 'logout');
    const openRandomPasswordGenerator = requireAction(actions, 'openRandomPasswordGenerator');
    const collapseAll = requireAction(actions, 'collapseAll');
    const expandAll = requireAction(actions, 'expandAll');
    const resetViewFilters = requireAction(actions, 'resetViewFilters');
    const resetAllPreferences = requireAction(actions, 'resetAllPreferences');
    const openOntologyEditor = requireAction(actions, 'openOntologyEditor');

    const defaults = {
        showBacklinks: false,
        showNoteTags: false,
        showTabUi: false,
        showPerfOverlay: false,
        autoCollapseLongNotes: false,
        sortOrder: 'updated',
        theme: 'system',
    };

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
            label: 'Toggle tab UI',
            persistenceKey: 'pref.show_tab_ui',
            defaultValue: defaults.showTabUi,
            apply: (next) => applyPreference('pref.show_tab_ui', next),
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
            id: 'pref.auto_collapse_long_notes',
            kind: 'boolean',
            label: 'Auto-collapse long notes',
            persistenceKey: 'pref.auto_collapse_long_notes',
            defaultValue: defaults.autoCollapseLongNotes,
            apply: (next) => applyPreference('pref.auto_collapse_long_notes', next),
        },
        {
            id: 'pref.sort_order',
            kind: 'select',
            label: 'Sort order',
            persistenceKey: 'pref.sort_order',
            defaultValue: defaults.sortOrder,
            options: [
                { value: 'newest', label: 'Newest' },
                { value: 'oldest', label: 'Oldest' },
                { value: 'updated', label: 'Updated' },
            ],
            apply: (next) => applyPreference('pref.sort_order', next),
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
            execute: async () => expandAll(),
        },
        {
            id: 'action.collapse_all',
            kind: 'action',
            label: 'Collapse all notes (current view)',
            execute: async () => collapseAll(),
        },
        {
            id: 'action.reset_view_filters',
            kind: 'action',
            label: 'Reset current view filters',
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
    ];
}
