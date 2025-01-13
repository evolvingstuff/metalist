import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';

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
 * - noteId: ID of currently edited note
 * - lastSavedContent: Content at last save
 * 
 * Transitions:
 * - Enter: Sets up note for editing, manages focus
 * - Exit: Saves changes, cleans up editable state
 * 
 * @example
 * // Enter editing state
 * await transition('editing', {
 *   noteId: 'note-123',
 *   cursorOffset: 10
 * });
 */

// State data
let currentNoteId = null;

export const editingTransitions = {
    enter: async (context, prevState) => {
        // Context is already validated by EditingContext class
        if (!context) {
            throw new Error('Editing enter transition missing context');
        }

        console.log(' Starting with context:', context);
        
        // Store current note ID
        currentNoteId = context.noteId;

        // Start activity monitoring
        context.activityMonitor?.startMonitoring();

        // Set up note for editing
        const noteElement = DOMUtils.getNoteById(context.noteId);
        if (!noteElement) {
            throw new Error(`Could not find note element with ID: ${context.noteId}`);
        }

        // Get initial content for change detection
        context.setLastSavedContent(DOMUtils.getNoteContentHTMLById(context.noteId));

        // Set cursor position if we have coordinates
        if (context.coordinates) {
            const offset = DOMUtils.getCursorOffsetFromClick(noteElement, context.coordinates);
            context.setCursorOffset(offset);
            DOMUtils.setCursorOffset(noteElement, offset);
        } else if (context.cursorOffset !== null) {
            // Use existing cursor offset
            DOMUtils.setCursorOffset(noteElement, context.cursorOffset);
        } else {
            // Default to focusing at end
            DOMUtils.focusNote(noteElement);
        }

        return context;
    },

    exit: async (context, nextState) => {
        const { noteId, lastSavedContent, activityMonitor } = context;
        
        // Stop activity monitoring
        activityMonitor?.stopMonitoring();

        if (!noteId) {
            console.log('[EDITING EXIT] No note to save');
            return {};
        }
        
        // Save if content changed
        const currentContent = DOMUtils.getNoteContentHTMLById(noteId);
        if (currentContent !== lastSavedContent) {
            console.log('[EDITING EXIT] Saving content changes:', {
                noteId,
                lastSavedContent,
                currentContent
            });
            await NotesAPI.saveNote(noteId, currentContent);
            console.log('[EDITING EXIT] Content saved');
        }

        // Let view layer handle DOM cleanup
        return {};
    },

    handleEvent: async ({ type, context }) => {
        // NO MERCY - validate event and context
        if (!type) {
            throw new Error('Event missing type');
        }
        if (!(context instanceof StateContext)) {
            throw new Error('Invalid context: must be StateContext instance');
        }

        if (type === 'KEY_DOWN') {
            const { key, metaKey, shiftKey } = context;
            if (!key) {
                throw new Error('KEY_DOWN missing key');
            }

            // Escape to exit editing
            if (key === 'Escape') {
                return { type: 'START_IDLE' };
            }

            // Meta+Enter to create note
            if (key === 'Enter' && metaKey) {
                if (!context.noteId) {
                    throw new Error('Create note missing parent ID');
                }

                return {
                    type: 'CREATE_NOTE',
                    context: StateContext.fromStateData({
                        noteId: context.noteId,
                        cursorOffset: 0  // Start at beginning of new note
                    }),
                    data: {  // Additional data for API
                        parentId: context.noteId,
                        noteType: shiftKey ? 'child' : 'sibling'
                    }
                };
            }

            // Meta+Arrow to move note
            if (key.startsWith('Arrow') && metaKey) {
                return {
                    type: 'MOVE_NOTE',
                    context: StateContext.fromStateData({
                        noteId: context.noteId,
                        cursorOffset: 0  // Start at beginning of moved note
                    }),
                    data: {  // Additional data for API
                        direction: key.replace('Arrow', '').toLowerCase(),
                        noteId: context.noteId
                    }
                };
            }

            // Regular keys handled by contenteditable
            return context;
        }

        if (type === 'INACTIVITY_TIMEOUT') {
            const { noteId, lastSavedContent } = context;
            const currentContent = DOMUtils.getNoteContentHTMLById(noteId);
            
            // Only save if content has changed
            if (currentContent !== lastSavedContent) {
                console.log(' [EDITING] Auto-saving note:', {
                    noteId,
                    content: currentContent
                });

                try {
                    await NotesAPI.updateNote(noteId, {
                        content: currentContent
                    });

                    // Update last saved content
                    context.setLastSavedContent(currentContent);
                    return context;
                } catch (error) {
                    console.error(' [EDITING] Failed to save note:', error);
                    throw new Error(`Failed to save note: ${error.message}`);
                }
            }

            return context;
        }

        // Click outside note -> exit editing
        if (type === 'CLICKED_OUTSIDE_NOTE') {
            return { type: 'START_IDLE' };
        }

        // Content changes handled by auto-save
        if (type === 'NOTE_CONTENT_CHANGED') {
            return context;
        }

        if (type === 'NOTE_CONTENT_CLICKED') {
            // Validate event context
            if (!context.noteId) {
                throw new Error('Event context missing noteId');
            }

            // If clicking same note, just update cursor
            if (context.noteId === currentNoteId) {
                const coordinates = context.coordinates;
                if (!coordinates) {
                    throw new Error('Event context missing coordinates');
                }

                try {
                    const offset = DOMUtils.getCursorOffsetFromClick(DOMUtils.getActiveNoteElement(), coordinates);
                    context.setCursorOffset(offset);
                    DOMUtils.setCursorOffset(DOMUtils.getActiveNoteElement(), offset);
                    return context;
                } catch (error) {
                    console.error(' [EDITING] Failed to set cursor from click:', error);
                    return context;  // Keep editing even if cursor update fails
                }
            }

            // Different note - start editing that one
            return {
                type: 'START_EDITING',
                context: context
            };
        }

        if (type === 'SWITCH_NOTE') {
            const { noteId, cursorOffset } = context;
            return {
                type: 'STOP_EDITING'
            };
        }

        if (type === 'CREATE_NOTE') {
            const { parentId, noteType } = context;
            return {
                type: 'STOP_EDITING'
            };
        }

        if (type === 'DELETE_NOTE') {
            return {
                type: 'STOP_EDITING'
            };
        }

        // Unknown event
        throw new Error(`Unknown event type: ${type}`);
    }
};
