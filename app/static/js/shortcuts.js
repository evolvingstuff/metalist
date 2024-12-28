import { NoteStateMachine } from './modules/note-state-machine.js';

export const shortcuts = {
    stopEditing: {
        key: 'Escape',
        modifiers: [],
        description: 'Stop editing current note'
    },
    addSibling: {
        key: 'Enter',
        modifiers: ['meta'],  // or ctrl for Windows
        description: 'Add sibling note below current note'
    },
    addChild: {
        key: 'Enter',
        modifiers: ['meta', 'shift'],  // or ctrl for Windows
        description: 'Add child note under current note'
    },
    addTop: {
        key: 'Enter',
        modifiers: [],
        description: 'Add new note at top (when not editing)'
    },
    undo: {
        key: 'z',
        modifiers: ['meta'],  // or ctrl for Windows
        description: 'Undo'
    },
    redo: {
        key: 'y',
        modifiers: ['meta'],  // or ctrl for Windows
        description: 'Redo'
    }
};

export function setupKeyboardShortcuts(handlers) {
    document.addEventListener('keydown', (e) => {
        for (const [name, shortcut] of Object.entries(shortcuts)) {
            if (e.key.toLowerCase() === shortcut.key.toLowerCase()) {
                // Check if modifiers match exactly
                const hasAllModifiers = shortcut.modifiers.every(mod => 
                    mod === 'meta' ? (e.metaKey || e.ctrlKey) : e[`${mod}Key`]
                );
                const hasOnlyRequiredModifiers = !['meta', 'ctrl', 'shift', 'alt'].some(mod =>
                    e[`${mod}Key`] && !shortcut.modifiers.includes(mod === 'ctrl' ? 'meta' : mod)
                );

                if (hasAllModifiers && hasOnlyRequiredModifiers) {
                    // Only handle Enter when not editing
                    if (shortcut.key === 'Enter' && 
                        NoteStateMachine.state === 'editing' && 
                        shortcut.modifiers.length === 0) {
                        return;
                    }
                    e.preventDefault();
                    handlers[name]?.();
                    return;
                }
            }
        }
    });
}
