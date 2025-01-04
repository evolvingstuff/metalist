/**
 * Maps low-level events to state machine events based on current state
 * This is where we interpret the user's intention based on context
 */
export const EventMapper = {
    // Current state → event type → handler mapping
    handlers: {
        idle: {
            ADD_BUTTON_CLICKED: () => ({
                type: 'CREATE_TOP_NOTE'
            }),
            NOTE_CONTENT_CLICKED: (event) => ({
                type: 'START_EDITING',
                data: {
                    nextNote: event.noteElement,
                    nextContent: DOMUtils.getNoteContentText(event.noteElement),
                    cursorPosition: event.position
                }
            }),

            COMMAND_ENTER_PRESSED: (event) => ({
                type: 'CREATE_NOTE',
                data: {
                    type: 'top'
                }
            }),

            SEARCH_FOCUSED: (event) => ({
                type: 'START_SEARCH',
                data: {
                    initialQuery: event.query
                }
            }),

            FRAGMENT_LOADED: (event) => {
                // Check if we need to start editing a new note
                const newNoteId = localStorage.getItem('newNoteId');
                if (newNoteId) {
                    const newNote = document.querySelector(`[data-id="${newNoteId}"]`);
                    if (newNote) {
                        localStorage.removeItem('newNoteId');
                        return {
                            type: 'START_EDITING',
                            data: {
                                nextNote: newNote,
                                cursorPosition: localStorage.getItem('cursorPosition') || 'end'
                            }
                        };
                    }
                }
                return null;  // No state change needed
            }
        },

        editing: {
            NOTE_CONTENT_CLICKED: (event, context) => {
                // If clicking same note, do nothing
                if (event.noteElement === context.currentNote) {
                    return null;
                }

                return {
                    type: 'SWITCH_NOTE',
                    data: {
                        prevNote: context.currentNote,
                        lastSavedContent: context.lastSavedContent,
                        nextNote: event.noteElement,
                        nextContent: DOMUtils.getNoteContentText(event.noteElement),
                        cursorPosition: event.position
                    }
                };
            },

            ESCAPE_PRESSED: (event, context) => ({
                type: 'STOP_EDITING',
                data: {
                    prevNote: context.currentNote,
                    lastSavedContent: context.lastSavedContent
                }
            }),

            COMMAND_ENTER_PRESSED: (event, context) => ({
                type: 'CREATE_NOTE',
                data: {
                    type: event.shift ? 'child' : 'sibling',
                    parentNote: context.currentNote
                }
            }),

            COMMAND_ARROW_PRESSED: (event, context) => ({
                type: 'MOVE_NOTE',
                data: {
                    direction: event.direction,
                    noteElement: context.currentNote
                }
            }),

            FRAGMENT_LOADED: (event, context) => {
                // If we were editing a note that was moved
                const wasMovedWhileEditing = localStorage.getItem('wasMovedWhileEditing');
                if (wasMovedWhileEditing) {
                    localStorage.removeItem('wasMovedWhileEditing');
                    const noteId = localStorage.getItem('newNoteId');
                    if (noteId) {
                        const movedNote = document.querySelector(`[data-id="${noteId}"]`);
                        if (movedNote) {
                            return {
                                type: 'SWITCH_NOTE',
                                data: {
                                    prevNote: context.currentNote,
                                    nextNote: movedNote,
                                    cursorPosition: localStorage.getItem('cursorPosition') || 'end'
                                }
                            };
                        }
                    }
                }
                return null;
            }
        },

        searching: {
            NOTE_CONTENT_CLICKED: (event) => ({
                type: 'START_EDITING',
                data: {
                    nextNote: event.noteElement,
                    nextContent: DOMUtils.getNoteContentText(event.noteElement),
                    cursorPosition: event.position
                }
            }),

            ESCAPE_PRESSED: () => ({
                type: 'STOP_SEARCH'
            }),

            SEARCH_QUERY_CHANGED: (event) => ({
                type: 'UPDATE_SEARCH',
                data: {
                    query: event.query
                }
            }),

            FRAGMENT_LOADED: (event, context) => ({
                type: 'UPDATE_SEARCH',
                data: {
                    query: context.searchQuery,
                    fragmentData: event.data.apiResponse
                }
            })
        }
    },

    /**
     * Maps a low-level event to a state machine event based on current state
     */
    mapEvent(rawEvent, currentState, context = {}) {
        const stateHandlers = this.handlers[currentState];
        if (!stateHandlers) {
            console.warn(`No handlers for state: ${currentState}`);
            return null;
        }

        const handler = stateHandlers[rawEvent.type];
        if (!handler) {
            console.warn(`No handler for event ${rawEvent.type} in state ${currentState}`);
            return null;
        }

        return handler(rawEvent, context);
    }
}; 