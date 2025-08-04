import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote, createChildNote, moveNoteUp, moveNoteDown, actionCopyNote, actionPasteNoteSibling, actionPasteNoteChild } from '../actions/note-actions.js';
import { actionDeselectNote } from '../actions/selection-actions.js';
import { actionUndo, actionRedo } from '../actions/history-actions.js';
import { actionExitSearchMode } from '../actions/search-actions.js';

export function initKeyboardEvents() {
        
    document.addEventListener('keydown', handleKeyDown, { capture: true });
        
    Logger.logInit('Keyboard events handler');
}

function handleKeyDown(event) {
    if (!event) {
        throw new Error('handleKeyDown called without an event object');
    }
        
    if (typeof event.key !== 'string') {
        throw new Error(`Invalid KeyboardEvent: missing or invalid key property: ${event.key}`);
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Keyboard event ignored while system is loading', {
            key: event.key,
            meta: event.metaKey || event.ctrlKey,
            shift: event.shiftKey,
            isLoading: true
        });
        event.preventDefault();
        event.stopPropagation();
        return;
    }

    ModeContext.setKeyPressed(
        event.key,
        event.metaKey || event.ctrlKey,
        event.shiftKey
    );

    Logger.logDebug('Key pressed', {
        key: event.key,
        meta: event.metaKey || event.ctrlKey,
        shift: event.shiftKey
    }, Logger.LogCategory.EVENT);

    if (ModeContext.isEditing) {
                
        const isModifierKey = event.key === 'Control' || event.key === 'Alt' || 
                                                    event.key === 'Shift' || event.key === 'Meta';
        const isNavigationKey = event.key === 'ArrowUp' || event.key === 'ArrowDown' || 
                                                        event.key === 'ArrowLeft' || event.key === 'ArrowRight' ||
                                                        event.key === 'Home' || event.key === 'End' || 
                                                        event.key === 'PageUp' || event.key === 'PageDown';
        const isFunctionKey = event.key.startsWith('F') && event.key.length > 1; 

        if (!isModifierKey && !isNavigationKey && !isFunctionKey && 
                !event.ctrlKey && !event.metaKey && event.key !== 'Escape') {

            Logger.logDebug('Detected content-changing keypress', {
                key: event.key,
                noteId: ModeContext.currentNoteId
            }, Logger.LogCategory.EVENT);

            if (!ModeContext.isDirty) {
                ModeContext.setDirty(true);
                Logger.logDebug('Content marked as dirty due to typing', {
                    key: event.key,
                    noteId: ModeContext.currentNoteId
                }, Logger.LogCategory.STATE);
            }
        }
    }

    switch (event.key) {
        case 'Escape':
            handleEscapeKey();
            break;
        case 'Enter':
            if ((event.metaKey || event.ctrlKey) && event.shiftKey) {
                handleCreateChildNoteShortcut(event);
            } else if (event.metaKey || event.ctrlKey) {
                handleCreateNoteShortcut(event);
            } else {
                handleEnterKey(event);
            }
            break;
        case 'Backspace':
        case 'Delete':
            if (event.metaKey) {
                handleDeleteNoteShortcut(event);
            } else if (event.ctrlKey) {
                handleDeleteNoteShortcut(event);
            }
            break;
        case '/':
            if (event.metaKey || event.ctrlKey) {
                handleSearchShortcut();
            }
            break;
        case 'ArrowUp':
            if (event.metaKey || event.ctrlKey) {
                handleMoveNoteUpShortcut(event);
            }
            break;
        case 'ArrowDown':
            if (event.metaKey || event.ctrlKey) {
                handleMoveNoteDownShortcut(event);
            }
            break;
        case 'v':
            if (event.metaKey || event.ctrlKey) {
                if (event.shiftKey) {
                    handlePasteNoteChildShortcut(event);
                } else {
                    handlePasteNoteSiblingShortcut(event);
                }
            }
            break;
        case 'z':
            if (event.metaKey || event.ctrlKey) {
                if (event.shiftKey) {
                    handleRedoShortcut(event);
                } else {
                    handleUndoShortcut(event);
                }
            }
            break;
        case 'c':
            if (event.metaKey || event.ctrlKey) {
                handleCopyNoteShortcut(event);
            }
            break;
        case 'y':
            if (event.metaKey || event.ctrlKey) {
                handleRedoShortcut(event);
            }
            break;
                
    }
}

function handleEscapeKey() {
    if (ModeContext.isSearching === undefined) {
        throw new Error('ModeContext missing isSearching property in handleEscapeKey');
    }
        
    if (ModeContext.isSearching) {
        ModeContext.setSearching(false);
        ModeContext.validate();
        Logger.logDebug('Search cancelled via Escape key', {}, Logger.LogCategory.EVENT);
    }
    else if (ModeContext.isEditing) {
                
        actionDeselectNote();
                
        Logger.logDebug('Editing cancelled via Escape key', {
            previousNoteId: ModeContext.currentNoteId 
        }, Logger.LogCategory.EVENT);
    }
    else {
                
        Logger.logNoop('Escape key pressed but had no effect', {
            isSearching: ModeContext.isSearching,
            isEditing: ModeContext.isEditing
        });
    }
}

function handleEnterKey(event) {
    if (!event) {
        throw new Error('handleEnterKey called without an event object');
    }
        
    if (ModeContext.isEditing === undefined) {
        throw new Error('ModeContext missing isEditing property in handleEnterKey');
    }

    Logger.logDebug('Enter key pressed', {
        inEditor: ModeContext.isEditing,
        noteId: ModeContext.currentNoteId
    });

}

function handleCreateNoteShortcut(event) {
    if (!event) {
        throw new Error('handleCreateNoteShortcut called without an event object');
    }

    Logger.logDebug('Create note shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    createNote();
}

function handleCreateChildNoteShortcut(event) {
    if (!event) {
        throw new Error('handleCreateChildNoteShortcut called without an event object');
    }

    Logger.logDebug('Create child note shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    createChildNote();
}

function handleDeleteNoteShortcut(event) {
    if (!event) {
        throw new Error('handleDeleteNoteShortcut called without an event object');
    }
        
    const noteId = ModeContext.currentNoteId;

    Logger.logDebug('Delete note shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: noteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    if (noteId) {
                
        deleteNote(noteId);
    } else {
                
        Logger.logNoop('Delete shortcut pressed but no note is selected', {
            isEditing: ModeContext.isEditing,
            currentNoteId: null
        });
    }
}

function handleSearchShortcut() {
    if (typeof ModeContext.setSearching !== 'function') {
        throw new Error('ModeContext missing setSearching method in handleSearchShortcut');
    }
        
    ModeContext.setSearching(true);
    ModeContext.validate();
    Logger.logDebug('Search activated via keyboard shortcut');

}

function handleMoveNoteUpShortcut(event) {
    if (!event) {
        throw new Error('handleMoveNoteUpShortcut called without an event object');
    }

    event.preventDefault();
    event.stopPropagation();

    const noteId = ModeContext.currentNoteId;
    if (!noteId) {
        Logger.logNoop('Move up shortcut pressed but no note is selected', {
            isEditing: ModeContext.isEditing,
            currentNoteId: null
        });
        return;
    }

    Logger.logDebug('Move note up shortcut triggered', {
        noteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    moveNoteUp(noteId);
}

function handleMoveNoteDownShortcut(event) {
    if (!event) {
        throw new Error('handleMoveNoteDownShortcut called without an event object');
    }

    event.preventDefault();
    event.stopPropagation();

    const noteId = ModeContext.currentNoteId;
    if (!noteId) {
        Logger.logNoop('Move down shortcut pressed but no note is selected', {
            isEditing: ModeContext.isEditing,
            currentNoteId: null
        });
        return;
    }

    Logger.logDebug('Move note down shortcut triggered', {
        noteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    moveNoteDown(noteId);
}

function handleUndoShortcut(event) {
    if (!event) {
        throw new Error('handleUndoShortcut called without an event object');
    }

    if (ModeContext.isEditing) {
        return;  
    }

    Logger.logDebug('Undo shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    event.stopPropagation();

    actionUndo();
}

function handleRedoShortcut(event) {
    if (!event) {
        throw new Error('handleRedoShortcut called without an event object');
    }

    if (ModeContext.isEditing) {
        return;  
    }

    Logger.logDebug('Redo shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    event.stopPropagation();

    actionRedo();
}

function handleCopyNoteShortcut(event) {
    if (!event) {
        throw new Error('handleCopyNoteShortcut called without an event object');
    }

    Logger.logDebug('Copy note shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    if (!ModeContext.isEditing) {
        Logger.logNoop('Copy shortcut pressed but not in editing mode', {
            isEditing: false
        });
        return;
    }

    const currentNoteId = ModeContext.currentNoteId;
    if (!currentNoteId) {
        Logger.logNoop('Copy shortcut pressed but no note is selected', {
            isEditing: true,
            currentNoteId: null
        });
        return;
    }

    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && document.activeElement.isContentEditable) {

        Logger.logDebug('Text selection detected, using default copy behavior', {}, Logger.LogCategory.EVENT);

        if (ModeContext.clipboardNoteId) {
            Logger.logDebug('Clearing clipboard note ID due to text copy', {
                previousClipboardNoteId: ModeContext.clipboardNoteId
            }, Logger.LogCategory.EVENT);
            ModeContext.setClipboardNoteId(null);
        }
        
        return;
    }

    event.preventDefault();
    actionCopyNote();
    
    Logger.logDebug('Note copied to clipboard', {
        noteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);
}

function handlePasteNoteSiblingShortcut(event) {
    if (!event) {
        throw new Error('handlePasteNoteSiblingShortcut called without an event object');
    }

    Logger.logDebug('Paste note as sibling shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        clipboardNoteId: ModeContext.clipboardNoteId
    }, Logger.LogCategory.EVENT);

    if (!ModeContext.isEditing || !ModeContext.currentNoteId || !ModeContext.clipboardNoteId) {
        Logger.logNoop('Paste shortcut conditions not met', {
            isEditing: ModeContext.isEditing,
            currentNoteId: ModeContext.currentNoteId,
            clipboardNoteId: ModeContext.clipboardNoteId
        });
        return;
    }

    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && document.activeElement.isContentEditable) {
        Logger.logDebug('Text selection detected, using default paste', {}, Logger.LogCategory.EVENT);
        return;
    }

    event.preventDefault();
    actionPasteNoteSibling();
}

function handlePasteNoteChildShortcut(event) {
    if (!event) {
        throw new Error('handlePasteNoteChildShortcut called without an event object');
    }

    event.preventDefault();

    Logger.logDebug('Paste note as child shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        clipboardNoteId: ModeContext.clipboardNoteId
    }, Logger.LogCategory.EVENT);

    if (!ModeContext.isEditing || !ModeContext.currentNoteId || !ModeContext.clipboardNoteId) {
        Logger.logNoop('Paste as child shortcut conditions not met', {
            isEditing: ModeContext.isEditing,
            currentNoteId: ModeContext.currentNoteId,
            clipboardNoteId: ModeContext.clipboardNoteId
        });
        return;
    }
    
    actionPasteNoteChild();
}