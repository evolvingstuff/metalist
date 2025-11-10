import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote } from '../actions/note-actions.js';
import { actionSelectNote, actionDeselectNote, actionSwitchNotes } from '../actions/selection-actions.js';
import { actionEnterSearchMode, actionExitSearchMode } from '../actions/search-actions.js';
import { DOMUtils } from '../../dom-utils.js'; 

export function initMouseEvents() {
        
    document.addEventListener('click', handleClick, { capture: true });
    document.addEventListener('mouseover', handleMouseOver, { capture: true });
    document.addEventListener('mouseout', handleMouseOut, { capture: true });

    Logger.logInit('Mouse events handler');
}

function handleClick(event) {
    if (!event) {
        throw new Error('handleClick called without an event object');
    }
        
    if (event.clientX === undefined || event.clientY === undefined) {
        throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
    }
        
    if (!event.target) {
        throw new Error('Click event missing target element');
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Click event ignored while system is loading', {
            eventType: event.type,
            targetElement: event.target.tagName,
            isLoading: true
        });
        return; 
    }

    const toolbarElement = event.target.closest('#rich-text-toolbar');
    if (toolbarElement) {
        Logger.logDebug('Click inside rich text toolbar', {
            eventType: event.type
        }, Logger.LogCategory.EVENT);
        return;
    }
    
    // Check if we're disconnected from server
    if (!ModeContext.isConnected) {
        const noteContent = event.target.closest('.note-content');
        const searchField = event.target.closest('#search-input');
        const createButton = event.target.closest('.add-note');
        
        // Only allow certain actions when disconnected
        if (noteContent || createButton) {
            Logger.logNoop('Click event ignored while disconnected from server', {
                eventType: event.type,
                targetElement: event.target.tagName,
                isConnected: false
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        // Allow clicking on search field even when disconnected
    }

    const coordinates = {
        x: event.clientX,
        y: event.clientY
    };

    const noteContent = event.target.closest('.note-content');
    const searchField = event.target.closest('#search-input');
    const createButton = event.target.closest('.add-note');
    const deleteButton = event.target.closest('#trash-can');

    if (deleteButton) {
                
        if (ModeContext.isSearching) {
            actionExitSearchMode();
        }

        const noteId = ModeContext.currentNoteId;
                
        if (noteId) {
            Logger.logDebug('Delete button clicked for current note', { 
                noteId,
                coordinates 
            }, Logger.LogCategory.EVENT);

            deleteNote(noteId);
        } else {
                        
            Logger.logNoop('Delete button clicked but no note is selected', { 
                coordinates 
            });
        }
    } else if (noteContent) {
        const noteElement = noteContent.closest('.note');
        if (!noteElement) {
            throw new Error('Found .note-content without parent .note element');
        }
        
        // Check if note is locked - don't allow interaction
        if (noteElement.classList.contains('locked')) {
            Logger.logNoop('Click on locked note ignored', {
                noteId: noteElement.dataset.noteId,
                reason: 'note_locked'
            });
            event.preventDefault();
            event.stopPropagation();
            return;
        }
                
        const noteId = noteElement.dataset.noteId;
        if (!noteId) {
            throw new Error('Note element missing data-note-id attribute');
        }

        const rect = noteContent.getBoundingClientRect();
        if (!rect || typeof rect.left !== 'number' || typeof rect.right !== 'number' || 
                typeof rect.top !== 'number' || typeof rect.bottom !== 'number') {
            throw new Error(`Invalid bounding rect for note content: ${JSON.stringify(rect)}`);
        }
                
        const isWithinBounds = (
            coordinates.x >= rect.left &&
            coordinates.x <= rect.right &&
            coordinates.y >= rect.top &&
            coordinates.y <= rect.bottom
        );
                
        if (isWithinBounds) {
                        
            if (ModeContext.isSearching) {
                console.log('DEBUG: About to call exitSearchMode', { 
                    isSearching: ModeContext.isSearching, 
                    where: 'click in note' 
                });
                actionExitSearchMode();
            } else {
                console.log('DEBUG: Search mode already inactive', { 
                    isSearching: ModeContext.isSearching, 
                    where: 'click in note' 
                });
            }

            if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
                // Don't calculate or save cursor position when entering edit mode
                // The click position on rendered content (e.g., LaTeX) doesn't map meaningfully 
                // to cursor position in source text

                if (ModeContext.currentNoteId) {
                    actionSwitchNotes(noteId);
                } else {
                    actionSelectNote(noteId);
                }
                                
                Logger.logDebug('Click in note content - selecting note', { 
                    noteId,
                    coordinates,
                    isEditing: true
                }, Logger.LogCategory.EVENT);
            } else {
                if (ModeContext.isCaretHidden && ModeContext.currentNoteId === noteId) {
                    DOMUtils.revealCaret(noteElement);
                    ModeContext.markCaretVisible();
                }

                Logger.logNoop('Click in already selected note - no action needed', { 
                    noteId,
                    coordinates,
                    isEditing: true
                });
            }
        } else {
                        
            if (ModeContext.isEditing) {
                actionDeselectNote();
            }
                        
            Logger.logDebug('Click near note but outside content bounds', {
                noteId,
                coordinates,
                elementBounds: {
                    left: rect.left,
                    right: rect.right,
                    top: rect.top,
                    bottom: rect.bottom
                },
                isEditing: false
            }, Logger.LogCategory.EVENT);
        }
    } else if (searchField) {

        actionEnterSearchMode();
                
        Logger.logDebug('Click in search field', { coordinates }, Logger.LogCategory.EVENT);
    } else if (createButton) {
        
        if (ModeContext.isLoading) {
            Logger.logNoop('Create button clicked while system is loading - ignoring', {
                coordinates,
                isLoading: true
            });
            return; 
        }
                
        if (ModeContext.isSearching) {
            console.log('DEBUG: About to call exitSearchMode', { 
                isSearching: ModeContext.isSearching, 
                where: 'create note button' 
            });
            actionExitSearchMode();
        } else {
            console.log('DEBUG: Search mode already inactive', { 
                isSearching: ModeContext.isSearching, 
                where: 'create note button' 
            });
        }
                
        Logger.logDebug('Create note button clicked', { coordinates }, Logger.LogCategory.EVENT);
        createNote();
    } else {

        if (ModeContext.isEditing) {
            actionDeselectNote();
                        
            Logger.logDebug('Click outside any note - exiting edit mode', {
                coordinates,
                isEditing: false,
                currentNoteId: null
            }, Logger.LogCategory.EVENT);
        }

        if (ModeContext.isSearching) {
            console.log('DEBUG: About to call exitSearchMode', { 
                isSearching: ModeContext.isSearching, 
                where: 'click outside handler' 
            });
            actionExitSearchMode();
        } else {
            console.log('DEBUG: Search mode already inactive', { 
                isSearching: ModeContext.isSearching, 
                where: 'click outside handler' 
            });
        }
    }
}

function handleMouseOver(event) {
    if (!event) {
        throw new Error('handleMouseOver called without an event object');
    }

    const target = event.target;
    if (!target) {
        throw new Error('Mouseover event missing target element');
    }

    const noteElement = target.closest('.note');
    if (!noteElement) {
        return;
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Note element missing data-note-id attribute in handleMouseOver');
    }

    if (ModeContext.hoveredNoteId === noteId) {
        return;
    }

    ModeContext.setHoveredNoteId(noteId);

    Logger.logDebug('Pointer entered note', {
        noteId,
        isEditing: ModeContext.isEditing
    }, Logger.LogCategory.EVENT);
}

function handleMouseOut(event) {
    if (!event) {
        throw new Error('handleMouseOut called without an event object');
    }

    const target = event.target;
    if (!target) {
        throw new Error('Mouseout event missing target element');
    }

    const noteElement = target.closest('.note');
    if (!noteElement) {
        return;
    }

    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
        throw new Error('Note element missing data-note-id attribute in handleMouseOut');
    }

    const relatedTarget = event.relatedTarget;
    if (relatedTarget && noteElement.contains(relatedTarget)) {
        return;
    }

    if (ModeContext.hoveredNoteId !== noteId) {
        return;
    }

    ModeContext.setHoveredNoteId(null);

    Logger.logDebug('Pointer left note', {
        noteId
    }, Logger.LogCategory.EVENT);
}
