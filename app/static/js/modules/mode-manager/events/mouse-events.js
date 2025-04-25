import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { createNote, deleteNote } from '../actions/note-actions.js';
import { selectNote, deselectNote, switchNotes } from '../actions/selection-actions.js';
import { enterSearchMode, exitSearchMode } from '../actions/search-actions.js';
import { DOMUtils } from '../../dom-utils.js'; 

export function initMouseEvents() {
        
    document.addEventListener('click', handleClick, { capture: true });

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
            exitSearchMode();
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
                exitSearchMode();
            } else {
                console.log('DEBUG: Search mode already inactive', { 
                    isSearching: ModeContext.isSearching, 
                    where: 'click in note' 
                });
            }

            if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {

                const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, coordinates);

                const content = DOMUtils.getNoteContent(noteElement);
                Logger.logDebug('Note content structure:', { 
                    html: content.innerHTML,
                    text: content.textContent,
                    cursorOffset,
                    coordinates,
                    childNodes: Array.from(content.childNodes).map(node => ({
                        type: node.nodeType,
                        name: node.nodeName,
                        text: node.textContent?.substring(0, 20)
                    }))
                }, Logger.LogCategory.DEBUG);

                ModeContext._savedCursorOffset = { 
                    offset: cursorOffset,
                    noteId 
                };
                                
                Logger.logDebug('Stored cursor offset before fragment load', { 
                    cursorOffset, 
                    noteId 
                }, Logger.LogCategory.EVENT);

                if (ModeContext.currentNoteId) {
                    switchNotes(noteId);
                } else {
                    selectNote(noteId);
                }
                                
                Logger.logDebug('Click in note content - selecting note', { 
                    noteId,
                    coordinates,
                    isEditing: true
                }, Logger.LogCategory.EVENT);
            } else {
                                
                Logger.logNoop('Click in already selected note - no action needed', { 
                    noteId,
                    coordinates,
                    isEditing: true
                });
            }
        } else {
                        
            if (ModeContext.isEditing) {
                deselectNote();
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

        enterSearchMode();
                
        Logger.logDebug('Click in search field', { coordinates }, Logger.LogCategory.EVENT);
    } else if (createButton) {
                
        if (ModeContext.isSearching) {
            console.log('DEBUG: About to call exitSearchMode', { 
                isSearching: ModeContext.isSearching, 
                where: 'create note button' 
            });
            exitSearchMode();
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
            deselectNote();
                        
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
            exitSearchMode();
        } else {
            console.log('DEBUG: Search mode already inactive', { 
                isSearching: ModeContext.isSearching, 
                where: 'click outside handler' 
            });
        }
    }
}