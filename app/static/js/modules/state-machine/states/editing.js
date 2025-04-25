import { DOMUtils } from '../../dom-utils.js';
import { NotesAPI } from '../../api-client.js';
import { StateContext } from '../state-context.js';
import { StateMachine } from '../state-machine-controller.js';
import { CONFIG } from '../../config.js';
import { CreateChildEffect, CreateSiblingEffect, UpdateNoteEffect, SaveNoteEffect, DeleteNoteEffect, MoveNoteEffect } from '../effects.js';

export const editingTransitions = {
    enter: async () => {
                                
        if (!(StateMachine.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }

        const noteId = StateMachine.currentStateContext.getNoteId();
        if (!noteId) {
            throw new Error('Note ID not set');
        }

        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

        const coordinates = StateMachine.currentStateContext.getCoordinates();
        if (coordinates) {
            const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, coordinates);
            StateMachine.currentStateContext.setCursorOffset(cursorOffset);
            StateMachine.currentStateContext.resetCoordinates();
        }

        const contentElement = DOMUtils.getNoteContent(noteElement);
        console.log('Entering edit mode for note:', {
            noteId,
            innerHTML: contentElement.innerHTML
        });

        const content = DOMUtils.getNoteContentHTML(noteElement);
        StateMachine.currentStateContext.setLastSavedContent(content || '');

        DOMUtils.setNoteEditable(noteElement, true);
        DOMUtils.focusNote(noteElement, StateMachine.currentStateContext.getCursorOffset());

        StateMachine.startActivityMonitor();
    },

    exit: async () => {
                                
        StateMachine.stopActivityMonitor();

        const noteId = StateMachine.currentStateContext.getNoteId();
        if (!noteId) {
            throw new Error('No note ID in editing state context');
        }

        const noteElement = DOMUtils.getNoteById(noteId);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

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
                                                
            StateMachine.currentStateContext.addEffect(new SaveNoteEffect(noteId, currentContent));
        }

        DOMUtils.setNoteEditable(noteElement, false);
    },

    handleEvent: async () => {
                                
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

                    const clickCoordinates = StateMachine.currentStateContext.getCoordinates();
                    const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, clickCoordinates);

                    StateMachine.currentStateContext
                        .setTargetNoteId(targetNoteId)
                        .setCursorOffset(cursorOffset)
                        .setTargetState('editing');
                }
                break;
            }

            case 'ADD_BUTTON_CLICKED': {
                                                                
                const currentNoteId = StateMachine.currentStateContext.getNoteId();
                if (!currentNoteId) {
                    throw new Error('Current note ID not set');
                }

                const shiftKey = StateMachine.currentStateContext.getShiftKey();
                if (typeof shiftKey !== 'boolean') {
                    throw new Error('Add button click missing shift key state');
                }

                if (shiftKey) {
                                                                                
                    StateMachine.currentStateContext
                        .addEffect(new CreateChildEffect(currentNoteId))
                        .setTargetState('editing');
                } else {
                                                                                
                    StateMachine.currentStateContext
                        .addEffect(new CreateSiblingEffect(currentNoteId))
                        .setTargetState('editing');
                }
                break;
            }

            case 'SEARCH_FOCUSED': {
                                                                
                if (StateMachine.currentStateContext.isInactive()) {
                    StateMachine.currentStateContext.setTargetState('idle');
                }
                break;
            }

            case 'SEARCH_CLICKED': {
                                                                
                StateMachine.currentStateContext
                    .setTargetState('searching');
                break;
            }

            case 'KEY_DOWN': {
                const key = StateMachine.currentStateContext.getKey();
                const metaKey = StateMachine.currentStateContext.getMetaKey();
                const shiftKey = StateMachine.currentStateContext.getShiftKey();

                if (key === 'Escape') {
                    console.log('Escape key pressed');
                                                                                
                    StateMachine.currentStateContext
                        .setTargetState('idle');
                    break;
                }

                if (metaKey && key === 'Enter') {
                                                                                
                    const currentNoteId = StateMachine.currentStateContext.getNoteId();
                    if (!currentNoteId) {
                        throw new Error('Current note ID not set');
                    }

                    if (shiftKey) {
                                                                                                
                        StateMachine.currentStateContext
                            .addEffect(new CreateChildEffect(currentNoteId))
                            .setTargetState('editing');
                    } else {
                                                                                                
                        StateMachine.currentStateContext
                            .addEffect(new CreateSiblingEffect(currentNoteId))
                            .setTargetState('editing');
                    }
                }

                if (metaKey && (key === 'Delete' || key === 'Backspace')) {
                                                                                
                    const currentNoteId = StateMachine.currentStateContext.getNoteId();
                    if (!currentNoteId) {
                        throw new Error('Current note ID not set');
                    }

                    StateMachine.currentStateContext
                        .addEffect(new DeleteNoteEffect(currentNoteId))
                        .setTargetState('idle');
                }

                if (metaKey && (key === 'ArrowUp' || key === 'ArrowDown')) {
                                                                                
                    const currentNoteId = StateMachine.currentStateContext.getNoteId();
                    if (!currentNoteId) {
                        throw new Error('Current note ID not set');
                    }

                    StateMachine.currentStateContext
                        .addEffect(new MoveNoteEffect(currentNoteId, key === 'ArrowUp' ? 'before' : 'after'))
                        .setTargetState('editing')
                        .setTargetNoteId(currentNoteId);
                }
                break;
            }

            case 'NOTE_CONTENT_CHANGED': {
                                                                
                console.log('Last saved content:', StateMachine.currentStateContext.getLastSavedContent());

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
