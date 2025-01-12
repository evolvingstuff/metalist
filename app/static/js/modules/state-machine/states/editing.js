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
        if (!data) {
            throw new Error('Editing enter transition missing data');
        }

        const { noteId, cursorPosition, clickInfo, activityMonitor } = data;
        
        if (!noteId) {
            throw new Error('Editing enter transition missing noteId');
        }

        console.log('📝 [EDITING ENTER] Looking for note:', noteId);
        
        // Try both ID formats for debugging
        const nextNote = document.querySelector(`[data-note-id="${noteId}"], [data-id="${noteId}"]`);
        if (!nextNote) {
            console.error('📝 [EDITING ENTER] Could not find note:', {
                noteId,
                existingIds: Array.from(document.querySelectorAll('[data-note-id], [data-id]')).map(el => ({
                    noteId: el.dataset.noteId,
                    id: el.dataset.id
                }))
            });
            throw new Error(`Could not find note with ID: ${noteId}`);
        }
        
        console.log('📝 [EDITING ENTER] Starting with data:', {
            noteId,
            nextNote,
            nextNoteDataset: nextNote.dataset,
            cursorPosition,
            clickInfo,
            hasActivityMonitor: !!activityMonitor
        });
        
        // Clean up any existing editing state
        const allNotes = DOMUtils.getAllNotes();
        allNotes.forEach(note => DOMUtils.setNoteEditable(note, false));
        
        // Set up note for editing
        DOMUtils.setNoteEditable(nextNote, true);
        
        // Handle cursor position based on context
        if (clickInfo) {
            console.log('📝 [EDITING ENTER] Using stored click info:', clickInfo);
            
            // Validate clickInfo structure
            if (typeof clickInfo.isDiv !== 'boolean') {
                throw new Error('Click info missing isDiv flag');
            }
            if (!clickInfo.noteId) {
                throw new Error('Click info missing noteId');
            }
            if (clickInfo.noteId !== noteId) {
                throw new Error('Click info noteId does not match target note');
            }

            // Use stored click info after DOM refresh
            if (clickInfo.isDiv) {
                console.log('📝 [EDITING ENTER] Focusing div');
                DOMUtils.focusNote(nextNote);
            } else {
                // Find matching text node in refreshed DOM
                const content = DOMUtils.getNoteContent(nextNote);
                if (!content) {
                    throw new Error('Could not find note content element');
                }

                const nodes = Array.from(content.childNodes);
                console.log('📝 [EDITING ENTER] Looking for text node:', {
                    targetText: clickInfo.textContent,
                    foundNodes: nodes.map(n => n.textContent)
                });
                
                const index = nodes.findIndex(n => n.textContent === clickInfo.textContent);
                if (index !== -1) {
                    console.log('📝 [EDITING ENTER] Found matching node at index:', index);
                    try {
                        DOMUtils.setCursorPosition(nextNote, {
                            offset: clickInfo.offset,
                            path: [index]
                        });
                    } catch (e) {
                        console.error('📝 [EDITING ENTER] Failed to set cursor:', e);
                        // Fallback to focusing note
                        DOMUtils.focusNote(nextNote);
                    }
                } else {
                    console.log('📝 [EDITING ENTER] No matching node found, focusing at end');
                    DOMUtils.focusNote(nextNote);
                }
            }
        } else if (cursorPosition === 'end') {
            console.log('📝 [EDITING ENTER] Focusing at end');
            DOMUtils.focusNote(nextNote);
        } else if (cursorPosition) {
            console.log('📝 [EDITING ENTER] Setting cursor position:', cursorPosition);
            try {
                DOMUtils.setCursorPosition(nextNote, cursorPosition);
            } catch (e) {
                console.error('📝 [EDITING ENTER] Failed to set cursor:', e);
                // Fallback to focusing note
                DOMUtils.focusNote(nextNote);
            }
        }

        // Start activity monitoring
        activityMonitor?.startMonitoring();

        return {
            currentNote: nextNote,
            lastSavedContent: DOMUtils.getNoteContentText(nextNote),
            activityMonitor
        };
    },

    exit: async (data, nextState) => {
        const { currentNote, lastSavedContent, activityMonitor } = data;
        
        // Stop activity monitoring
        activityMonitor?.stopMonitoring();

        if (!currentNote) {
            console.log('[EDITING EXIT] No current note to save');
            return {};
        }

        const noteId = DOMUtils.getNoteId(currentNote);
        if (!noteId) {
            throw new Error('Current note missing ID');
        }
        
        // Save if content changed
        const currentContent = DOMUtils.getNoteContentText(currentNote);
        if (currentContent !== lastSavedContent) {
            console.log('[EDITING EXIT] Saving content changes:', {
                noteId,
                lastSavedContent,
                currentContent
            });
            await NotesAPI.saveNote(noteId, currentContent);
            console.log('[EDITING EXIT] Content saved');
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
        if (!event) {
            throw new Error('Editing state received null/undefined event');
        }

        const { type } = event;
        
        if (type === 'KEY_DOWN') {
            const { key, metaKey, shiftKey, target } = event;

            if (key === 'Escape') {
                return { type: 'START_IDLE' };
            }

            if (key === 'Enter' && metaKey) {
                const parentNote = DOMUtils.findNoteElement(target);
                const parentId = DOMUtils.getNoteId(parentNote);
                if (!parentId) {
                    throw new Error('Create note missing parent ID');
                }

                return {
                    type: 'CREATE_NOTE',
                    data: {
                        parentId,  // Use ID instead of DOM node
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
            return { type: 'NO_OP' };  // Content changes handled by auto-save
        }

        if (type === 'NOTE_CONTENT_CLICKED') {
            const noteId = DOMUtils.getNoteId(event.noteElement);
            const { target } = event;
            
            console.log(' [EDITING] Got click on note:', {
                noteElement: event.noteElement,
                noteId,
                dataset: event.noteElement?.dataset,
                target,
                targetDataset: target?.dataset,
                currentNote: data.currentNote
            });
            
            if (!noteId) {
                console.error(' [EDITING] No note ID found:', event.noteElement);
                throw new Error('Could not find note ID on clicked element');
            }

            // If clicking same note, no-op
            if (noteId === DOMUtils.getNoteId(data.currentNote)) {
                return { type: 'NO_OP' };
            }

            // Don't store DOM node references, just the data we need
            const isDiv = target.tagName === 'DIV';
            
            // DIVs might not have direct text content, but spans should
            if (!isDiv && !target.textContent) {
                console.error('📝 [EDITING] Non-div target missing textContent:', target);
                throw new Error('Non-div target missing textContent');
            }

            const clickInfo = {
                isDiv,
                offset: isDiv ? 0 : target.textContent.length,
                textContent: isDiv ? '' : target.textContent,  // Empty for divs, actual content for spans
                noteId
            };

            console.log('📝 [EDITING] Note content clicked:', {
                tagName: target.tagName,
                textContent: target.textContent,
                noteId,
                clickInfo
            });

            return {
                type: 'START_EDITING',
                data: {
                    noteId,
                    clickInfo
                }
            };
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
            const { parentId, noteType } = event.data;
            
            if (!parentId) {
                throw new Error('No note ID found');
            }

            let result;
            if (noteType === 'child') {
                result = await NotesAPI.createChild(parentId);
            } else {
                result = await NotesAPI.createSibling(parentId);
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