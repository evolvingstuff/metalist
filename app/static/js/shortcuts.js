export const shortcuts = {
    stopEditing: {
        key: 'Escape',
        description: 'Stop editing current note'
    }
    // Ready for more shortcuts like:
    // createNote: { key: 'Ctrl+N', description: 'Create new note' },
    // deleteNote: { key: 'Ctrl+D', description: 'Delete current note' },
    // etc.
};

export function setupKeyboardShortcuts(handlers) {
    document.addEventListener('keydown', (e) => {
        if (e.key === shortcuts.stopEditing.key) {
            handlers.stopEditing();
        }
        // Ready for more shortcut handling
    });
}
