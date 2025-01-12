import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';

/**
 * Editing State
 * 
 * Manages note editing functionality including:
 * - Setting up editable notes
 * - Cursor position management
 * - Content change tracking
 * - Auto-saving
 * 
 * State Data:
 * - currentNote: Currently edited note element
 * - lastSavedContent: Content at last save
 * - currentContent: Current note content
 * 
 * Transitions:
 * - Enter: Sets up note for editing, manages focus
 * - Exit: Saves changes, cleans up editable state
 * 
 * @example
 * // Enter editing state
 * await transition('editing', {
 *   nextNote: noteElement,
 *   cursorPosition: 'end'
 * });
 */

export const editingTransitions = {
    enter: async (data, prevState) => {
        const { nextNote, cursorPosition, activityMonitor } = data;
        
        // Clean up any existing editing state
        const allNotes = DOMUtils.getAllNotes();
        allNotes.forEach(note => DOMUtils.setNoteEditable(note, false));
        
        // Set up note for editing
        DOMUtils.setNoteEditable(nextNote, true);
        
        // Handle cursor position based on context
        if (cursorPosition === 'end') {
            DOMUtils.focusNote(nextNote);
        } else if (cursorPosition) {
            DOMUtils.setCursorPosition(nextNote, cursorPosition);
        }

        // Start activity monitoring
        activityMonitor?.startMonitoring();

        return {
            currentNote: nextNote,
            lastSavedContent: DOMUtils.getNoteContentText(nextNote),
            currentContent: DOMUtils.getNoteContentText(nextNote)
        };
    },

    exit: async (data, nextState) => {
        const { currentNote, lastSavedContent, activityMonitor } = data;
        
        // Stop activity monitoring
        activityMonitor?.stopMonitoring();
        
        // Save if content changed
        const currentContent = DOMUtils.getNoteContentText(currentNote);
        if (currentContent !== lastSavedContent) {
            console.log(' [EDITING EXIT] Saving content changes:', {
                noteId: DOMUtils.getNoteId(currentNote),
                lastSavedContent,
                currentContent
            });
            await NotesAPI.saveNote(
                DOMUtils.getNoteId(currentNote), 
                currentContent
            );
            console.log(' [EDITING EXIT] Content saved');
        }

        // Clean up all notes - remove editing class from everything
        const allNotes = DOMUtils.getAllNotes();
        allNotes.forEach(note => DOMUtils.setNoteEditable(note, false));

        // Clear selection
        if (window.getSelection) {
            window.getSelection().removeAllRanges();
        }

        return {};  // Clear temporary editing state
    },

    handleEvent: async (event, data) => {
        const { type } = event;
        
        if (type === 'KEY_DOWN') {
            const { key, metaKey, shiftKey, target } = event;

            if (key === 'Escape') {
                return { type: 'START_IDLE' };
            }

            if (key === 'Enter' && metaKey) {
                return {
                    type: 'CREATE_NOTE',
                    data: {
                        parentNote: DOMUtils.findNoteElement(target),
                        noteType: shiftKey ? 'child' : 'sibling'
                    }
                };
            }

            if (key.startsWith('Arrow') && metaKey) {
                return {
                    type: 'MOVE_NOTE',
                    data: {
                        direction: key.replace('Arrow', '').toLowerCase(),
                        noteElement: data.currentNote
                    }
                };
            }

            // Regular keys are handled by contenteditable and trigger NOTE_CONTENT_CHANGED
            return { type: 'NO_OP' };
        }

        if (type === 'INACTIVITY_TIMEOUT') {
            const { currentNote, lastSavedContent } = data;
            const currentContent = DOMUtils.getNoteContentText(currentNote);
            
            // Only save if content has changed
            if (currentContent !== lastSavedContent) {
                console.log('⏰ [EDITING] Auto-saving on inactivity:', {
                    noteId: DOMUtils.getNoteId(currentNote),
                    lastSavedContent,
                    currentContent
                });
                
                // Fire and forget save
                NotesAPI.updateNote(
                    DOMUtils.getNoteId(currentNote), 
                    currentContent
                );
                
                return {
                    type: 'NO_OP',
                    data: { lastSavedContent: currentContent }
                };
            }

            return { type: 'NO_OP' };
        }

        if (type === 'CLICKED_OUTSIDE_NOTE') {
            return { type: 'START_IDLE' };
        }
        
        if (type === 'NOTE_CONTENT_CHANGED') {
            const { content } = event;
            return { currentContent: content };
        }

        if (type === 'SWITCH_NOTE') {
            const { nextNote, cursorPosition } = event.data;
            return {
                type: 'START_EDITING',
                data: {
                    nextNote,
                    cursorPosition
                }
            };
        }

        if (type === 'CREATE_NOTE') {
            const { parentNote, noteType } = event.data;
            const noteId = parentNote?.getAttribute('data-id');
            
            if (!noteId) {
                throw new Error('No note ID found');
            }

            let result;
            if (noteType === 'child') {
                result = await NotesAPI.createChild(noteId);
            } else {
                result = await NotesAPI.createSibling(noteId);
            }
            
            if (!result) {
                throw new Error('Failed to create note');
            }

            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    nextNote: newNote,
                    cursorPosition: 'end'
                }
            };
        }

        if (type === 'COMMAND_ENTER_PRESSED') {
            const { note } = event.data;
            const noteId = note?.getAttribute('data-id');
            if (!noteId) {
                throw new Error('No note ID found');
            }

            const result = await NotesAPI.createSibling(noteId);
            if (!result) {
                throw new Error('Failed to create note');
            }

            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    nextNote: newNote,
                    cursorPosition: 'end'
                }
            };
        }

        if (type === 'SHIFT_COMMAND_ENTER_PRESSED') {
            const { note } = event.data;
            const noteId = note?.getAttribute('data-id');
            if (!noteId) {
                throw new Error('No note ID found');
            }

            const result = await NotesAPI.createChild(noteId);
            if (!result) {
                throw new Error('Failed to create note');
            }

            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (!newNote) {
                throw new Error('Created note not found in DOM');
            }

            return {
                type: 'START_EDITING',
                data: {
                    nextNote: newNote,
                    cursorPosition: 'end'
                }
            };
        }

        if (type === 'FRAGMENT_LOADED') {
            return { type: 'NO_OP' };
        }

        if (type === 'NO_OP') {
            return { type: 'NO_OP' };
        }

        throw new Error(`Unhandled event type: ${type}`);
    }
}; 