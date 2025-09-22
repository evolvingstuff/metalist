import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote, deleteNoteOutsideEdit, createChildNote, moveNoteUp, moveNoteDown, collapseNote, expandNote, actionCopyNote, actionPasteNoteSibling, actionPasteNoteChild } from '../actions/note-actions.js';
import { actionDeselectNote } from '../actions/selection-actions.js';
import { actionUndo, actionRedo } from '../actions/history-actions.js';
import { actionExitSearchMode } from '../actions/search-actions.js';
import { PasswordModal } from '../../modals/password-modal.js';

export function initKeyboardEvents() {
        
    document.addEventListener('keydown', handleKeyDown, { capture: true });
    document.addEventListener('paste', handlePasteEvent, { capture: false });
        
    Logger.logInit('Keyboard events handler');
    
    // Initialize search contexts list on startup
    updateSearchContextsList();
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
    
    const hoveredDetails = getHoveredNoteDetails(event);

    const isArrowKey = event.key === 'ArrowUp' || event.key === 'ArrowDown';
    const intendsHoverMove = (
        isArrowKey &&
        !event.metaKey &&
        !event.ctrlKey &&
        !ModeContext.isEditing &&
        Boolean(hoveredDetails.noteId)
    );
    const isDeleteKey = event.key === 'Backspace' || event.key === 'Delete';
    const intendsHoverDelete = (
        isDeleteKey &&
        !event.metaKey &&
        !event.ctrlKey &&
        !ModeContext.isEditing &&
        Boolean(hoveredDetails.noteId)
    );

    // Check if we're disconnected from server for operations that need it
    if (!ModeContext.isConnected) {
        const needsServer = (
            // Create/delete operations
            (event.key === 'Enter' && ((event.metaKey || event.ctrlKey) || !ModeContext.isEditing)) ||
            ((event.key === 'Backspace' || event.key === 'Delete') && ((event.metaKey || event.ctrlKey) || intendsHoverDelete)) ||
            // Move operations
            (isArrowKey && ((event.metaKey || event.ctrlKey) || intendsHoverMove)) ||
            // Paste operations
            (event.key === 'v' && (event.metaKey || event.ctrlKey)) ||
            // Copy operations
            (event.key === 'c' && (event.metaKey || event.ctrlKey)) ||
            // Undo/redo
            ((event.key === 'z' || event.key === 'y') && (event.metaKey || event.ctrlKey))
        );
        
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
            } else if (!ModeContext.isEditing && hoveredDetails.noteId) {
                handleDeleteHoveredNote(event, hoveredDetails);
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
            } else if (!ModeContext.isEditing && hoveredDetails.noteId) {
                handleMoveHoveredNote(event, 'up', hoveredDetails);
            }
            break;
        case 'ArrowDown':
            if (event.metaKey || event.ctrlKey) {
                handleMoveNoteDownShortcut(event);
            } else if (!ModeContext.isEditing && hoveredDetails.noteId) {
                handleMoveHoveredNote(event, 'down', hoveredDetails);
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
        case ' ':
        case 'Space':
        case 'Spacebar':
            handleToggleCollapseShortcut(event);
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
        case 'p':
            if (event.metaKey || event.ctrlKey) {
                handlePasswordModalShortcut(event);
            }
            break;
        default:
            break;
                
    }
}

function getHoveredNoteDetails(event) {
    const safeEvent = event || {};

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

function handleMoveHoveredNote(event, direction, prefetchedDetails = null) {
    if (!event) {
        throw new Error('handleMoveHoveredNote called without an event object');
    }

    if (ModeContext.isEditing) {
        return;
    }

    const { noteId: hoveredNoteId } = prefetchedDetails ?? getHoveredNoteDetails(event);
    if (!hoveredNoteId) {
        Logger.logNoop('Move note shortcut ignored: no hovered note', {
            direction
        });
        return;
    }

    if (!ModeContext.isConnected) {
        Logger.logNoop('Move note shortcut ignored while disconnected from server', {
            direction,
            hoveredNoteId
        });
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    Logger.logDebug(
        direction === 'up' ? 'Move hovered note up shortcut triggered' : 'Move hovered note down shortcut triggered',
        {
            hoveredNoteId,
            currentNoteId: ModeContext.currentNoteId
        },
        Logger.LogCategory.EVENT
    );

    if (direction === 'up') {
        moveNoteUp(hoveredNoteId);
    } else {
        moveNoteDown(hoveredNoteId);
    }
}

function handleDeleteHoveredNote(event, prefetchedDetails = null) {
    if (!event) {
        throw new Error('handleDeleteHoveredNote called without an event object');
    }

    if (ModeContext.isEditing) {
        return;
    }

    const { noteId: hoveredNoteId } = prefetchedDetails ?? getHoveredNoteDetails(event);
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

    deleteNoteOutsideEdit(hoveredNoteId);
}

function handleToggleCollapseShortcut(event) {
    if (!event) {
        throw new Error('handleToggleCollapseShortcut called without an event object');
    }

    if (ModeContext.isEditing) {
        Logger.logNoop('Toggle collapse shortcut ignored while editing', {
            currentNoteId: ModeContext.currentNoteId
        });
        return;
    }

    let hoveredNoteId = ModeContext.hoveredNoteId;
    let hoveredElement = null;

    if (!hoveredNoteId) {
        const elementFromEvent = typeof event.target?.closest === 'function' ? event.target.closest('.note') : null;
        if (elementFromEvent && elementFromEvent.dataset.noteId) {
            hoveredElement = elementFromEvent;
            hoveredNoteId = elementFromEvent.dataset.noteId;
            if (ModeContext.hoveredNoteId !== hoveredNoteId) {
                ModeContext.setHoveredNoteId(hoveredNoteId);
            }
        }
    }

    if (!hoveredNoteId) {
        const hoveredCandidates = Array.from(document.querySelectorAll('.note:hover'));
        if (hoveredCandidates.length > 0) {
            const deepest = hoveredCandidates[hoveredCandidates.length - 1];
            if (deepest && deepest.dataset.noteId) {
                hoveredElement = deepest;
                hoveredNoteId = deepest.dataset.noteId;
                if (ModeContext.hoveredNoteId !== hoveredNoteId) {
                    ModeContext.setHoveredNoteId(hoveredNoteId);
                }
            }
        }
    }

    if (!hoveredNoteId) {
        Logger.logNoop('Toggle collapse shortcut ignored: no hovered note', {
            isEditing: ModeContext.isEditing
        });
        return;
    }

    if (!hoveredElement) {
        hoveredElement = document.querySelector(`[data-note-id="${hoveredNoteId}"]`);
    }

    const isCurrentlyCollapsed = hoveredElement?.dataset?.isCollapsed === 'true';
    const canCollapse = hoveredElement?.dataset?.canCollapse !== 'false';

    Logger.logDebug('Toggle collapse shortcut triggered', {
        hoveredNoteId,
        isCurrentlyCollapsed,
        canCollapse
    }, Logger.LogCategory.EVENT);

    event.preventDefault();
    event.stopPropagation();

    if (isCurrentlyCollapsed) {
        expandNote(hoveredNoteId);
    } else {
        if (!canCollapse) {
            Logger.logNoop('Toggle collapse shortcut ignored: note cannot collapse', {
                hoveredNoteId
            });
            return;
        }
        collapseNote(hoveredNoteId);
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

    if (ModeContext.isEditing) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    if (ModeContext.isSearching) {
        actionExitSearchMode();
    }

    createNote();
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
    
    try {
        // Set clipboard mode to note and call server
        if (ModeContext.clipboardMode !== 'note') {
            ModeContext.setClipboardMode('note');
        }
        
        // Copy to server clipboard
        await actionCopyNote();
        
        Logger.logDebug('Note copied to server clipboard', {
            noteId: ModeContext.currentNoteId
        }, Logger.LogCategory.EVENT);
        
        // Also copy HTML to system clipboard
        try {
            // Import the API module
            const { NotesAPI } = await import('../../api-client.js');
            
            // Get HTML export of the note
            const htmlResponse = await NotesAPI.exportNoteAsHtml(currentNoteId);
            
            if (htmlResponse && htmlResponse.html) {
                // Copy HTML to system clipboard
                if (navigator.clipboard && navigator.clipboard.write) {
                    // Modern clipboard API with HTML support
                    const htmlBlob = new Blob([htmlResponse.html], { type: 'text/html' });
                    const plainTextBlob = new Blob([htmlResponse.plain_text], { type: 'text/plain' });
                    
                    const clipboardItem = new ClipboardItem({
                        'text/html': htmlBlob,
                        'text/plain': plainTextBlob
                    });
                    
                    await navigator.clipboard.write([clipboardItem]);
                    Logger.logDebug('HTML copied to system clipboard using Clipboard API', {}, Logger.LogCategory.EVENT);
                } else if (navigator.clipboard && navigator.clipboard.writeText) {
                    // Fallback to plain text if HTML not supported
                    await navigator.clipboard.writeText(htmlResponse.plain_text);
                    Logger.logDebug('Plain text copied to system clipboard', {}, Logger.LogCategory.EVENT);
                } else {
                    // Legacy fallback using execCommand
                    const textarea = document.createElement('textarea');
                    textarea.value = htmlResponse.plain_text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    Logger.logDebug('Text copied to system clipboard using legacy method', {}, Logger.LogCategory.EVENT);
                }
            }
        } catch (htmlError) {
            Logger.logDebug('Error copying HTML to system clipboard', {
                error: htmlError.message
            }, Logger.LogCategory.EVENT);
            // Continue even if HTML copy fails - server clipboard still works
        }
    } catch (error) {
        Logger.logDebug('Error copying note', {
            error: error.message
        }, Logger.LogCategory.EVENT);
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
    actionPasteNoteSibling();
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
    actionPasteNoteChild();
}

function handlePasswordModalShortcut(event) {
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
        actionDeselectNote();
    }

    // Open the password modal
    const passwordModal = new PasswordModal();
    passwordModal.open();
}


function handlePasteEvent(event) {
    if (!event || !event.clipboardData) {
        Logger.logDebug('Paste event without clipboard data - allowing default behavior', {}, Logger.LogCategory.EVENT);
        return;
    }

    // Get HTML from clipboard if available
    const html = event.clipboardData.getData('text/html');
    
    Logger.logDebug('Paste event detected', {
        hasHtml: !!html,
        htmlLength: html ? html.length : 0,
        isEditing: ModeContext.isEditing
    }, Logger.LogCategory.EVENT);

    // Check if this is our note HTML (contains note-content class)
    if (html && html.includes('class="note-content"')) {
        Logger.logDebug('Detected note HTML in clipboard - using server clipboard', {}, Logger.LogCategory.EVENT);
        
        // This is our note HTML - prevent default and use server clipboard
        if (ModeContext.isEditing && ModeContext.currentNoteId) {
            event.preventDefault();
            
            // Determine if shift is held for child paste
            if (event.shiftKey) {
                actionPasteNoteChild();
            } else {
                actionPasteNoteSibling();
            }
        }
    } else {
        // External content - allow default paste behavior
        Logger.logDebug('External content detected - using browser default paste', {
            hasHtml: !!html
        }, Logger.LogCategory.EVENT);
        
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
    
    const tabs = ModeContext.tabs;
    const activeTabId = ModeContext.activeTabId;
    
    // Build the list of search contexts
    let contextsList = [];
    const sortedTabIds = Object.keys(tabs).map(id => parseInt(id)).sort((a, b) => a - b);
    for (let i = 0; i < sortedTabIds.length; i++) {
        const tabId = sortedTabIds[i].toString();
        const originalQuery = tabs[tabId].searchQuery || '';
        let displayQuery = originalQuery || '(empty)';
        
        // Truncate long search queries for display
        if (displayQuery.length > 12 && displayQuery !== '(empty)') {
            displayQuery = displayQuery.substring(0, 12) + '...';
        }
        
        const isActive = tabId === activeTabId;
        const isEmpty = !originalQuery || originalQuery.trim() === '';
        const activeStyle = isActive ? 'color: #90EE90;' : '';
        const hoverStyle = 'cursor: pointer; padding: 2px 0;';
        
        // Add red - button for active contexts (only if there are multiple tabs)
        const deleteButton = (isActive && sortedTabIds.length > 1) ? 
            ` <span style="color: #ff4444; cursor: pointer;" class="delete-context" data-actual-tab-id="${tabId}">-</span>` : '';
        
        contextsList.push(`<div style="${activeStyle}${hoverStyle}" data-tab-id="${tabId}" class="tab-context-item">${i}: ${displayQuery}${deleteButton}</div>`);
    }
    
    // Add the + item at the end
    contextsList.push(`<div style="cursor: pointer; padding: 2px 0; color: #ccc;" class="add-context-item">+</div>`);
    
    if (contextsList.length > 0) {
        searchContextsList.innerHTML = contextsList.join('');
        searchContextsList.style.display = 'block';
        
        // Add click handlers to each tab context item
        searchContextsList.querySelectorAll('.tab-context-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const tabId = e.target.getAttribute('data-tab-id');
                if (tabId && tabId !== ModeContext.activeTabId) {
                    // Switch to the tab directly
                    ModeContext.switchToTab(tabId);
                    
                    // Update search input field to match new tab's query
                    const searchInput = document.getElementById('search-input');
                    if (searchInput) {
                        searchInput.value = ModeContext.searchQuery;
                    }
                    
                    // Update the display and trigger refresh
                    updateSearchContextsList();
                    
                    // Trigger a refresh with the new tab's search query
                    import('../actions/ui-actions.js').then(async ({ actionRefreshAndMaybeSelect }) => {
                        try {
                            await actionRefreshAndMaybeSelect();
                        } catch (error) {
                            console.error('Failed to refresh after tab switch', error);
                        }
                    });
                }
            });
            
            // Add hover effect
            item.addEventListener('mouseenter', (e) => {
                if (e.target.getAttribute('data-tab-id') !== ModeContext.activeTabId) {
                    e.target.style.color = '#fff';
                }
            });
            
            item.addEventListener('mouseleave', (e) => {
                if (e.target.getAttribute('data-tab-id') !== ModeContext.activeTabId) {
                    e.target.style.color = '#ccc';
                }
            });
        });
        
        // Add click handler for the + item
        const addContextItem = searchContextsList.querySelector('.add-context-item');
        if (addContextItem) {
            addContextItem.addEventListener('click', () => {
                // Find the next available tab ID
                let nextTabId = 0;
                while (ModeContext.tabs[nextTabId.toString()]) {
                    nextTabId++;
                }
                
                // Get current search query to inherit
                const currentSearchQuery = ModeContext.searchQuery;
                
                // Switch to the new tab directly (this will create it automatically)
                ModeContext.switchToTab(nextTabId.toString());
                
                // Set the new tab's search query to inherit from current
                ModeContext.setSearchQuery(currentSearchQuery);
                
                // Update search input field to match new tab's query
                const searchInput = document.getElementById('search-input');
                if (searchInput) {
                    searchInput.value = ModeContext.searchQuery;
                }
                
                // Update the display and trigger refresh
                updateSearchContextsList();
                
                // Trigger a refresh with the new tab's search query
                import('../actions/ui-actions.js').then(async ({ actionRefreshAndMaybeSelect }) => {
                    try {
                        await actionRefreshAndMaybeSelect();
                    } catch (error) {
                        console.error('Failed to refresh after tab switch', error);
                    }
                });
            });
            
            // Add hover effect for + item
            addContextItem.addEventListener('mouseenter', (e) => {
                e.target.style.color = '#fff';
            });
            
            addContextItem.addEventListener('mouseleave', (e) => {
                e.target.style.color = '#ccc';
            });
        }
        
        // Add click handler for delete buttons
        searchContextsList.querySelectorAll('.delete-context').forEach(deleteBtn => {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent tab switching when clicking delete
                
                // Don't delete if there's only one tab left
                if (Object.keys(ModeContext.tabs).length <= 1) {
                    return;
                }
                
                // Clear localStorage completely first
                localStorage.removeItem('metalist_tab_state');
                
                // Get the current active tab ID to delete
                const deleteTabId = ModeContext.activeTabId;
                
                // Remove the active tab
                delete ModeContext.tabs[deleteTabId];
                
                // Get all remaining tabs and their data
                const remainingData = [];
                const sortedIds = Object.keys(ModeContext.tabs).map(id => parseInt(id)).sort((a, b) => a - b);
                for (const id of sortedIds) {
                    remainingData.push(ModeContext.tabs[id.toString()]);
                }
                
                // Clear tabs and rebuild with consecutive numbering
                ModeContext._tabs = {};
                for (let i = 0; i < remainingData.length; i++) {
                    ModeContext._tabs[i.toString()] = remainingData[i];
                }
                
                // Set active tab to 0 directly
                ModeContext._activeTabId = '0';
                
                // Update search query to match new tab 0 (this will trigger proper updates)
                ModeContext.setSearchQuery(ModeContext._tabs['0'].searchQuery || '');
                
                // Update search input field
                const searchInput = document.getElementById('search-input');
                if (searchInput) {
                    searchInput.value = ModeContext._searchQuery;
                }
                
                // Save the updated state to localStorage
                ModeContext._saveTabStateToStorage();
                
                // Refresh the display
                updateSearchContextsList();
                
                // Trigger a refresh to load the correct notes for the new active tab
                import('../actions/ui-actions.js').then(async ({ actionRefreshAndMaybeSelect }) => {
                    try {
                        await actionRefreshAndMaybeSelect();
                    } catch (error) {
                        console.error('Failed to refresh after tab deletion', error);
                    }
                });
            });
        });
        
    } else {
        searchContextsList.style.display = 'none';
    }
}
