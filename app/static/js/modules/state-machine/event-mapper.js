import { DOMUtils } from '../dom-utils.js';
import { StateContext } from './state-context.js';

export const EventMapper = {
                
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

        const handler = this.handlers[currentState]?.[stateContext.type];
        if (!handler) {
            throw new Error(`No handler for event '${stateContext.type}' in state '${currentState}'`);
        }

        return handler(stateContext);
    }
}; 