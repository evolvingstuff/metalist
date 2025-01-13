import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';

/**
 * Event Mapper
 * 
 * Maps raw DOM events to state machine events based on the current state.
 * The mapping is purely about event type translation - all event properties
 * (noteId, content, coordinates, etc.) are preserved from the original StateContext.
 * 
 * Design:
 * 1. Each state (idle, editing, searching) defines which raw events it handles
 * 2. For each raw event, defines what state machine event it maps to
 * 3. Unhandled events in a state are considered errors
 * 
 * Example:
 * In idle state:
 *   NOTE_CONTENT_CLICKED -> NOTE_CONTENT_CLICKED
 *   SEARCH_FOCUSED -> SEARCH_FOCUSED
 * 
 * In editing state:
 *   CLICKED_OUTSIDE_NOTE -> CLICKED_OUTSIDE_NOTE
 *   NOTE_CONTENT_CLICKED -> NOTE_CONTENT_CLICKED (same event)
 */
export const EventMapper = {
    // Current state → event type → handler mapping
    handlers: {
        idle: {
            KEY_DOWN: (stateContext) => stateContext.setType('KEY_DOWN'),
            ADD_BUTTON_CLICKED: (stateContext) => stateContext.setType('ADD_BUTTON_CLICKED'),
            NOTE_CONTENT_CLICKED: (stateContext) => stateContext.setType('NOTE_CONTENT_CLICKED'),
            NOTE_CONTENT_CHANGED: (stateContext) => stateContext.setType('NOTE_CONTENT_CHANGED'),
            CLICKED_OUTSIDE_NOTE: (stateContext) => stateContext.setType('CLICKED_OUTSIDE_NOTE'),
            SEARCH_FOCUSED: (stateContext) => stateContext.setType('SEARCH_FOCUSED'),
            FRAGMENT_LOADED: (stateContext) => stateContext.setType('FRAGMENT_LOADED'),
            NO_OP: (stateContext) => stateContext.setType('NO_OP')
        },

        editing: {
            KEY_DOWN: (stateContext) => stateContext.setType('KEY_DOWN'),
            NOTE_CONTENT_CLICKED: (stateContext) => stateContext.setType('NOTE_CONTENT_CLICKED'),
            NOTE_CONTENT_CHANGED: (stateContext) => stateContext.setType('NOTE_CONTENT_CHANGED'),
            CLICKED_OUTSIDE_NOTE: (stateContext) => stateContext.setType('CLICKED_OUTSIDE_NOTE'),
            SEARCH_FOCUSED: (stateContext) => stateContext.setType('SEARCH_FOCUSED'),
            FRAGMENT_LOADED: (stateContext) => stateContext.setType('FRAGMENT_LOADED'),
            NO_OP: (stateContext) => stateContext.setType('NO_OP')
        },

        searching: {
            KEY_DOWN: (stateContext) => stateContext.setType('KEY_DOWN'),
            NOTE_CONTENT_CLICKED: (stateContext) => stateContext.setType('NOTE_CONTENT_CLICKED'),
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
            throw new Error(`No handler for event '${stateContext.type}' in state '${currentState}'`);
        }

        // Map raw event to state machine event
        return handler(stateContext);
    }
}; 