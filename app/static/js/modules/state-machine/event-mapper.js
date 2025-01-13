import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';

/**
 * Event Mapper
 * 
 * Maps raw events (StateContext objects) to state machine events based on current state.
 * This is where we interpret user intentions based on state context.
 * 
 * Structure:
 * {
 *   [state]: {
 *     [eventType]: (stateContext) => ({
 *       type: 'STATE_MACHINE_EVENT',
 *       context: stateContext  // Pass through or modified StateContext
 *     })
 *   }
 * }
 * 
 * Flow:
 * 1. Raw Events -> StateContext with event type and data
 * 2. Event Mapper -> State machine event with same or modified StateContext
 * 3. State Machine -> Handles event and context
 * 
 * NO_OP events are returned when:
 * - No handler exists for current state/event type
 * - Event should be ignored in current state
 * 
 * @example
 * // Mapping in idle state
 * idle: {
 *   ADD_BUTTON_CLICKED: (stateContext) => ({
 *     type: 'CREATE_TOP_NOTE',
 *     context: stateContext
 *   })
 * }
 */
export const EventMapper = {
    // Current state → event type → handler mapping
    handlers: {
        idle: {
            KEY_DOWN: (stateContext) => {
                // Pass through key info but strip DOM
                return stateContext.setType('KEY_DOWN').setKey(stateContext.key).setMetaKey(stateContext.metaKey).setShiftKey(stateContext.shiftKey);
            },

            ADD_BUTTON_CLICKED: (stateContext) => stateContext.setType('CREATE_TOP_NOTE'),

            NOTE_CONTENT_CLICKED: (stateContext) => {
                if (!stateContext) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event');
                }

                if (!stateContext.noteId) {
                    throw new Error('Note content click missing note ID');
                }

                return stateContext.setType('NOTE_CONTENT_CLICKED').setNoteId(stateContext.noteId);
            },

            NOTE_CONTENT_CHANGED: (stateContext) => {
                return stateContext
                    .setType('NOTE_CONTENT_CHANGED')
                    .setNoteId(stateContext.noteId)
                    .setContent(stateContext.content);
            },

            CLICKED_OUTSIDE_NOTE: (stateContext) => stateContext.setType('CLICKED_OUTSIDE_NOTE'),

            SEARCH_FOCUSED: (stateContext) => stateContext.setType('SEARCH_FOCUSED'),

            FRAGMENT_LOADED: (stateContext) => stateContext.setType('FRAGMENT_LOADED'),

            NO_OP: (stateContext) => stateContext.setType('NO_OP')
        },

        editing: {
            KEY_DOWN: (stateContext) => {
                const context = stateContext.context || new StateContext();
                context.key = stateContext.key;
                context.metaKey = stateContext.metaKey;
                context.shiftKey = stateContext.shiftKey;

                return stateContext.setType('KEY_DOWN').setContext(context);
            },

            NOTE_CONTENT_CLICKED: (stateContext) => {
                if (!stateContext) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event');
                }

                if (!stateContext.noteId) {
                    throw new Error('Note content click missing note ID');
                }

                return stateContext.setType('NOTE_CONTENT_CLICKED').setNoteId(stateContext.noteId);
            },

            NOTE_CONTENT_CHANGED: (stateContext) => {
                return stateContext
                    .setType('NOTE_CONTENT_CHANGED')
                    .setNoteId(stateContext.noteId)
                    .setContent(stateContext.content);
            },

            CLICKED_OUTSIDE_NOTE: (stateContext) => stateContext.setType('CLICKED_OUTSIDE_NOTE'),

            SEARCH_FOCUSED: (stateContext) => stateContext.setType('SEARCH_FOCUSED'),

            FRAGMENT_LOADED: (stateContext) => stateContext.setType('FRAGMENT_LOADED'),

            NO_OP: (stateContext) => stateContext.setType('NO_OP')
        },

        searching: {
            KEY_DOWN: (stateContext) => stateContext
                .setType('KEY_DOWN')
                .setKey(stateContext.key)
                .setMetaKey(stateContext.metaKey)
                .setShiftKey(stateContext.shiftKey),

            NOTE_CONTENT_CLICKED: (stateContext) => {
                if (!stateContext) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event');
                }

                if (!stateContext.noteId) {
                    throw new Error('Note content click missing note ID');
                }

                return stateContext
                    .setType('NOTE_CONTENT_CLICKED')
                    .setNoteId(stateContext.noteId)
                    .setCoordinates(stateContext.coordinates)
                    .setLastSavedContent(stateContext.lastSavedContent);
            },

            NOTE_CONTENT_CHANGED: (stateContext) => {
                return stateContext
                    .setType('NOTE_CONTENT_CHANGED')
                    .setNoteId(stateContext.noteId)
                    .setContent(stateContext.content);
            },

            CLICKED_OUTSIDE_NOTE: (stateContext) => stateContext.setType('CLICKED_OUTSIDE_NOTE'),

            SEARCH_FOCUSED: (stateContext) => stateContext.setType('SEARCH_FOCUSED'),

            FRAGMENT_LOADED: (stateContext) => stateContext.setType('FRAGMENT_LOADED'),

            NO_OP: (stateContext) => stateContext.setType('NO_OP')
        }
    },

    /**
     * Maps a low-level event to a state machine event based on current state
     */
    mapEvent(stateContext, currentState) {
        if (!stateContext) {
            throw new Error('State context is required');
        }
        if (!(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context');
        }
        if (!currentState) {
            throw new Error('Current state is required');
        }

        // Get handler for current state and event type
        const handler = this.handlers[currentState]?.[stateContext.type];
        if (!handler) {
            return stateContext.setType('NO_OP');
        }

        // Map raw event to state machine event
        return handler(stateContext);
    }
}; 