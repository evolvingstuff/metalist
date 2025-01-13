import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';

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
            KEY_DOWN: (event) => {
                // Pass through key info but strip DOM
                return {
                    type: 'KEY_DOWN',
                    context: event.context,  // Pass through existing context
                    key: event.key,
                    metaKey: event.metaKey,
                    shiftKey: event.shiftKey
                };
            },

            ADD_BUTTON_CLICKED: () => ({
                type: 'CREATE_TOP_NOTE'
            }),

            NOTE_CONTENT_CLICKED: (event) => {
                // Validate required fields
                if (!event) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event');
                }
                if (!event.context) {
                    throw new Error('NOTE_CONTENT_CLICKED missing context');
                }
                if (!(event.context instanceof StateContext)) {
                    throw new Error('Invalid context: must be StateContext instance');
                }

                return {
                    type: 'NOTE_CONTENT_CLICKED',
                    context: event.context
                };
            },

            CLICKED_OUTSIDE_NOTE: () => ({ type: 'CLICKED_OUTSIDE_NOTE' }),

            SEARCH_FOCUSED: () => ({ type: 'SEARCH_FOCUSED' }),

            FRAGMENT_LOADED: () => ({ type: 'FRAGMENT_LOADED' }),

            NO_OP: () => ({ type: 'NO_OP' })
        },

        editing: {
            KEY_DOWN: (event) => {
                // Pass through key info but strip DOM
                return {
                    type: 'KEY_DOWN',
                    context: event.context,  // Pass through existing context
                    key: event.key,
                    metaKey: event.metaKey,
                    shiftKey: event.shiftKey
                };
            },

            NOTE_CONTENT_CLICKED: (event) => {
                // Validate required fields
                if (!event) {
                    throw new Error('NOTE_CONTENT_CLICKED missing event');
                }
                if (!event.context) {
                    throw new Error('NOTE_CONTENT_CLICKED missing context');
                }
                if (!(event.context instanceof StateContext)) {
                    throw new Error('Invalid context: must be StateContext instance');
                }

                return {
                    type: 'NOTE_CONTENT_CLICKED',
                    context: event.context
                };
            },

            CLICKED_OUTSIDE_NOTE: () => ({ type: 'CLICKED_OUTSIDE_NOTE' }),

            SEARCH_FOCUSED: () => ({ type: 'SEARCH_FOCUSED' }),

            FRAGMENT_LOADED: () => ({ type: 'FRAGMENT_LOADED' }),

            NO_OP: () => ({ type: 'NO_OP' })
        },

        searching: {
            KEY_DOWN: (event) => {
                // Pass through key info but strip DOM
                return {
                    type: 'KEY_DOWN',
                    context: event.context,  // Pass through existing context
                    key: event.key,
                    metaKey: event.metaKey,
                    shiftKey: event.shiftKey
                };
            },

            NOTE_CONTENT_CLICKED: (event) => ({
                type: 'NOTE_CONTENT_CLICKED',
                context: event.context  // Pass through the context
            }),

            CLICKED_OUTSIDE_NOTE: () => ({
                type: 'CLICKED_OUTSIDE_NOTE'
            }),

            SEARCH_FOCUSED: () => ({ type: 'SEARCH_FOCUSED' }),

            FRAGMENT_LOADED: () => ({ type: 'FRAGMENT_LOADED' }),

            NO_OP: () => ({ type: 'NO_OP' })
        }
    },

    /**
     * Maps a low-level event to a state machine event based on current state
     * NO MERCY - all data must be valid!
     */
    mapEvent(rawEvent, currentState, context = {}) {
        // NO MERCY validation
        if (!rawEvent) {
            throw new Error('Raw event is required');
        }
        if (!rawEvent.type) {
            throw new Error('Raw event missing type');
        }
        if (!currentState) {
            throw new Error('Current state is required');
        }
        if (!this.handlers[currentState]) {
            throw new Error(`Invalid state: ${currentState}`);
        }

        // Get handler for current state and event type
        const handler = this.handlers[currentState][rawEvent.type];
        if (!handler) {
            throw new Error(`No handler for event ${rawEvent.type} in state ${currentState}`);
        }

        // Map event with context
        const mappedEvent = handler(rawEvent);
        if (!mappedEvent) {
            throw new Error(`Handler returned null for event ${rawEvent.type}`);
        }
        if (!mappedEvent.type) {
            throw new Error(`Handler returned event without type for ${rawEvent.type}`);
        }

        return mappedEvent;
    }
}; 