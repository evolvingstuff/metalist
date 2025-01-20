import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { StateMachine } from '../state-machine-controller.js';
import { CONFIG } from '../../config.js';
import { CreateChildEffect, CreateSiblingEffect, UpdateNoteEffect, SaveNoteEffect, DeleteNoteEffect, MoveNoteEffect } from '../effects.js';

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

        // Get current note ID - should be set by transition()
        const noteId = StateMachine.currentStateContext.getNoteId();
        if (!noteId) {
            throw new Error('Note ID not set');
        }

        // Get note element
        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

        // Set up cursor position if we have coordinates
        const coordinates = StateMachine.currentStateContext.getCoordinates();
        if (coordinates) {
            const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, coordinates);
            StateMachine.currentStateContext.setCursorOffset(cursorOffset);
            StateMachine.currentStateContext.resetCoordinates();
        }

        // Log the note content
        const contentElement = DOMUtils.getNoteContent(noteElement);
        console.log('Entering edit mode for note:', {
            noteId,
            innerHTML: contentElement.innerHTML
        });

        // Set initial content for comparison on exit
        const content = DOMUtils.getNoteContentHTML(noteElement);
        StateMachine.currentStateContext.setLastSavedContent(content || '');

        // Make note editable and focus
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
        console.log(' Exit content comparison:', {
            noteId,
            currentLength: currentContent.length,
            lastSavedLength: lastSavedContent.length,
            current: currentContent.slice(0, 50) + '...',
            lastSaved: lastSavedContent.slice(0, 50) + '...',
            equal: currentContent === lastSavedContent
        });

        if (currentContent !== lastSavedContent) {
            // Use SaveNoteEffect to ensure save completes before transition
            StateMachine.currentStateContext.addEffect(new SaveNoteEffect(noteId, currentContent));
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
                // Just set target state - no need for type during transition
                StateMachine.currentStateContext
                    .setTargetState('idle');
                break;
            }

            case 'NOTE_CONTENT_CLICKED': {
                const noteElement = DOMUtils.getNoteById(StateMachine.currentStateContext.getNoteId());
                const contentElement = DOMUtils.getNoteContent(noteElement);
                const currentContent = DOMUtils.getNoteContentHTML(noteElement);
                console.log('Current note state:', {
                    noteId: StateMachine.currentStateContext.getNoteId(),
                    contentLength: currentContent.length,
                    cursorOffset: StateMachine.currentStateContext.getCursorOffset()
                });

                const currentNoteId = StateMachine.currentStateContext.getNoteId();
                const targetNoteId = StateMachine.currentStateContext.getTargetNoteId();

                // If clicking different note, switch to it
                if (currentNoteId !== targetNoteId) {
                    const noteElement = DOMUtils.getNoteById(targetNoteId);
                    if (!noteElement) {
                        throw new Error('Note element not found');
                    }

                    const content = DOMUtils.getNoteContentHTML(noteElement);
                    console.log('Switching to note:', {
                        noteId: targetNoteId,
                        contentLength: content.length,
                        cursorOffset: StateMachine.currentStateContext.getCursorOffset()
                    });

                    // Get cursor offset from click coordinates
                    const clickCoordinates = StateMachine.currentStateContext.getCoordinates();
                    const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, clickCoordinates);

                    // Transition to editing state (triggers exit handler)
                    StateMachine.currentStateContext
                        .setTargetNoteId(targetNoteId)
                        .setCursorOffset(cursorOffset)
                        .setTargetState('editing');
                }
                break;
            }

            case 'ADD_BUTTON_CLICKED': {
                // Get current note ID for positioning
                const currentNoteId = StateMachine.currentStateContext.getNoteId();
                if (!currentNoteId) {
                    throw new Error('Current note ID not set');
                }

                const shiftKey = StateMachine.currentStateContext.getShiftKey();
                if (typeof shiftKey !== 'boolean') {
                    throw new Error('Add button click missing shift key state');
                }

                if (shiftKey) {
                    // Shift+Add: Create child note
                    StateMachine.currentStateContext
                        .addEffect(new CreateChildEffect(currentNoteId))
                        .setTargetState('editing');
                } else {
                    // Add: Create sibling note below
                    StateMachine.currentStateContext
                        .addEffect(new CreateSiblingEffect(currentNoteId))
                        .setTargetState('editing');
                }
                break;
            }

            case 'SEARCH_FOCUSED': {
                // Return to idle if inactive
                if (StateMachine.currentStateContext.isInactive()) {
                    StateMachine.currentStateContext.setTargetState('idle');
                }
                break;
            }

            case 'SEARCH_CLICKED': {
                // Save and transition to searching state
                StateMachine.currentStateContext
                    .setTargetState('searching');
                break;
            }

            case 'KEY_DOWN': {
                const key = StateMachine.currentStateContext.getKey();
                const metaKey = StateMachine.currentStateContext.getMetaKey();
                const shiftKey = StateMachine.currentStateContext.getShiftKey();
                
                // Handle keyboard shortcuts
                if (key === 'Escape') {
                    console.log('Escape key pressed');
                    // Escape: Return to idle
                    StateMachine.currentStateContext
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
                        StateMachine.currentStateContext
                            .addEffect(new CreateChildEffect(currentNoteId))
                            .setTargetState('editing');
                    } else {
                        // Cmd+Enter: Create sibling note below
                        StateMachine.currentStateContext
                            .addEffect(new CreateSiblingEffect(currentNoteId))
                            .setTargetState('editing');
                    }
                }

                if (metaKey && (key === 'Delete' || key === 'Backspace')) {
                    // Cmd+Delete: Delete current note
                    const currentNoteId = StateMachine.currentStateContext.getNoteId();
                    if (!currentNoteId) {
                        throw new Error('Current note ID not set');
                    }

                    StateMachine.currentStateContext
                        .addEffect(new DeleteNoteEffect(currentNoteId))
                        .setTargetState('idle');
                }

                if (metaKey && (key === 'ArrowUp' || key === 'ArrowDown')) {
                    // Get current note ID for moving
                    const currentNoteId = StateMachine.currentStateContext.getNoteId();
                    if (!currentNoteId) {
                        throw new Error('Current note ID not set');
                    }

                    // Queue move effect and stay in editing
                    StateMachine.currentStateContext
                        .addEffect(new MoveNoteEffect(currentNoteId, key === 'ArrowUp' ? 'before' : 'after'))
                        .setTargetState('editing')
                        .setTargetNoteId(currentNoteId);
                }
                break;
            }

            case 'NOTE_CONTENT_CHANGED': {
                // Log the current lastSavedContent value
                console.log('Last saved content:', StateMachine.currentStateContext.getLastSavedContent());
                
                // Reset inactivity timer
                StateMachine.startActivityMonitor();
                break;
            }

            case 'TRASH_CAN_CLICKED': {
                const currentNoteId = StateMachine.currentStateContext.getNoteId();
                if (!currentNoteId) {
                    throw new Error('Current note ID not set');
                }

                StateMachine.currentStateContext
                    .addEffect(new DeleteNoteEffect(currentNoteId))
                    .setTargetState('idle');
                break;
            }

            default:
                throw new Error(`Unhandled event in editing state: ${eventType}`);
        }
    }
};
