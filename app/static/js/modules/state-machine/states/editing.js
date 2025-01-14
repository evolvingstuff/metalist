import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { StateMachine } from '../state-machine-controller.js';
import { CONFIG } from '../../config.js';

/**
 * Editing State
 * 
 * Manages note editing functionality including:
 * - Setting up editable notes
 * - Cursor position management
 * - Auto-saving
 * 
 * State Context:
 * - noteId: ID of currently edited note
 * - lastSavedContent: Content at last save
 * - cursorOffset: Cursor position in note
 * - activityMonitor: For tracking edit activity
 * 
 * Transitions:
 * - Enter: Sets up note for editing, manages focus
 * - Exit: Saves changes, cleans up editable state
 * 
 * @example
 * // Enter editing state
 * stateContext
 *   .setType('START_EDITING')
 *   .setNoteId('note-123')
 *   .setCursorOffset(10);
 */

export const editingTransitions = {
    enter: async () => {
        // Validate context
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const noteId = StateMachine.currentStateContext.getNoteId();
        if (!noteId) {
            throw new Error('Note ID not set');
        }

        // Make note editable
        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

        // Set initial content for comparison on exit
        const content = DOMUtils.getNoteContentHTML(noteElement);
        StateMachine.currentStateContext.setLastSavedContent(content);

        DOMUtils.setNoteEditable(noteElement, true);
        DOMUtils.focusNote(noteElement, StateMachine.currentStateContext.getCursorOffset());

        // Start tracking activity
        StateMachine.startActivityMonitor();
    },

    exit: async () => {
        // Stop tracking activity
        StateMachine.stopActivityMonitor();

        // Save note content if changed
        const noteId = StateMachine.currentStateContext.getNoteId();
        if (!noteId) {
            throw new Error('No note ID in editing state context');
        }

        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

        // Compare current content with last saved
        const currentContent = DOMUtils.getNoteContentHTML(noteElement);
        const lastSavedContent = StateMachine.currentStateContext.getLastSavedContent();
        if (currentContent !== lastSavedContent) {
            await NotesAPI.updateNote(noteId, currentContent);
            StateMachine.currentStateContext.setLastSavedContent(currentContent);
        }

        // Make current note non-editable
        DOMUtils.setNoteEditable(noteElement, false);
    },

    handleEvent: async () => {
        // Validate context
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const eventType = StateMachine.currentStateContext.getType();
        if (!eventType) {
            throw new Error('State context missing event type');
        }

        console.log('Handling event in editing:', {
            type: eventType,
            context: StateMachine.currentStateContext
        });

        switch (eventType) {
            case 'CLICKED_OUTSIDE_NOTE': {
                StateMachine.currentStateContext.setTargetState('idle');
                break;
            }

            case 'NOTE_CONTENT_CLICKED': {
                const currentNoteId = StateMachine.currentStateContext.getNoteId();
                const clickedNoteId = StateMachine.currentStateContext.getClickedNoteId();

                // If clicking different note, switch to it
                if (currentNoteId !== clickedNoteId) {
                    const noteElement = DOMUtils.getNoteById(clickedNoteId);
                    if (!noteElement) {
                        throw new Error('Note element not found');
                    }

                    const content = DOMUtils.getNoteContentHTML(noteElement);
                    StateMachine.currentStateContext
                        .setNoteId(clickedNoteId)
                        .setLastSavedContent(content)
                        .setTargetState('editing');  
                }
                break;
            }

            case 'SEARCH_FOCUSED': {
                // Return to idle if inactive
                if (StateMachine.currentStateContext.isInactive()) {
                    StateMachine.currentStateContext.setType('SEARCH_FOCUSED');
                }
                break;
            }

            case 'KEY_DOWN': {
                const key = StateMachine.currentStateContext.getKey();
                const metaKey = StateMachine.currentStateContext.getMetaKey();
                const shiftKey = StateMachine.currentStateContext.getShiftKey();
                
                // Handle keyboard shortcuts
                if (key === 'Escape') {
                    // Escape: Return to idle
                    StateMachine.currentStateContext
                        .setType('CLICKED_OUTSIDE_NOTE')
                        .setTargetState('idle');
                    break;
                }

                if (metaKey && key === 'Enter') {
                    // Get current note ID for positioning
                    const currentNoteId = StateMachine.currentStateContext.getNoteId();
                    if (!currentNoteId) {
                        throw new Error('Current note ID not set');
                    }

                    if (shiftKey) {
                        // Shift+Cmd+Enter: Create child note
                        const noteId = await NotesAPI.createChildNote(currentNoteId);
                        // Switch to new note
                        StateMachine.currentStateContext
                            .setType('NOTE_CONTENT_CLICKED')
                            .setNoteId(noteId)
                            .setLastSavedContent('');
                    } else {
                        // Cmd+Enter: Create sibling note below
                        const noteId = await NotesAPI.createSiblingNote(currentNoteId);
                        // Switch to new note
                        StateMachine.currentStateContext
                            .setType('NOTE_CONTENT_CLICKED')
                            .setNoteId(noteId)
                            .setLastSavedContent('');
                    }
                }
                break;
            }

            case 'NOTE_CONTENT_CHANGED': {
                // Reset inactivity timer
                StateMachine.startActivityMonitor();
                break;
            }

            default:
                throw new Error(`Unhandled event in editing state: ${eventType}`);
        }
    }
};
