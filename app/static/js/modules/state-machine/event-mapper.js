import { DOMUtils } from '../dom-utils.js';

/**
 * Event Mapper
 * 
 * Maps low-level events to state machine events based on current state.
 * This is where we interpret user intentions based on context.
 * 
 * Structure:
 * {
 *   [state]: {
 *     [eventType]: (event, context) => ({
 *       type: 'STATE_MACHINE_EVENT',
 *       data: { ... }
 *     })
 *   }
 * }
 * 
 * Each handler:
 * 1. Receives raw event and current state context
 * 2. Returns state machine event or null
 * 3. Can access DOM and other utilities
 * 
 * @example
 * // Mapping in idle state
 * idle: {
 *   ADD_BUTTON_CLICKED: () => ({
 *     type: 'CREATE_TOP_NOTE'
 *   })
 * }
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
            // Explicitly handle with no-op - clicking outside notes in idle state requires no action
            CLICK_OUTSIDE_NOTE: () => null,
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
                return null;  // No state change needed in idle state
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

            CLICK_OUTSIDE_NOTE: (event, context) => ({
                type: 'STOP_EDITING',
                data: {
                    prevNote: context.currentNote,
                    lastSavedContent: context.lastSavedContent
                }
            }),

            FRAGMENT_LOADED: (event, context) => {
                // No state restoration needed
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