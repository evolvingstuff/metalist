import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote, deleteNoteOutsideEdit, createChildNote, moveNoteUp, moveNoteDown, indentNote, outdentNote, actionCopyNote, actionPasteNoteSibling, actionPasteNoteChild } from '../actions/note-actions.js';
import { actionDeselectNote, actionExitEditingWithoutSavingOrRefreshing, actionSaveAndExitEditingWithoutRefreshing } from '../actions/selection-actions.js';
import { actionUndo, actionRedo } from '../actions/history-actions.js';
import { actionExitSearchMode } from '../actions/search-actions.js';
import { PasswordModal } from '../../modals/password-modal.js';
import { MemoryModal } from '../../modals/memory-modal.js';
import { HelpModal } from '../../modals/help-modal.js';
import { OntologyModal } from '../../modals/ontology-modal.js';
import { DOMUtils } from '../../dom-utils.js';
import { CONFIG } from '../../config.js';
import { ErrorHandler } from '../../error-handler.js';
import { persistTabStateSnapshot, createTabOnServer, deleteTabOnServer } from '../services/tab-state-service.js';
import { cacheNotesDomForTab, restoreNotesDomForTab, cloneNotesDomForTab, clearCachedNotesDomForTab, clearActiveNotesDom } from '../services/tab-dom-cache-service.js';
import { computeScrollAnchor } from '../services/scroll-anchor-service.js';
import { syncSearchInputValue } from '../services/search-input-service.js';
import { normalizeTagBarForNewTag, sanitizeTags, setTagBarValue, syncTagBar } from '../services/tag-bar-service.js';
import { renderMarkdownHtml } from '../services/markdown-render-service.js';
import { renderLatexHtml } from '../services/latex-render-service.js';
import { sanitizeAndInsertExternalPaste } from '../services/html-paste-sanitizer-service.js';
import { CommandPalette } from '../../command-palette/command-palette-controller.js';
import { CommandGate } from '../services/command-gate-service.js';

const memoryModal = new MemoryModal();
const helpModal = new HelpModal();
const ontologyModal = new OntologyModal();

const MODIFIER_KEYS = new Set(['Control', 'Alt', 'Shift', 'Meta']);
const NAVIGATION_KEYS = new Set([
    'ArrowUp',
    'ArrowDown',
    'ArrowLeft',
    'ArrowRight',
    'Home',
    'End',
    'PageUp',
    'PageDown',
]);
const MOVE_KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);
const DELETE_KEYS = new Set(['Backspace', 'Delete']);

let savedEditingRange = null;
let savedEditingRangeNoteId = null;
let savedEditingCursorOffset = null;

function isOntologyModalShortcut(event) {
    if (!event) {
        throw new Error('isOntologyModalShortcut called without event');
    }
    if (typeof event.key !== 'string') {
        throw new Error('isOntologyModalShortcut requires event.key');
    }

    const keyMatches = event.key === ';';
    const codeMatches = typeof event.code === 'string' && event.code === 'Semicolon';
    if (!keyMatches && !codeMatches) {
        return false;
    }
    if (!(event.metaKey || event.ctrlKey)) {
        return false;
    }
    if (event.shiftKey) {
        return false;
    }
    return true;
}

async function openOntologyModalFromShortcut() {
    if (ontologyModal.isOpen) {
        ontologyModal.focusSearchInput();
        return;
    }
    ontologyModal.open();
    ontologyModal.focusSearchInput();
}

export function initKeyboardEvents() {
        
    document.addEventListener('keydown', handleKeyDown, { capture: true });
    document.addEventListener('paste', handlePasteEvent, { capture: false });
    document.addEventListener('dragover', handleDragOverEvent, { capture: false });
    document.addEventListener('drop', handleDropEvent, { capture: false });
        
    Logger.logInit('Keyboard events handler');
    
    // Initialize search contexts list on startup
    updateSearchContextsList();
}

function handleKeyDown(event) {
    if (!event) {
        throw new Error('handleKeyDown called without an event object');
    }

    if (typeof event.key !== 'string') {
        Logger.logNoop('Ignoring keyboard event missing key', {
            eventType: event.type,
            keyValue: event.key,
        });
        return;
    }

    if (event.key === 'Enter') {
        const searchInput = document.getElementById('search-input');
        const suggestions = document.getElementById('search-suggestions');
        if (searchInput && suggestions && !suggestions.hidden && document.activeElement === searchInput) {
            Logger.logNoop('Ignoring Enter for global shortcuts while search suggestions are open');
            return;
        }
    }

    // Never interpret typing/navigation within inputs as global shortcuts.
    // In particular, Backspace/Delete must not delete notes while editing the search box.
    // Exception: Enter in the search input is treated like a global "create note" action.
	    if (event.key !== 'Escape') {
	        const target = event.target;
	        if (target instanceof HTMLElement) {
	            const tagName = target.tagName;
	            let isTextInput = false;
	            if (tagName === 'INPUT') {
	                isTextInput = true;
	            } else if (tagName === 'TEXTAREA') {
	                isTextInput = true;
	            }
	            const isSearchInput = tagName === 'INPUT' && target.id === 'search-input';
	            const isTagBarInput = tagName === 'INPUT' && target.classList.contains('note-tag-bar-input');
	            const isCommandPaletteShortcut = event.key === '/' && (event.metaKey || event.ctrlKey);
	            const isTagEditorShortcut = isOntologyModalShortcut(event);

	            if (isTextInput && !(isSearchInput && event.key === 'Enter') && !isCommandPaletteShortcut && !isTagEditorShortcut) {
	                const isCreateShortcut = event.key === 'Enter' && (event.metaKey || event.ctrlKey);
	                const isTabToggleShortcut = event.key === 'Tab';
	                if (!(isTagBarInput && (isCreateShortcut || isTabToggleShortcut))) {
	                    return;
	                }
	            }
	        }
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

    let metaOrCtrl = false;
    if (event.metaKey) {
        metaOrCtrl = true;
    } else if (event.ctrlKey) {
        metaOrCtrl = true;
    }

    ModeContext.setKeyPressed(event.key, metaOrCtrl, event.shiftKey);

    Logger.logDebug('Key pressed', {
        key: event.key,
        meta: event.metaKey || event.ctrlKey,
        shift: event.shiftKey
    }, Logger.LogCategory.EVENT);

    revealCaretForCurrentNote();

    if (ModeContext.modalStack && ModeContext.modalStack.length > 0) {
        const targetElement = event.target instanceof HTMLElement ? event.target.closest('.modal') : null;
        if (targetElement) {
            if (isOntologyModalShortcut(event)) {
                event.preventDefault();
                event.stopPropagation();
                const topModal = ModeContext.modalStack[ModeContext.modalStack.length - 1];
                if (topModal === 'ontologyModal') {
                    void openOntologyModalFromShortcut();
                }
            }
            return;
        }

        if (event.key !== 'Escape') {
            Logger.logNoop('Keyboard event ignored while a modal is open', {
                key: event.key,
                modalStack: ModeContext.modalStack.slice()
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }
    }

    if (ModeContext.isEditing) {
                
        const isModifierKey = MODIFIER_KEYS.has(event.key);
        const isNavigationKey = NAVIGATION_KEYS.has(event.key);
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
    
	    const hoveredDetails = getHoveredNoteDetails(event);

	    const isMoveKey = MOVE_KEYS.has(event.key);
	    const isDeleteKey = DELETE_KEYS.has(event.key);
	    const intendsHoverDelete = (
	        isDeleteKey &&
        !event.metaKey &&
        !event.ctrlKey &&
        !ModeContext.isEditing &&
        Boolean(hoveredDetails.noteId)
    );

    // Check if we're disconnected from server for operations that need it
    if (!ModeContext.isConnected) {
        let needsServer = false;
        if (event.key === 'Enter' && (metaOrCtrl || !ModeContext.isEditing)) {
            needsServer = true;
        } else if (isDeleteKey && (metaOrCtrl || intendsHoverDelete)) {
            needsServer = true;
	        } else if (isMoveKey && metaOrCtrl) {
	            needsServer = true;
	        } else if (event.key === 'v' && metaOrCtrl) {
	            needsServer = true;
        } else if (event.key === 'c' && metaOrCtrl) {
            needsServer = true;
        } else if ((event.key === 'z' || event.key === 'y') && metaOrCtrl) {
            needsServer = true;
        }
        
        if (needsServer) {
            Logger.logNoop('Keyboard shortcut ignored while disconnected from server', {
                key: event.key,
                meta: event.metaKey || event.ctrlKey,
                isConnected: false
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        // Allow ESC, search, and password modal even when disconnected
    }

    if (isOntologyModalShortcut(event)) {
        void handleOntologyModalShortcut(event);
        return;
    }

    switch (event.key) {
        case 'Tab':
            if (ModeContext.isEditing) {
                handleToggleTagBarFocusShortcut(event);
            }
            break;
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
            } else if (!ModeContext.isEditing && hoveredDetails.noteId) {
                handleDeleteHoveredNote(event, hoveredDetails);
            }
            break;
        case '/':
            if (event.metaKey || event.ctrlKey) {
                event.preventDefault();
                event.stopPropagation();
                void CommandPalette.toggle();
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
	        case 'ArrowLeft':
	            if (event.metaKey || event.ctrlKey) {
	                handleOutdentNoteShortcut(event);
	            }
	            break;
	        case 'ArrowRight':
	            if (event.metaKey || event.ctrlKey) {
	                handleIndentNoteShortcut(event);
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
        case 'r':
            if (event.metaKey || event.ctrlKey) {
                handleInsertEmbedReferenceShortcut(event);
            }
            break;
        case 'x':
            if (event.metaKey || event.ctrlKey) {
                void handleCutNoteShortcut(event);
            }
            break;
        case 'y':
            if (event.metaKey || event.ctrlKey) {
                handleRedoShortcut(event);
            }
            break;
        case 'p':
            if (event.metaKey || event.ctrlKey) {
                void handlePasswordModalShortcut(event);
            }
            break;
        case 'm':
            if (!event.metaKey && !event.ctrlKey && !event.shiftKey) {
                handleMemoryModalShortcut(event);
            }
            break;
        case '?':
            if (!event.metaKey && !event.ctrlKey) {
                handleHelpModalShortcut(event);
            }
            break;
        default:
            break;
                
    }
}

function handleToggleTagBarFocusShortcut(event) {
    if (!event) {
        throw new Error('handleToggleTagBarFocusShortcut called without an event object');
    }

    if (!ModeContext.isEditing || !ModeContext.currentNoteId) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    const currentNoteId = ModeContext.currentNoteId;
    const noteElement = DOMUtils.getNoteById(currentNoteId);

    const activeElement = document.activeElement;
    const activeIsTagInput = activeElement && activeElement.classList
        ? activeElement.classList.contains('note-tag-bar-input')
        : false;

	    if (activeIsTagInput) {
	        const tagInput = noteElement.querySelector('.note-tag-bar-input');
	        if (!tagInput) {
	            throw new Error('Expected tag input to exist when toggling focus back to content');
	        }
	
	        const rawTags = tagInput.value;
	        if (typeof rawTags !== 'string') {
	            throw new Error('Tag input value must be string');
	        }
	        const sanitized = sanitizeTags(rawTags);
	        setTagBarValue(noteElement, sanitized);

        const contentElement = DOMUtils.getNoteContent(noteElement);
        if (!contentElement) {
            throw new Error('Note missing content element when restoring focus');
        }

        contentElement.focus();

        if (savedEditingRange && savedEditingRangeNoteId === currentNoteId) {
            const range = savedEditingRange;
            const startOk = range.startContainer && contentElement.contains(range.startContainer);
            const endOk = range.endContainer && contentElement.contains(range.endContainer);
            if (startOk && endOk) {
                const selection = window.getSelection();
                if (!selection) {
                    throw new Error('No selection available when restoring editor range');
                }
                selection.removeAllRanges();
                selection.addRange(range);
                return;
            }
        }

        if (Number.isInteger(savedEditingCursorOffset) && savedEditingRangeNoteId === currentNoteId) {
            DOMUtils.focusNote(noteElement, savedEditingCursorOffset);
            return;
        }

        DOMUtils.focusNoteEdge(noteElement, 'end');
        return;
    }

    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const contentElement = DOMUtils.getNoteContent(noteElement);
        if (contentElement && range && range.commonAncestorContainer && contentElement.contains(range.commonAncestorContainer)) {
            savedEditingRange = range.cloneRange();
            savedEditingRangeNoteId = currentNoteId;
            savedEditingCursorOffset = null;

            const anchorNode = selection.anchorNode;
            if (anchorNode && contentElement.contains(anchorNode)) {
                savedEditingCursorOffset = DOMUtils.getCursorOffset(noteElement);
            }
        }
    }

    syncTagBar(noteElement);
    const tagInput = noteElement.querySelector('.note-tag-bar-input');
    if (!tagInput) {
        throw new Error('Tag input missing after syncTagBar');
    }

    normalizeTagBarForNewTag(noteElement, tagInput);

    tagInput.focus();
    const end = tagInput.value.length;
    tagInput.setSelectionRange(end, end);
}

function revealCaretForCurrentNote() {
    if (!ModeContext.isEditing || !ModeContext.isCaretHidden) {
        return;
    }

    const currentNoteId = ModeContext.currentNoteId;
    if (!currentNoteId) {
        return;
    }

    const noteElement = DOMUtils.getNoteById(currentNoteId);
    DOMUtils.revealCaret(noteElement);
    ModeContext.markCaretVisible();
}

function getHoveredNoteDetails(event) {
	const safeEvent = event ? event : {};

    const currentHoveredId = ModeContext.hoveredNoteId;
    if (currentHoveredId) {
        const existingElement = document.querySelector(`[data-note-id="${currentHoveredId}"]`);
        if (existingElement) {
            return { noteId: currentHoveredId, element: existingElement };
        }
    }

    if (typeof safeEvent.target?.closest === 'function') {
        const elementFromEvent = safeEvent.target.closest('.note');
        if (elementFromEvent && elementFromEvent.dataset?.noteId) {
            return {
                noteId: elementFromEvent.dataset.noteId,
                element: elementFromEvent
            };
        }
    }

    const hoveredCandidates = Array.from(document.querySelectorAll('.note:hover'));
    if (hoveredCandidates.length > 0) {
        const deepest = hoveredCandidates[hoveredCandidates.length - 1];
        if (deepest && deepest.dataset?.noteId) {
            return {
                noteId: deepest.dataset.noteId,
                element: deepest
            };
        }
    }

    return { noteId: null, element: null };
}

function handleDeleteHoveredNote(event, prefetchedDetails) {
    if (!event) {
        throw new Error('handleDeleteHoveredNote called without an event object');
    }

    if (ModeContext.isEditing) {
        return;
    }

	let resolvedDetails = prefetchedDetails;
	if (!resolvedDetails) {
		resolvedDetails = getHoveredNoteDetails(event);
	}
	const hoveredNoteId = resolvedDetails.noteId;
	if (!hoveredNoteId) {
		Logger.logNoop('Delete shortcut ignored: no hovered note');
		return;
	}

    if (!ModeContext.isConnected) {
        Logger.logNoop('Delete shortcut ignored while disconnected from server', {
            hoveredNoteId
        });
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    Logger.logDebug('Delete hovered note shortcut triggered', {
        hoveredNoteId,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    void CommandGate.run('keyboard.delete_hovered', async () => {
        await deleteNoteOutsideEdit(hoveredNoteId);
    });
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
	    void CommandGate.run('keyboard.escape.deselect', async () => {
	        await actionDeselectNote();
	    });
	            
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

    if (ModeContext.isEditing) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

	if (ModeContext.isSearching) {
		actionExitSearchMode();
	}

	void CommandGate.run('keyboard.enter.create', async () => {
		await createNote();
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

	void CommandGate.run('keyboard.create_note', async () => {
		await createNote();
	});
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

	void CommandGate.run('keyboard.create_child', async () => {
		await createChildNote();
	});
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
	    void CommandGate.run('keyboard.delete', async () => {
	        await deleteNote(noteId);
	    });
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

	void CommandGate.run('keyboard.move_up', async () => {
		await moveNoteUp(noteId);
	});
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

	void CommandGate.run('keyboard.move_down', async () => {
		await moveNoteDown(noteId);
	});
}

function handleIndentNoteShortcut(event) {
    if (!event) {
        throw new Error('handleIndentNoteShortcut called without an event object');
    }

    event.preventDefault();
    event.stopPropagation();

    const noteId = ModeContext.currentNoteId;
    if (!noteId) {
        Logger.logNoop('Indent shortcut pressed but no note is selected', {
            isEditing: ModeContext.isEditing,
            currentNoteId: null
        });
        return;
    }

    Logger.logDebug('Indent note shortcut triggered', {
        noteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

	void CommandGate.run('keyboard.indent', async () => {
		await indentNote(noteId);
	});
}

function handleOutdentNoteShortcut(event) {
    if (!event) {
        throw new Error('handleOutdentNoteShortcut called without an event object');
    }

    event.preventDefault();
    event.stopPropagation();

    const noteId = ModeContext.currentNoteId;
    if (!noteId) {
        Logger.logNoop('Outdent shortcut pressed but no note is selected', {
            isEditing: ModeContext.isEditing,
            currentNoteId: null
        });
        return;
    }

    Logger.logDebug('Outdent note shortcut triggered', {
        noteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

	void CommandGate.run('keyboard.outdent', async () => {
		await outdentNote(noteId);
	});
}

function handleUndoShortcut(event) {
    if (!event) {
        throw new Error('handleUndoShortcut called without an event object');
    }

    if (ModeContext.isEditing) {
        if (ModeContext.isDirty || ModeContext.editSessionHasEdits) {
            return;
        }

        Logger.logDebug('Undo shortcut in editing mode with no editor history; exiting edit mode first', {
            isEditing: ModeContext.isEditing,
            currentNoteId: ModeContext.currentNoteId,
            isDirty: ModeContext.isDirty,
            editSessionHasEdits: ModeContext.editSessionHasEdits
        }, Logger.LogCategory.EVENT);

        event.preventDefault();
        event.stopPropagation();

		void CommandGate.run('keyboard.undo', async () => {
			await actionUndo();
		});
		return;
	}

    Logger.logDebug('Undo shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    event.stopPropagation();

	void CommandGate.run('keyboard.undo', async () => {
		await actionUndo();
	});
}

function handleRedoShortcut(event) {
    if (!event) {
        throw new Error('handleRedoShortcut called without an event object');
    }

    if (ModeContext.isEditing) {
        if (ModeContext.isDirty || ModeContext.editSessionHasEdits) {
            return;
        }

        Logger.logDebug('Redo shortcut in editing mode with no editor history; issuing server redo', {
            isEditing: ModeContext.isEditing,
            currentNoteId: ModeContext.currentNoteId,
            isDirty: ModeContext.isDirty,
            editSessionHasEdits: ModeContext.editSessionHasEdits,
        }, Logger.LogCategory.EVENT);

        event.preventDefault();
        event.stopPropagation();

		void CommandGate.run('keyboard.redo', async () => {
			await actionRedo();
		});
		return;
	}

    Logger.logDebug('Redo shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    event.preventDefault();

    event.stopPropagation();

	void CommandGate.run('keyboard.redo', async () => {
		await actionRedo();
	});
}

async function handleCopyNoteShortcut(event) {
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

        Logger.logDebug('Text selection detected, using system clipboard for text copy', {}, Logger.LogCategory.EVENT);

        // Set clipboard mode to system and allow default browser behavior
        if (ModeContext.clipboardMode !== 'system') {
            ModeContext.setClipboardMode('system');
        }
        
        return; // Let browser handle text copy
    }

    // No text selected - do note copy
    event.preventDefault();

    if (ModeContext.clipboardMode !== 'note') {
        ModeContext.setClipboardMode('note');
    }

    const copyResult = await CommandGate.run('keyboard.copy_note', async () => {
        return await actionCopyNote();
    });
    if (copyResult === null) {
        return;
    }

    const copiedNoteId = copyResult?.note_id;
    if (typeof copiedNoteId === 'string' && copiedNoteId.length > 0) {
        if (ModeContext.clipboardNoteId !== copiedNoteId) {
            ModeContext.setClipboardNoteId(copiedNoteId);
        }
    }

    Logger.logDebug('Note copied to server clipboard', {
        noteId: ModeContext.currentNoteId
    }, Logger.LogCategory.EVENT);

    let renderedHtml = copyResult?.html;
    const renderedPlainText = copyResult?.plain_text;

    if (typeof renderedHtml === 'string') {
        renderedHtml = renderMarkdownHtml(renderedHtml);
        renderedHtml = renderLatexHtml(renderedHtml);
    }

    if (!renderedHtml && !renderedPlainText) {
        Logger.logDebug('Copy endpoint returned no rendered content', {}, Logger.LogCategory.EVENT);
        return;
    }

    if (renderedHtml && navigator.clipboard && navigator.clipboard.write) {
        const htmlBlob = new Blob([renderedHtml], { type: 'text/html' });
        const plainTextBlob = new Blob([
            renderedPlainText ?? ''
        ], { type: 'text/plain' });

        const clipboardItem = new ClipboardItem({
            'text/html': htmlBlob,
            'text/plain': plainTextBlob
        });

        await navigator.clipboard.write([clipboardItem]).catch((clipboardError) => {
            Logger.logDebug('Error copying rendered content to system clipboard', {
                error: clipboardError.message
            }, Logger.LogCategory.EVENT);
        });
        return;
    }

    if (renderedPlainText && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(renderedPlainText).catch((clipboardError) => {
            Logger.logDebug('Error copying rendered content to system clipboard', {
                error: clipboardError.message
            }, Logger.LogCategory.EVENT);
        });
        return;
    }

    if (renderedPlainText) {
        const textarea = document.createElement('textarea');
        textarea.value = renderedPlainText;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        Logger.logDebug('Rendered text copied to system clipboard via legacy fallback', {}, Logger.LogCategory.EVENT);
    }
}

function ensureSelectionInsideEditableContent(contentElement) {
    if (!contentElement) {
        throw new Error('ensureSelectionInsideEditableContent requires content element');
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable');
    }

    const hasRangeInContent = (
        selection.rangeCount > 0
        && contentElement.contains(selection.anchorNode)
        && contentElement.contains(selection.focusNode)
    );
    if (hasRangeInContent) {
        return;
    }

    const range = document.createRange();
    range.selectNodeContents(contentElement);
    range.collapse(false);
    contentElement.focus();
    selection.removeAllRanges();
    selection.addRange(range);
}

function _linePrefixText(fullText) {
    if (typeof fullText !== 'string') {
        throw new Error('_linePrefixText requires string');
    }
    const lastLf = fullText.lastIndexOf('\n');
    const lastCr = fullText.lastIndexOf('\r');
    const boundary = Math.max(lastLf, lastCr);
    if (boundary === -1) {
        return fullText;
    }
    return fullText.slice(boundary + 1);
}

function _lineSuffixText(fullText) {
    if (typeof fullText !== 'string') {
        throw new Error('_lineSuffixText requires string');
    }
    const lf = fullText.indexOf('\n');
    const cr = fullText.indexOf('\r');
    let boundary = -1;
    if (lf === -1) {
        boundary = cr;
    } else if (cr === -1) {
        boundary = lf;
    } else {
        boundary = Math.min(lf, cr);
    }
    if (boundary === -1) {
        return fullText;
    }
    return fullText.slice(0, boundary);
}

function getSelectionLineContext(contentElement) {
    if (!(contentElement instanceof HTMLElement)) {
        throw new Error('getSelectionLineContext requires content element');
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable');
    }
    if (selection.rangeCount === 0) {
        throw new Error('Selection range missing');
    }

    const range = selection.getRangeAt(0);
    if (!contentElement.contains(range.startContainer) || !contentElement.contains(range.endContainer)) {
        throw new Error('Selection is outside editable content');
    }

    const beforeRange = document.createRange();
    beforeRange.selectNodeContents(contentElement);
    beforeRange.setEnd(range.startContainer, range.startOffset);
    const beforeText = beforeRange.toString();

    const afterRange = document.createRange();
    afterRange.selectNodeContents(contentElement);
    afterRange.setStart(range.endContainer, range.endOffset);
    const afterText = afterRange.toString();

    const beforeLineText = _linePrefixText(beforeText);
    const afterLineText = _lineSuffixText(afterText);

    return {
        hasTextBeforeOnLine: beforeLineText.length > 0,
        hasTextAfterOnLine: afterLineText.length > 0,
    };
}

function insertPlainTextAtCurrentSelection(text) {
    if (typeof text !== 'string') {
        throw new Error('insertPlainTextAtCurrentSelection requires text string');
    }

    const inserted = document.execCommand('insertText', false, text);
    if (inserted) {
        return;
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable while inserting text');
    }
    if (selection.rangeCount === 0) {
        throw new Error('Selection range missing while inserting text');
    }

    const range = selection.getRangeAt(0);
    range.deleteContents();
    const textNode = document.createTextNode(text);
    range.insertNode(textNode);
    range.setStartAfter(textNode);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);
}

function handleInsertEmbedReferenceShortcut(event) {
    if (!event) {
        throw new Error('handleInsertEmbedReferenceShortcut called without an event object');
    }

    if (!ModeContext.isEditing) {
        return;
    }

    const currentNoteId = ModeContext.currentNoteId;
    if (typeof currentNoteId !== 'string' || currentNoteId.length === 0) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    const referenceNoteId = ModeContext.clipboardNoteId;
    if (typeof referenceNoteId !== 'string' || referenceNoteId.length === 0) {
        Logger.logNoop('Reference shortcut ignored: no copied note UUID available', {
            isEditing: ModeContext.isEditing,
            currentNoteId,
        });
        return;
    }

    const noteElement = DOMUtils.getNoteById(currentNoteId);
    const contentElement = DOMUtils.getNoteContent(noteElement);
    if (!(contentElement instanceof HTMLElement)) {
        throw new Error('Current note missing editable content element');
    }

    ensureSelectionInsideEditableContent(contentElement);
    const lineContext = getSelectionLineContext(contentElement);
    const referenceToken = `![[${referenceNoteId}]]`;
    let insertionText = referenceToken;
    if (lineContext.hasTextBeforeOnLine) {
        insertionText = `\n${insertionText}`;
    }
    if (lineContext.hasTextAfterOnLine) {
        insertionText = `${insertionText}\n`;
    }
    insertPlainTextAtCurrentSelection(insertionText);

    if (!ModeContext.isDirty) {
        ModeContext.setDirty(true);
    }
}

async function handleCutNoteShortcut(event) {
    if (!event) {
        throw new Error('handleCutNoteShortcut called without an event object');
    }

    Logger.logDebug('Cut note shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
    }, Logger.LogCategory.EVENT);

    if (!ModeContext.isEditing) {
        return;
    }

    const currentNoteId = ModeContext.currentNoteId;
    if (!currentNoteId) {
        return;
    }

    const activeElement = document.activeElement;
    const isTextInput = activeElement
        && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA');
    if (isTextInput) {
        const selectionStart = activeElement.selectionStart;
        const selectionEnd = activeElement.selectionEnd;
        if (typeof selectionStart === 'number' && typeof selectionEnd === 'number' && selectionEnd > selectionStart) {
            if (ModeContext.clipboardMode !== 'system') {
                ModeContext.setClipboardMode('system');
            }
            return;
        }
    }

    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && document.activeElement && document.activeElement.isContentEditable) {
        if (ModeContext.clipboardMode !== 'system') {
            ModeContext.setClipboardMode('system');
        }
        return;
    }

    if (!ModeContext.isConnected) {
        Logger.logNoop('Cut note shortcut ignored while disconnected from server', {
            isConnected: false,
        });
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    if (ModeContext.clipboardMode !== 'note') {
        ModeContext.setClipboardMode('note');
    }

    const cutResult = await CommandGate.run('keyboard.cut_note', async () => {
        const copyResult = await actionCopyNote();
        let renderedHtml = copyResult?.html;
        const renderedPlainText = copyResult?.plain_text;

        if (typeof renderedHtml === 'string') {
            renderedHtml = renderMarkdownHtml(renderedHtml);
        }

        if (renderedHtml || renderedPlainText) {
            if (
                renderedHtml
                && typeof ClipboardItem !== 'undefined'
                && navigator.clipboard
                && typeof navigator.clipboard.write === 'function'
            ) {
                const htmlBlob = new Blob([renderedHtml], { type: 'text/html' });
                const plainText = typeof renderedPlainText === 'string' ? renderedPlainText : '';
                const plainTextBlob = new Blob([
                    plainText,
                ], { type: 'text/plain' });
                await navigator.clipboard.write([
                    new ClipboardItem({
                        'text/html': htmlBlob,
                        'text/plain': plainTextBlob,
                    })
                ]);
            } else if (typeof renderedPlainText === 'string' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                await navigator.clipboard.writeText(renderedPlainText);
            }
        }

        await deleteNote(currentNoteId);
    });
    if (cutResult === null) {
        return;
    }
}

function handlePasteNoteSiblingShortcut(event) {
    if (!event) {
        throw new Error('handlePasteNoteSiblingShortcut called without an event object');
    }

    Logger.logDebug('Paste sibling shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        clipboardMode: ModeContext.clipboardMode
    }, Logger.LogCategory.EVENT);

    // Check clipboard mode to determine behavior
    if (ModeContext.clipboardMode === 'system') {
        Logger.logDebug('System clipboard mode - allowing default paste behavior', {}, Logger.LogCategory.EVENT);
        return; // NO preventDefault - let browser handle text paste
    }

    // Note clipboard mode - check conditions for note paste
    if (!ModeContext.isEditing || !ModeContext.currentNoteId) {
        Logger.logNoop('Note paste shortcut conditions not met', {
            isEditing: ModeContext.isEditing,
            currentNoteId: ModeContext.currentNoteId,
            clipboardMode: ModeContext.clipboardMode
        });
        return;
    }

    // YES preventDefault - prevent browser, do note paste
    event.preventDefault();
    void CommandGate.run('keyboard.paste_sibling', async () => {
        await actionPasteNoteSibling();
    });
}

function handlePasteNoteChildShortcut(event) {
    if (!event) {
        throw new Error('handlePasteNoteChildShortcut called without an event object');
    }

    Logger.logDebug('Paste child shortcut triggered', {
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        clipboardMode: ModeContext.clipboardMode
    }, Logger.LogCategory.EVENT);

    // Check clipboard mode to determine behavior
    if (ModeContext.clipboardMode === 'system') {
        Logger.logDebug('System clipboard mode - allowing default paste behavior', {}, Logger.LogCategory.EVENT);
        return; // NO preventDefault - let browser handle text paste
    }

    // Note clipboard mode - check conditions for note paste
    if (!ModeContext.isEditing || !ModeContext.currentNoteId) {
        Logger.logNoop('Note paste child shortcut conditions not met', {
            isEditing: ModeContext.isEditing,
            currentNoteId: ModeContext.currentNoteId,
            clipboardMode: ModeContext.clipboardMode
        });
        return;
    }
    
    // YES preventDefault - prevent browser, do note paste
    event.preventDefault();
    void CommandGate.run('keyboard.paste_child', async () => {
        await actionPasteNoteChild();
    });
}

async function handlePasswordModalShortcut(event) {
    if (!event) {
        throw new Error('handlePasswordModalShortcut called without an event object');
    }

    Logger.logDebug('Password modal shortcut triggered (Cmd+P)', {}, Logger.LogCategory.EVENT);

    event.preventDefault();
    event.stopPropagation();

    // Exit search mode if active
    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

	// Exit editing mode if active
	if (ModeContext.isEditing) {
		const result = await CommandGate.run('keyboard.password_modal.exit_editing', async () => {
			await actionSaveAndExitEditingWithoutRefreshing();
		});
		if (result === null) {
			return;
		}
	}

    // Open the password modal
    const passwordModal = new PasswordModal();
    passwordModal.open();
}

async function handleOntologyModalShortcut(event) {
    if (!event) {
        throw new Error('handleOntologyModalShortcut called without an event object');
    }

    Logger.logDebug('Ontology modal shortcut triggered (Cmd/Ctrl+;)', {}, Logger.LogCategory.EVENT);

    event.preventDefault();
    event.stopPropagation();

    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    if (ModeContext.isEditing) {
        const result = await CommandGate.run('keyboard.ontology_modal.exit_editing', async () => {
            await actionSaveAndExitEditingWithoutRefreshing();
        });
        if (result === null) {
            return;
        }
    }

    await openOntologyModalFromShortcut();
}

function handleMemoryModalShortcut(event) {
    if (!event) {
        throw new Error('handleMemoryModalShortcut called without an event object');
    }

    if (ModeContext.isEditing || ModeContext.isSearching || ModeContext.isLoading) {
        Logger.logNoop('Memory modal shortcut ignored: not in idle state', {
            isEditing: ModeContext.isEditing,
            isSearching: ModeContext.isSearching,
            isLoading: ModeContext.isLoading
        });
        return;
    }

    if (ModeContext.modalStack && ModeContext.modalStack.length > 0) {
        Logger.logNoop('Memory modal shortcut ignored: another modal already open', {
            stackDepth: ModeContext.modalStack.length
        });
        return;
    }

    event.preventDefault();
    event.stopPropagation();

	let searchQuery = ModeContext.searchQuery;
	if (typeof searchQuery !== 'string') {
		searchQuery = '';
	}
	memoryModal.openWithSearch(searchQuery);
    Logger.logDebug('Memory modal opened via keyboard shortcut', {
        searchQuery
    }, Logger.LogCategory.EVENT);
}

function handleHelpModalShortcut(event) {
    if (!event) {
        throw new Error('handleHelpModalShortcut called without an event object');
    }

    if (ModeContext.isEditing || ModeContext.isSearching || ModeContext.isLoading) {
        Logger.logNoop('Help modal shortcut ignored: not in idle state', {
            isEditing: ModeContext.isEditing,
            isSearching: ModeContext.isSearching,
            isLoading: ModeContext.isLoading
        });
        return;
    }

    if (ModeContext.modalStack && ModeContext.modalStack.length > 0) {
        Logger.logNoop('Help modal shortcut ignored: another modal already open', {
            stackDepth: ModeContext.modalStack.length
        });
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    helpModal.open();
    Logger.logDebug('Help modal opened via keyboard shortcut', {}, Logger.LogCategory.EVENT);
}

function getMaxPasteDataImageBytes() {
    return getPastePositiveIntegerConfig('MAX_DATA_IMAGE_BYTES');
}

function getPastePositiveIntegerConfig(key) {
    if (typeof key !== 'string' || key.length === 0) {
        throw new Error('getPastePositiveIntegerConfig expects non-empty key');
    }
    if (!CONFIG || !CONFIG.PASTE) {
        throw new Error('CONFIG.PASTE is required for image paste handling');
    }
    const value = CONFIG.PASTE[key];
    if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) {
        throw new Error(`CONFIG.PASTE.${key} must be a positive integer`);
    }
    return value;
}

function getEmbedTargetImageBytes() {
    const targetBytes = getPastePositiveIntegerConfig('EMBED_TARGET_IMAGE_BYTES');
    const maxBytes = getMaxPasteDataImageBytes();
    if (targetBytes > maxBytes) {
        throw new Error(
            `CONFIG.PASTE.EMBED_TARGET_IMAGE_BYTES (${targetBytes}) cannot exceed CONFIG.PASTE.MAX_DATA_IMAGE_BYTES (${maxBytes})`,
        );
    }
    return targetBytes;
}

function getEmbedMaxDimensionPx() {
    return getPastePositiveIntegerConfig('EMBED_MAX_DIMENSION_PX');
}

function getMaxClipboardImageBytes() {
    return getPastePositiveIntegerConfig('MAX_CLIPBOARD_IMAGE_BYTES');
}

function getImageFilesFromTransfer(transferData) {
    if (!transferData) {
        throw new Error('getImageFilesFromTransfer expects transferData');
    }

    const foundFiles = [];
    const seenKeys = new Set();

    const addFileCandidate = (candidate) => {
        if (!(candidate instanceof File)) {
            return;
        }
        if (typeof candidate.type !== 'string' || !candidate.type.toLowerCase().startsWith('image/')) {
            return;
        }
        const dedupeKey = `${candidate.name}|${candidate.size}|${candidate.type}|${candidate.lastModified}`;
        if (seenKeys.has(dedupeKey)) {
            return;
        }
        seenKeys.add(dedupeKey);
        foundFiles.push(candidate);
    };

    if (transferData.items && transferData.items.length > 0) {
        let i = 0;
        while (i < transferData.items.length) {
            const item = transferData.items[i];
            if (item && item.kind === 'file' && typeof item.type === 'string' && item.type.toLowerCase().startsWith('image/')) {
                const file = item.getAsFile();
                addFileCandidate(file);
            }
            i += 1;
        }
    }

    if (transferData.files && transferData.files.length > 0) {
        let i = 0;
        while (i < transferData.files.length) {
            const file = transferData.files[i];
            addFileCandidate(file);
            i += 1;
        }
    }

    if (foundFiles.length === 0) {
        return foundFiles;
    }

    foundFiles.sort((left, right) => right.size - left.size);
    return [foundFiles[0]];
}

function transferHasFiles(transferData) {
    if (!transferData) {
        return false;
    }

    if (transferData.items && transferData.items.length > 0) {
        let i = 0;
        while (i < transferData.items.length) {
            const item = transferData.items[i];
            if (item && item.kind === 'file') {
                return true;
            }
            i += 1;
        }
    }

    if (transferData.files && transferData.files.length > 0) {
        return true;
    }

    return false;
}

function readBlobAsDataUrl(blob) {
    if (!(blob instanceof Blob)) {
        throw new Error('readBlobAsDataUrl expects Blob');
    }
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => {
            reject(new Error('Failed reading image blob as data URL'));
        };
        reader.onload = () => {
            if (typeof reader.result !== 'string') {
                reject(new Error('Unexpected FileReader result type'));
                return;
            }
            resolve(reader.result);
        };
        reader.readAsDataURL(blob);
    });
}

function loadImageElementFromBlob(blob) {
    if (!(blob instanceof Blob)) {
        throw new Error('loadImageElementFromBlob expects Blob');
    }
    return new Promise((resolve, reject) => {
        const objectUrl = URL.createObjectURL(blob);
        const image = new Image();

        image.onload = () => {
            URL.revokeObjectURL(objectUrl);
            if (!Number.isFinite(image.naturalWidth) || !Number.isFinite(image.naturalHeight)) {
                reject(new Error('Loaded image has invalid dimensions'));
                return;
            }
            if (image.naturalWidth <= 0 || image.naturalHeight <= 0) {
                reject(new Error('Loaded image has zero dimensions'));
                return;
            }
            resolve(image);
        };

        image.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            reject(new Error('Failed decoding clipboard image'));
        };

        image.src = objectUrl;
    });
}

function computeScaledDimensions(sourceWidth, sourceHeight, maxDimensionPx) {
    if (!Number.isFinite(sourceWidth) || sourceWidth <= 0) {
        throw new Error(`computeScaledDimensions invalid sourceWidth: ${sourceWidth}`);
    }
    if (!Number.isFinite(sourceHeight) || sourceHeight <= 0) {
        throw new Error(`computeScaledDimensions invalid sourceHeight: ${sourceHeight}`);
    }
    if (!Number.isFinite(maxDimensionPx) || maxDimensionPx <= 0) {
        throw new Error(`computeScaledDimensions invalid maxDimensionPx: ${maxDimensionPx}`);
    }

    const largest = Math.max(sourceWidth, sourceHeight);
    if (largest <= maxDimensionPx) {
        return {
            width: Math.floor(sourceWidth),
            height: Math.floor(sourceHeight),
        };
    }

    const scale = maxDimensionPx / largest;
    return {
        width: Math.max(1, Math.floor(sourceWidth * scale)),
        height: Math.max(1, Math.floor(sourceHeight * scale)),
    };
}

function renderImageToBlob(sourceImage, width, height, mimeType, quality) {
    if (!(sourceImage instanceof HTMLImageElement)) {
        throw new Error('renderImageToBlob expects HTMLImageElement');
    }
    if (!Number.isFinite(width) || width <= 0) {
        throw new Error(`renderImageToBlob invalid width: ${width}`);
    }
    if (!Number.isFinite(height) || height <= 0) {
        throw new Error(`renderImageToBlob invalid height: ${height}`);
    }
    if (typeof mimeType !== 'string' || mimeType.length === 0) {
        throw new Error('renderImageToBlob expects mimeType');
    }

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (!context) {
        throw new Error('Canvas 2D context unavailable for image compression');
    }

    context.clearRect(0, 0, width, height);
    context.drawImage(sourceImage, 0, 0, width, height);

    return new Promise((resolve, reject) => {
        canvas.toBlob(
            (blob) => {
                if (!(blob instanceof Blob)) {
                    reject(new Error(`Canvas export failed for ${mimeType}`));
                    return;
                }
                resolve(blob);
            },
            mimeType,
            quality,
        );
    });
}

function estimateDataUrlPayloadBytes(dataUrl) {
    if (typeof dataUrl !== 'string') {
        throw new Error('estimateDataUrlPayloadBytes expects dataUrl string');
    }
    const commaIndex = dataUrl.indexOf(',');
    if (commaIndex < 0) {
        throw new Error('Data URL missing comma separator');
    }
    const payload = dataUrl.slice(commaIndex + 1).replace(/\s+/g, '');
    if (payload.length === 0) {
        return 0;
    }
    let paddingBytes = 0;
    if (payload.endsWith('==')) {
        paddingBytes = 2;
    } else if (payload.endsWith('=')) {
        paddingBytes = 1;
    }
    return Math.floor((payload.length * 3) / 4) - paddingBytes;
}

async function compressImageFileForEmbedding(file) {
    if (!(file instanceof File)) {
        throw new Error('compressImageFileForEmbedding expects File');
    }
    if (typeof file.size !== 'number' || file.size <= 0) {
        throw new Error(`Clipboard image has invalid size: ${file.size}`);
    }

    const maxClipboardBytes = getMaxClipboardImageBytes();
    if (file.size > maxClipboardBytes) {
        const maxMiB = (maxClipboardBytes / (1024 * 1024)).toFixed(1);
        ErrorHandler.showErrorBanner(
            `Image too large to process (${file.name || 'clipboard image'}). Max allowed is ${maxMiB} MiB.`,
            'error',
            6000,
            true,
        );
        return null;
    }

    const sourceImage = await loadImageElementFromBlob(file);
    const maxDimensionPx = getEmbedMaxDimensionPx();
    const targetBytes = getEmbedTargetImageBytes();
    const hardMaxBytes = getMaxPasteDataImageBytes();
    const initialSize = computeScaledDimensions(sourceImage.naturalWidth, sourceImage.naturalHeight, maxDimensionPx);

    const encodePlans = [
        { mimeType: 'image/webp', qualities: [0.82, 0.72, 0.62, 0.52, 0.42] },
        { mimeType: 'image/jpeg', qualities: [0.82, 0.72, 0.62, 0.52] },
    ];

    let bestBlob = null;
    let planIndex = 0;
    while (planIndex < encodePlans.length) {
        const plan = encodePlans[planIndex];
        let width = initialSize.width;
        let height = initialSize.height;

        while (true) {
            let qualityIndex = 0;
            while (qualityIndex < plan.qualities.length) {
                const quality = plan.qualities[qualityIndex];
                const candidate = await renderImageToBlob(sourceImage, width, height, plan.mimeType, quality);

                if (bestBlob === null || candidate.size < bestBlob.size) {
                    bestBlob = candidate;
                }
                if (candidate.size <= targetBytes) {
                    return candidate;
                }

                qualityIndex += 1;
            }

            if (Math.max(width, height) <= 512) {
                break;
            }
            width = Math.max(1, Math.floor(width * 0.85));
            height = Math.max(1, Math.floor(height * 0.85));
        }

        planIndex += 1;
    }

    if (bestBlob !== null && bestBlob.size <= hardMaxBytes) {
        return bestBlob;
    }

    return null;
}

async function imageFileToEmbeddedDataUrl(file) {
    const compressedBlob = await compressImageFileForEmbedding(file);
    if (!(compressedBlob instanceof Blob)) {
        return null;
    }
    const dataUrl = await readBlobAsDataUrl(compressedBlob);
    const payloadBytes = estimateDataUrlPayloadBytes(dataUrl);
    const maxBytes = getMaxPasteDataImageBytes();
    if (payloadBytes > maxBytes) {
        throw new Error(
            `Compressed clipboard image exceeds MAX_DATA_IMAGE_BYTES: ${payloadBytes} > ${maxBytes}`,
        );
    }
    return dataUrl;
}

function formatKiB(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) {
        throw new Error(`formatKiB invalid bytes: ${bytes}`);
    }
    return `${(bytes / 1024).toFixed(1)} KiB`;
}

function formatMiB(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) {
        throw new Error(`formatMiB invalid bytes: ${bytes}`);
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function showImageTooLargeForEmbedError(fileName) {
    const targetBytes = getEmbedTargetImageBytes();
    const maxBytes = getMaxPasteDataImageBytes();
    const label = typeof fileName === 'string' && fileName.length > 0
        ? fileName
        : 'clipboard image';
    ErrorHandler.showErrorBanner(
        `Could not shrink ${label} enough. Target ${formatKiB(targetBytes)}, hard max ${formatMiB(maxBytes)}.`,
        'error',
        6500,
        true,
    );
}

function showImageEmbedFailureError() {
    ErrorHandler.showErrorBanner(
        'Failed to embed pasted image. Copy image pixels (not Finder icon preview) and paste again.',
        'error',
        6000,
        true,
    );
}

function buildEmbeddedImageHtmlFromDataUrls(dataUrls) {
    if (!Array.isArray(dataUrls)) {
        throw new Error('buildEmbeddedImageHtmlFromDataUrls expects array');
    }
    if (dataUrls.length === 0) {
        return '';
    }

    let html = '';
    let i = 0;
    while (i < dataUrls.length) {
        const dataUrl = dataUrls[i];
        if (typeof dataUrl !== 'string' || !dataUrl.startsWith('data:image/')) {
            throw new Error(`Invalid data URL at index ${i}`);
        }

        const imageIndex = i + 1;
        html += `<img src="${dataUrl}" alt="pasted-image-${imageIndex}" style="max-width: 100%; width: auto; height: auto;" />`;
        if (imageIndex < dataUrls.length) {
            html += '<br />';
        }
        i += 1;
    }
    return html;
}

function clipboardHasFileUriReference(clipboardData) {
    if (!clipboardData || typeof clipboardData.getData !== 'function') {
        return false;
    }

    const uriList = clipboardData.getData('text/uri-list');
    if (typeof uriList !== 'string' || uriList.length === 0) {
        return false;
    }

    const lines = uriList.split(/\r?\n/);
    let i = 0;
    while (i < lines.length) {
        const line = lines[i].trim();
        if (line.length > 0 && !line.startsWith('#') && line.toLowerCase().startsWith('file://')) {
            return true;
        }
        i += 1;
    }
    return false;
}

function resolveEditingDropTarget(event) {
    if (!event) {
        throw new Error('resolveEditingDropTarget expects event');
    }
    if (!ModeContext.isEditing || !ModeContext.currentNoteId) {
        return null;
    }

    const rawTarget = event.target;
    if (!(rawTarget instanceof Element)) {
        return null;
    }

    const noteContent = rawTarget.closest('.note-content');
    if (!(noteContent instanceof HTMLElement)) {
        return null;
    }
    if (noteContent.getAttribute('contenteditable') !== 'true') {
        return null;
    }

    const noteElement = noteContent.closest('.note');
    if (!(noteElement instanceof HTMLElement)) {
        return null;
    }
    const noteId = noteElement.dataset.noteId;
    if (!noteId || noteId !== ModeContext.currentNoteId) {
        return null;
    }

    return noteContent;
}

function placeCaretAtEnd(element) {
    if (!(element instanceof HTMLElement)) {
        throw new Error('placeCaretAtEnd expects HTMLElement');
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable while placing caret');
    }

    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
}

function placeCaretAtDropPoint(noteContent, event) {
    if (!(noteContent instanceof HTMLElement)) {
        throw new Error('placeCaretAtDropPoint expects HTMLElement noteContent');
    }
    if (!event) {
        throw new Error('placeCaretAtDropPoint expects event');
    }
    if (typeof event.clientX !== 'number' || typeof event.clientY !== 'number') {
        return false;
    }

    let range = null;
    if (typeof document.caretRangeFromPoint === 'function') {
        range = document.caretRangeFromPoint(event.clientX, event.clientY);
    } else if (typeof document.caretPositionFromPoint === 'function') {
        const position = document.caretPositionFromPoint(event.clientX, event.clientY);
        if (position && position.offsetNode) {
            const candidateRange = document.createRange();
            candidateRange.setStart(position.offsetNode, position.offset);
            candidateRange.collapse(true);
            range = candidateRange;
        }
    }

    if (!(range instanceof Range)) {
        return false;
    }
    if (!noteContent.contains(range.startContainer)) {
        return false;
    }

    const selection = window.getSelection();
    if (!selection) {
        throw new Error('Selection API unavailable while placing drop caret');
    }

    selection.removeAllRanges();
    selection.addRange(range);
    return true;
}

async function pasteClipboardImagesAsEmbeddedContent(files) {
    if (!Array.isArray(files) || files.length === 0) {
        return false;
    }

    const dataUrls = [];

    let i = 0;
    while (i < files.length) {
        const file = files[i];
        if (!(file instanceof File)) {
            throw new Error(`Clipboard image at index ${i} is not a File`);
        }
        const dataUrl = await imageFileToEmbeddedDataUrl(file);
        if (dataUrl === null) {
            showImageTooLargeForEmbedError(file.name);
            return false;
        }
        const embeddedPayloadBytes = estimateDataUrlPayloadBytes(dataUrl);
        Logger.logDebug('Clipboard image compressed for embed', {
            fileName: file.name || null,
            originalBytes: file.size,
            embeddedPayloadBytes,
            embedTargetBytes: getEmbedTargetImageBytes(),
            embedMaxBytes: getMaxPasteDataImageBytes(),
        }, Logger.LogCategory.EVENT);
        dataUrls.push(dataUrl);
        i += 1;
    }

    const html = buildEmbeddedImageHtmlFromDataUrls(dataUrls);
    if (html.length === 0) {
        return false;
    }

    const syntheticPasteEvent = {
        clipboardData: {
            getData(format) {
                if (format === 'text/html') {
                    return html;
                }
                return '';
            },
        },
    };
    return sanitizeAndInsertExternalPaste(syntheticPasteEvent);
}

function handleDragOverEvent(event) {
    if (!event || !event.dataTransfer) {
        return;
    }

    const target = resolveEditingDropTarget(event);
    if (!(target instanceof HTMLElement)) {
        return;
    }
    if (!transferHasFiles(event.dataTransfer)) {
        return;
    }

    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
}

function handleDropEvent(event) {
    if (!event || !event.dataTransfer) {
        return;
    }

    const target = resolveEditingDropTarget(event);
    if (!(target instanceof HTMLElement)) {
        return;
    }
    if (!transferHasFiles(event.dataTransfer)) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    const imageFiles = getImageFilesFromTransfer(event.dataTransfer);
    if (imageFiles.length === 0) {
        ErrorHandler.showErrorBanner(
            'Dropped file is not a supported image.',
            'error',
            5000,
            true,
        );
        return;
    }

    target.focus();
    const positioned = placeCaretAtDropPoint(target, event);
    if (!positioned) {
        placeCaretAtEnd(target);
    }

    void pasteClipboardImagesAsEmbeddedContent(imageFiles)
        .then((inserted) => {
            Logger.logDebug('Dropped image file handled', {
                imageCount: imageFiles.length,
                inserted,
                selectedImageBytes: imageFiles[0] ? imageFiles[0].size : null,
            }, Logger.LogCategory.EVENT);

            if (inserted && !ModeContext.isDirty) {
                ModeContext.setDirty(true);
                Logger.logDebug('Content marked as dirty due to dropped embedded image', {
                    noteId: ModeContext.currentNoteId,
                }, Logger.LogCategory.STATE);
            }
        })
        .catch((error) => {
            const message = error instanceof Error ? error.message : String(error);
            Logger.logDebug('Dropped image file handling failed', {
                error: message,
            }, Logger.LogCategory.EVENT);
            showImageEmbedFailureError();
        });
}


function handlePasteEvent(event) {
    if (!event || !event.clipboardData) {
        Logger.logDebug('Paste event without clipboard data - allowing default behavior', {}, Logger.LogCategory.EVENT);
        return;
    }

    const activeElement = document.activeElement;
    const hasEditableTarget = Boolean(activeElement && activeElement.isContentEditable);
    const shouldHandleInlinePaste = ModeContext.isEditing && hasEditableTarget;
    const imageFiles = shouldHandleInlinePaste ? getImageFilesFromTransfer(event.clipboardData) : [];

    if (shouldHandleInlinePaste) {
        if (imageFiles.length > 0) {
            event.preventDefault();
            void pasteClipboardImagesAsEmbeddedContent(imageFiles)
                .then((inserted) => {
                    Logger.logDebug('Clipboard image paste handled', {
                        imageCount: imageFiles.length,
                        inserted,
                        selectedImageBytes: imageFiles[0] ? imageFiles[0].size : null,
                    }, Logger.LogCategory.EVENT);

                    if (inserted && !ModeContext.isDirty) {
                        ModeContext.setDirty(true);
                        Logger.logDebug('Content marked as dirty due to embedded image paste', {
                            noteId: ModeContext.currentNoteId,
                        }, Logger.LogCategory.STATE);
                    }
                })
                .catch((error) => {
                    const message = error instanceof Error ? error.message : String(error);
                    Logger.logDebug('Clipboard image paste failed', {
                        error: message,
                    }, Logger.LogCategory.EVENT);
                    showImageEmbedFailureError();
                });
            return;
        }
    }

    // Get HTML from clipboard if available
    const html = event.clipboardData.getData('text/html');
    
    Logger.logDebug('Paste event detected', {
        hasHtml: !!html,
        htmlLength: html ? html.length : 0,
        imageFileCount: imageFiles.length,
        hasFileUriReference: clipboardHasFileUriReference(event.clipboardData),
        isEditing: ModeContext.isEditing
    }, Logger.LogCategory.EVENT);

    if (
        shouldHandleInlinePaste
        && imageFiles.length === 0
        && typeof html === 'string'
        && html.includes('<img')
        && clipboardHasFileUriReference(event.clipboardData)
    ) {
        event.preventDefault();
        ErrorHandler.showErrorBanner(
            'Clipboard contains a file reference/icon preview, not image bytes. Open the image and copy the pixels, then paste again.',
            'error',
            7000,
            true,
        );
        return;
    }

    // Check if this is our note HTML (contains note-content class)
    if (html && html.includes('class="note-content"')) {
        Logger.logDebug('Detected note HTML in clipboard - using server clipboard', {}, Logger.LogCategory.EVENT);
        
        // This is our note HTML - prevent default and use server clipboard
        if (ModeContext.isEditing && ModeContext.currentNoteId) {
            event.preventDefault();
            
			// Determine if shift is held for child paste
			if (event.shiftKey) {
				void CommandGate.run('paste_event.child', async () => {
					await actionPasteNoteChild();
				});
			} else {
				void CommandGate.run('paste_event.sibling', async () => {
					await actionPasteNoteSibling();
				});
			}
		}
	} else {
        const shouldSanitizeExternalHtml = ModeContext.isEditing && hasEditableTarget && typeof html === 'string' && html.length > 0;

        if (shouldSanitizeExternalHtml) {
            event.preventDefault();
            const inserted = sanitizeAndInsertExternalPaste(event);
            Logger.logDebug('External HTML paste sanitized and inserted', {
                inserted,
                htmlLength: html.length
            }, Logger.LogCategory.EVENT);
        } else {
            Logger.logDebug('External content detected - using browser default paste', {
                hasHtml: !!html
            }, Logger.LogCategory.EVENT);
        }
        
        // Mark content as dirty since we're pasting external content
        if (ModeContext.isEditing && !ModeContext.isDirty) {
            ModeContext.setDirty(true);
            Logger.logDebug('Content marked as dirty due to paste', {
                noteId: ModeContext.currentNoteId
            }, Logger.LogCategory.STATE);
        }
    }
}

export function updateSearchContextsList() {
    const searchContextsList = document.getElementById('search-contexts-list');
    if (!searchContextsList) return;
    const showTabUi = document.body.classList.contains('pref-show-tab-ui');
    
    const tabs = ModeContext.tabs;
    const activeTabId = ModeContext.activeTabId;
    const tabOrder = ModeContext.tabOrder;

    if (!CONFIG.TABS || typeof CONFIG.TABS.MAX_TABS !== 'number' || CONFIG.TABS.MAX_TABS <= 0) {
        throw new Error('CONFIG.TABS.MAX_TABS must be a positive number');
    }
    
    // Build the list of search contexts
    let contextsList = [];
    if (!Array.isArray(tabOrder) || tabOrder.length === 0) {
        throw new Error('ModeContext.tabOrder must be a non-empty array');
    }
	for (let i = 0; i < tabOrder.length; i++) {
	    const tabId = tabOrder[i];
	    const tabEntry = tabs[tabId];
	    if (!tabEntry || typeof tabEntry !== 'object') {
	        throw new Error(`ModeContext.tabs missing entry for tab ${tabId}`);
	    }

	    let originalQuery = tabEntry.searchQuery;
	    if (typeof originalQuery !== 'string') {
	        originalQuery = '';
	    }
	    let displayQuery = originalQuery;
	    if (!displayQuery) {
	        displayQuery = '(empty)';
	    }
        
        // Truncate long search queries for display
        if (displayQuery.length > 12 && displayQuery !== '(empty)') {
            displayQuery = displayQuery.substring(0, 12) + '...';
        }
        
        const isActive = tabId === activeTabId;

        const atLimit = tabOrder.length >= CONFIG.TABS.MAX_TABS;
        const addClass = atLimit ? 'is-disabled' : '';
        const canDelete = tabOrder.length > 1;
        const deleteClass = canDelete ? '' : 'is-disabled';

        const canMoveUp = tabOrder.length > 1 && i > 0;
        const canMoveDown = tabOrder.length > 1 && i < tabOrder.length - 1;

        const moveUpClass = canMoveUp ? '' : 'is-hidden';
        const moveDownClass = canMoveDown ? '' : 'is-hidden';

        const actions = `
            <span class="tab-context-action duplicate-context ${addClass}" data-source-tab-id="${tabId}" aria-disabled="${atLimit}">+</span>
            <span class="tab-context-action tab-context-action--danger delete-context ${deleteClass}" data-delete-tab-id="${tabId}" aria-disabled="${!canDelete}">-</span>
            <span class="tab-context-action move-up-context ${moveUpClass}" data-move-tab-id="${tabId}">↑</span>
            <span class="tab-context-action move-down-context ${moveDownClass}" data-move-tab-id="${tabId}">↓</span>
        `;

        const activeClass = isActive ? 'is-active' : '';
        contextsList.push(
            `<div data-tab-id="${tabId}" class="tab-context-item ${activeClass}">`
            + `<span class="tab-context-index">${i + 1}:</span>`
            + `<span class="tab-context-query">${displayQuery}</span>`
            + `<span class="tab-context-actions">${actions}</span>`
            + `</div>`
        );
    }
    
    if (contextsList.length > 0) {
        searchContextsList.innerHTML = contextsList.join('');
        if (showTabUi) {
            searchContextsList.style.display = 'block';
        } else {
            searchContextsList.style.display = 'none';
        }
        
        // Add click handlers to each tab context item
        searchContextsList.querySelectorAll('.tab-context-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const tabId = e.currentTarget.getAttribute('data-tab-id');
                if (!tabId || tabId === ModeContext.activeTabId) {
                    return;
                }
					void CommandGate.run('tab.switch', async () => {
						await switchToTabContext(tabId, {});
					});
	            });
	        });
        
        // Add click handlers for per-tab + (duplicate)
        searchContextsList.querySelectorAll('.duplicate-context').forEach(addBtn => {
            addBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (e.currentTarget.getAttribute('aria-disabled') === 'true') {
                    return;
                }
                const sourceTabId = e.currentTarget.getAttribute('data-source-tab-id');
	                void CommandGate.run('tab.duplicate', async () => {
	                    await duplicateTabContext(sourceTabId);
	                });
	            });
	        });
        
        // Add click handler for delete buttons
        searchContextsList.querySelectorAll('.delete-context').forEach(deleteBtn => {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (e.currentTarget.getAttribute('aria-disabled') === 'true') {
                    return;
                }
                const deleteTabId = e.currentTarget.getAttribute('data-delete-tab-id');
	                void CommandGate.run('tab.delete', async () => {
	                    await deleteTabContext(deleteTabId);
	                });
	            });
	        });

        searchContextsList.querySelectorAll('.move-up-context').forEach(moveBtn => {
            moveBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const moveTabId = e.currentTarget.getAttribute('data-move-tab-id');
	                void CommandGate.run('tab.move_up', async () => {
	                    await moveTabContext(moveTabId, -1);
	                });
	            });
	        });

	        searchContextsList.querySelectorAll('.move-down-context').forEach(moveBtn => {
	            moveBtn.addEventListener('click', (e) => {
	                e.stopPropagation();
	                const moveTabId = e.currentTarget.getAttribute('data-move-tab-id');
	                void CommandGate.run('tab.move_down', async () => {
	                    await moveTabContext(moveTabId, 1);
	                });
	            });
	        });
        
    } else {
        searchContextsList.style.display = 'none';
    }
}

async function switchToTabContext(tabId, options) {
	if (options === null || typeof options !== 'object') {
		throw new Error('switchToTabContext requires options object');
	}

    if (ModeContext.isEditing) {
        await actionSaveAndExitEditingWithoutRefreshing();
    }

    const previousTabId = ModeContext.activeTabId;
    const tabOrder = ModeContext.tabOrder;
    if (!Array.isArray(tabOrder) || tabOrder.length === 0) {
        throw new Error('ModeContext.tabOrder must be a non-empty array');
    }
    const previousTabIndex = tabOrder.indexOf(previousTabId);
    if (previousTabIndex === -1) {
        throw new Error(`previousTabId not present in ModeContext.tabOrder: ${previousTabId}`);
    }
    const nextTabIndex = tabOrder.indexOf(tabId);
    if (nextTabIndex === -1) {
        throw new Error(`tabId not present in ModeContext.tabOrder: ${tabId}`);
    }
    const perfContext = `switchTab tab#${previousTabIndex + 1}→tab#${nextTabIndex + 1}`;

	ModeContext.beginIgnoreScrollEvents();
	await (async () => {
		await persistCurrentTabState();

		ModeContext.switchToTab(tabId, { force: true });
		cacheNotesDomForTab(previousTabId);
		restoreNotesDomForTab(tabId);

		syncSearchInputField();
		updateSearchContextsList();

		// Persist new tab selection and any newly created tab immediately
		await persistTabStateSnapshot();

		const startedAt = performance.now();
		const { actionRefreshAndMaybeSelect } = await import('../actions/ui-actions.js');
		await actionRefreshAndMaybeSelect({
			startedAt,
			context: perfContext,
			expectedUpdatedNotesMax: options.expectedUpdatedNotesMax,
			expectedVdomOpsMax: options.expectedVdomOpsMax,
		});

		ModeContext.restoreScrollForActiveTab();
	})().finally(() => {
		ModeContext.endIgnoreScrollEvents();
	});
}

function snapshotActiveTabScrollState() {
    const currentScroll = Math.max(0, Math.round(window.scrollY));
    ModeContext.updateActiveTabScroll(currentScroll);
    ModeContext.updateActiveTabScrollAnchor(computeScrollAnchor({ anchorBias: 'auto' }), true);
}

async function duplicateTabContext(sourceTabId) {
	const startedEditing = ModeContext.isEditing;

    if (startedEditing) {
        await actionSaveAndExitEditingWithoutRefreshing();
    }
    if (typeof sourceTabId !== 'string' || sourceTabId.length === 0) {
        throw new Error('sourceTabId is required for tab duplication');
    }
    if (!CONFIG.TABS || typeof CONFIG.TABS.MAX_TABS !== 'number' || CONFIG.TABS.MAX_TABS <= 0) {
        throw new Error('CONFIG.TABS.MAX_TABS must be a positive number');
    }
    if (typeof CONFIG.TABS.CREATE_AND_SWITCH !== 'boolean') {
        throw new Error('CONFIG.TABS.CREATE_AND_SWITCH must be a boolean');
    }

    if (!ModeContext.tabs[sourceTabId]) {
        throw new Error(`Cannot duplicate missing tab: ${sourceTabId}`);
    }

    const payload = ModeContext.getTabStatePayload();
	if (payload.tabOrder.length >= CONFIG.TABS.MAX_TABS) {
		ErrorHandler.showInfoBanner(
			`Tab limit reached (${CONFIG.TABS.MAX_TABS}). Close a tab before adding another.`,
			6000,
		);
		return;
	}

    snapshotActiveTabScrollState();
    await persistTabStateSnapshot();

    const sourceEntry = ModeContext.tabs[sourceTabId];
    if (!sourceEntry || typeof sourceEntry !== 'object') {
        throw new Error(`Cannot duplicate tab with missing state: ${sourceTabId}`);
    }

    const response = await createTabOnServer(sourceTabId);
    const newTabId = response?.newTabId;
    if (typeof newTabId !== 'string' || newTabId.length === 0) {
        throw new Error('Server did not return newTabId');
    }

    if (!response || typeof response !== 'object' || !response.tabs || typeof response.tabs !== 'object') {
        throw new Error('Server did not return tab-state payload');
    }
    if (!response.tabs[newTabId] || typeof response.tabs[newTabId] !== 'object') {
        throw new Error('Server tab-state response missing new tab payload');
    }

    const sourceScrollY = typeof sourceEntry.scrollY === 'number' && sourceEntry.scrollY >= 0
        ? Math.round(sourceEntry.scrollY)
        : 0;
    const sourceSearchQuery = typeof sourceEntry.searchQuery === 'string' ? sourceEntry.searchQuery : '';
    const sourceScrollAnchor = sourceEntry.scrollAnchor && typeof sourceEntry.scrollAnchor === 'object'
        ? sourceEntry.scrollAnchor
        : null;

	let sourceAnchorRootId = null;
	if (sourceTabId === ModeContext.activeTabId) {
		let anchorRootId = ModeContext.getRootAnchorId();
		if (!anchorRootId) {
			anchorRootId = ModeContext.getLastKnownRootId();
		}
		sourceAnchorRootId = anchorRootId;
	} else if (typeof sourceEntry.anchorRootId === 'string' && sourceEntry.anchorRootId.length > 0) {
		sourceAnchorRootId = sourceEntry.anchorRootId;
	}

    response.tabs[newTabId].scrollY = sourceScrollY;
    response.tabs[newTabId].searchQuery = sourceSearchQuery;
    response.tabs[newTabId].scrollAnchor = sourceScrollAnchor;
    response.tabs[newTabId].anchorRootId = sourceAnchorRootId;

    const sourceHashCount = ModeContext.getTabNoteHashCount(sourceTabId);
    if (sourceHashCount <= 0) {
        throw new Error('Cannot duplicate tab: source tab has no diff cache yet');
    }
    const cloneResult = cloneNotesDomForTab(sourceTabId, newTabId, {
        activeTabId: ModeContext.activeTabId,
        collectNoteHashes: sourceHashCount === 0,
    });
    if (!cloneResult.cloned) {
        throw new Error('Cannot duplicate tab: source tab DOM is not cached');
    }

    ModeContext.hydrateTabState(response);

    // Only seed the new tab's diff cache if we also cloned its DOM.
    // If we seed hashes without DOM, the server can legitimately return a
    // bootstrap payload with an empty `notes` map (hashes match), and the
    // client would then crash when it needs note payloads to insert nodes.
    if (cloneResult.cloned && cloneResult.nodeCount > 0) {
        const hashCloneResult = ModeContext.cloneTabNoteHashes(sourceTabId, newTabId);
        if (!hashCloneResult.cloned && cloneResult.noteHashes instanceof Map) {
            ModeContext.seedTabNoteHashes(newTabId, cloneResult.noteHashes);
        } else if (!hashCloneResult.cloned) {
            throw new Error('Cannot duplicate tab: failed to seed diff cache for new tab');
        }
    }
    updateSearchContextsList();

    if (CONFIG.TABS.CREATE_AND_SWITCH) {
        const switchOptions = startedEditing
            ? {}
            : {
                expectedUpdatedNotesMax: 0,
                expectedVdomOpsMax: 0,
            };

        await switchToTabContext(newTabId, switchOptions);
        return;
    }

    return;
}

async function moveTabContext(tabId, delta) {
	if (ModeContext.isEditing) {
		await actionSaveAndExitEditingWithoutRefreshing();
	}
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('tabId is required for tab reorder');
    }
    if (delta !== -1 && delta !== 1) {
        throw new Error('delta must be -1 or 1 for tab reorder');
    }

    const tabOrder = ModeContext.tabOrder;
    if (!Array.isArray(tabOrder) || tabOrder.length === 0) {
        throw new Error('ModeContext.tabOrder must be a non-empty array');
    }
    if (tabOrder.length === 1) {
        return;
    }

    const index = tabOrder.indexOf(tabId);
    if (index === -1) {
        return;
    }
    const target = index + delta;
    if (target < 0 || target >= tabOrder.length) {
        return;
    }

    const currentScroll = Math.max(0, Math.round(window.scrollY));
    ModeContext.updateActiveTabScroll(currentScroll);
    ModeContext.updateActiveTabScrollAnchor(computeScrollAnchor({ anchorBias: 'auto' }), true);

    ModeContext.moveTabInOrder(tabId, delta);
    updateSearchContextsList();
    await persistTabStateSnapshot();
}

async function deleteTabContext(deleteTabId) {
	if (ModeContext.isEditing) {
		await actionSaveAndExitEditingWithoutRefreshing();
	}
    if (typeof deleteTabId !== 'string' || deleteTabId.length === 0) {
        throw new Error('deleteTabId is required for tab deletion');
    }

    const payload = ModeContext.getTabStatePayload();
    if (payload.tabOrder.length <= 1) {
        return;
    }
    if (!payload.tabs[deleteTabId]) {
        throw new Error(`Cannot delete missing tab: ${deleteTabId}`);
    }

    const activeBeforeDelete = ModeContext.activeTabId;
    const beforeTabOrder = payload.tabOrder;
    if (!Array.isArray(beforeTabOrder) || beforeTabOrder.length === 0) {
        throw new Error('ModeContext.tabOrder must be a non-empty array');
    }
    const activeBeforeIndex = beforeTabOrder.indexOf(activeBeforeDelete);
    if (activeBeforeIndex === -1) {
        throw new Error(`activeTabId not present in ModeContext.tabOrder: ${activeBeforeDelete}`);
    }
    const deleteTabIndex = beforeTabOrder.indexOf(deleteTabId);
    if (deleteTabIndex === -1) {
        throw new Error(`deleteTabId not present in ModeContext.tabOrder: ${deleteTabId}`);
    }

    if (deleteTabId === activeBeforeDelete) {
        clearActiveNotesDom();
    } else {
        clearCachedNotesDomForTab(deleteTabId);
    }

    snapshotActiveTabScrollState();
    await persistTabStateSnapshot();

    const response = await deleteTabOnServer(deleteTabId);
    ModeContext.hydrateTabState(response);

    syncSearchInputField();
    updateSearchContextsList();

    if (ModeContext.activeTabId !== activeBeforeDelete) {
        restoreNotesDomForTab(ModeContext.activeTabId);
        const afterTabOrder = ModeContext.tabOrder;
        if (!Array.isArray(afterTabOrder) || afterTabOrder.length === 0) {
            throw new Error('ModeContext.tabOrder must be a non-empty array');
        }
        const activeAfterIndex = afterTabOrder.indexOf(ModeContext.activeTabId);
        if (activeAfterIndex === -1) {
            throw new Error(`activeTabId not present in ModeContext.tabOrder: ${ModeContext.activeTabId}`);
        }
        const perfContext = `deleteTab tab#${deleteTabIndex + 1}→switch tab#${activeBeforeIndex + 1}→tab#${activeAfterIndex + 1}`;
        const startedAt = performance.now();
        const { actionRefreshAndMaybeSelect } = await import('../actions/ui-actions.js');
        await actionRefreshAndMaybeSelect({ startedAt, context: perfContext });
        ModeContext.restoreScrollForActiveTab();
    }
}

function syncSearchInputField() {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) {
        return;
    }

    const activeQuery = ModeContext.searchQuery;
    if (typeof activeQuery !== 'string') {
        throw new Error('ModeContext.searchQuery must be a string');
    }

    syncSearchInputValue(searchInput, activeQuery);
}

async function persistCurrentTabState() {
    const currentScroll = Math.max(0, Math.round(window.scrollY));
    ModeContext.updateActiveTabScroll(currentScroll);
    ModeContext.updateActiveTabScrollAnchor(computeScrollAnchor({ anchorBias: 'auto' }), true);
    await persistTabStateSnapshot();
}
