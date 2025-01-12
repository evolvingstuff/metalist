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
            KEY_DOWN: (event) => event, // Pass through to state handler

            ADD_BUTTON_CLICKED: () => ({
                type: 'CREATE_TOP_NOTE'
            }),

            NOTE_CONTENT_CLICKED: (event) => ({
                type: 'START_EDITING',
                data: {
                    noteId: event.noteId,
                    cursorPosition: event.position
                }
            }),

            CLICKED_OUTSIDE_NOTE: () => ({ type: 'NO_OP' }),

            SEARCH_FOCUSED: () => ({
                type: 'START_SEARCHING',
                data: {}
            }),

            FRAGMENT_LOADED: () => ({ type: 'NO_OP' }),

            NO_OP: () => ({ type: 'NO_OP' })
        },

        editing: {
            KEY_DOWN: (event) => event, // Pass through to state handler

            NOTE_CONTENT_CLICKED: (event, context) => {
                // Validate required fields
                if (!event) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event');
                }
                if (!event.target) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event.target');
                }
                if (!event.noteElement) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event.noteElement');
                }

                return { 
                    type: 'NOTE_CONTENT_CLICKED',
                    noteElement: event.noteElement,
                    target: event.target
                };
            },

            CLICKED_OUTSIDE_NOTE: () => ({ type: 'START_IDLE' }),

            SEARCH_FOCUSED: () => ({
                type: 'START_SEARCHING',
                data: { query: '' }
            }),

            FRAGMENT_LOADED: () => ({ type: 'NO_OP' }),

            NO_OP: () => ({ type: 'NO_OP' })
        },

        searching: {
            KEY_DOWN: (event) => event, // Pass through to state handler

            NOTE_CONTENT_CLICKED: (event) => ({
                type: 'START_EDITING',
                data: {
                    noteId: event.noteId,
                    cursorPosition: event.position
                }
            }),

            CLICKED_OUTSIDE_NOTE: () => ({
                type: 'START_IDLE'
            }),

            SEARCH_FOCUSED: () => ({ type: 'NO_OP' }),

            FRAGMENT_LOADED: () => ({ type: 'NO_OP' }),

            NO_OP: () => ({ type: 'NO_OP' })
        }
    },

    /**
     * Maps a low-level event to a state machine event based on current state
     */
    mapEvent(rawEvent, currentState, context = {}) {
        const stateHandlers = this.handlers[currentState];
        if (!stateHandlers) {
            throw new Error(`No handlers for state: ${currentState}`);
        }

        const handler = stateHandlers[rawEvent.type];
        if (!handler) {
            throw new Error(`No handler for event ${rawEvent.type} in state ${currentState}`);
        }

        const mappedEvent = handler(rawEvent, context);
        // Return a special NO_OP event for null returns
        return mappedEvent === null ? { type: 'NO_OP' } : mappedEvent;
    }
}; 