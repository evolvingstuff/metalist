import { RawEvents } from './raw-events.js';
import { EventMapper } from './event-mapper.js';
import { StateTransitions } from './transition-coordinator.js';
import { NotesAPI } from '../api-client.js';
import { ActivityMonitor } from './activity-monitor.js';
import { StateContext } from './state-context.js';
import { DOMUtils } from '../dom-utils.js';

/**
 * State Machine Controller
 * 
 * Core controller that coordinates all state machine operations:
 * 1. Raw event handling (DOM events → low-level events)
 * 2. Event mapping (low-level events → state machine events)
 * 3. State transitions (state changes with enter/exit hooks)
 * 
 * Flow:
 * DOM Event → Raw Event → Mapped Event → State Transition → New State
 * 
 * @example
 * // Initialize
 * StateMachine.init();
 * 
 * // Handle DOM event
 * StateMachine.handleRawEvent('AddButtonClick', event);
 * 
 * // Direct state machine event
 * StateMachine.handleMappedEvent({
 *   type: 'START_EDITING',
 *   context: { nextNote: noteElement }
 * });
 */

// Valid state machine states
export const States = {
    IDLE: 'idle',
    EDITING: 'editing',
    SEARCHING: 'searching'
};

// Every single possible event must be listed here
export const Events = {
    // State transitions
    START_EDITING: 'START_EDITING',
    START_SEARCHING: 'START_SEARCHING',
    START_IDLE: 'START_IDLE',
    STOP_EDITING: 'STOP_EDITING',
    STOP_SEARCHING: 'STOP_SEARCHING',
    
    // UI events
    NOTE_CONTENT_CLICKED: 'NOTE_CONTENT_CLICKED',
    CLICKED_OUTSIDE_NOTE: 'CLICKED_OUTSIDE_NOTE',
    CREATE_TOP_NOTE: 'CREATE_TOP_NOTE',
    MENU_CLICKED: 'MENU_CLICKED',
    TRASH_CAN_CLICKED: 'TRASH_CAN_CLICKED',
    SEARCH_FOCUSED: 'SEARCH_FOCUSED',
    KEY_DOWN: 'KEY_DOWN',
    FRAGMENT_LOADED: 'FRAGMENT_LOADED',
    NO_OP: 'NO_OP',

    // Activity events
    INACTIVITY_TIMEOUT: 'INACTIVITY_TIMEOUT'
};

// Explicit mapping of which events can trigger which state transitions
const StateTransitionMap = {
    [Events.START_EDITING]: States.EDITING,
    [Events.START_SEARCHING]: States.SEARCHING,
    [Events.START_IDLE]: States.IDLE,
    [Events.STOP_EDITING]: States.IDLE,
    [Events.STOP_SEARCHING]: States.IDLE
};

export const StateMachine = {
    state: States.IDLE,
    activityMonitor: null,
    listeners: [],

    /**
     * Initialize the state machine
     */
    init() {
        this.state = States.IDLE;
        this.activityMonitor = new ActivityMonitor(this);  // Pass controller reference
        this.listeners = [];
    },

    /**
     * Check if an event type is valid
     */
    isValidEvent(eventType) {
        return Object.values(Events).includes(eventType);
    },

    /**
     * Handle raw DOM event
     * NO MERCY - all errors must be thrown!
     */
    handleRawEvent(eventName, domEvent) {
        // NO MERCY - event validation
        if (!eventName) {
            throw new Error('Event name is required');
        }
        if (!domEvent) {
            throw new Error('DOM event is required');
        }

        // Create raw event with context
        const rawEvent = RawEvents.handleEvent(eventName, domEvent);

        // NO MERCY validation
        if (!rawEvent) {
            throw new Error('Raw event handler returned null');
        }
        if (!rawEvent.type) {
            throw new Error('Raw event missing type');
        }

        // Get note info if event happened in a note
        const noteElement = DOMUtils.findNoteElement(domEvent.target);
        if (noteElement) {
            const noteId = DOMUtils.getNoteId(noteElement);
            if (!noteId) {
                throw new Error('Note missing ID');
            }

            // Create context if none exists
            if (!rawEvent.context) {
                rawEvent.context = StateContext.fromStateData({
                    noteId,
                    cursorOffset: 0
                });
            }
        }

        // Map raw event to state machine event
        const mappedEvent = EventMapper.mapEvent(rawEvent, this.state);
        if (!mappedEvent) {
            throw new Error('Event mapper returned null');
        }

        // Skip NO_OP events
        if (mappedEvent.type === Events.NO_OP) {
            console.log('Skipping NO_OP event');
            return;
        }

        // Handle mapped event
        return this.handleMappedEvent(mappedEvent);
    },

    /**
     * Handle a mapped state machine event
     */
    async handleMappedEvent(event) {
        // Validate event structure
        if (!event || typeof event !== 'object') {
            throw new Error('Invalid event: not an object');
        }

        const { type, context } = event;
        
        // Validate event type
        if (!type || typeof type !== 'string') {
            throw new Error('Invalid event: missing or invalid type');
        }
        if (!this.isValidEvent(type)) {
            throw new Error(`Invalid event type: ${type}`);
        }

        // For START_EDITING, validate context
        if (type === Events.START_EDITING) {
            if (!context) {
                throw new Error('START_EDITING missing context');
            }
            if (!(context instanceof StateContext)) {
                throw new Error('Invalid context: must be StateContext instance');
            }
            context.validate();  // NO MERCY validation
        }

        console.log(' State Machine Event:', {
            type,
            currentState: this.state,
            context
        });

        // Try transition events first
        try {
            const targetState = this.getTargetState(type);
            await this.transition(targetState, context);
            return;
        } catch (error) {
            // Not a transition event, let current state handle it
            const stateHandler = StateTransitions.handlers[this.state];
            if (!stateHandler) {
                throw new Error(`No handler for state: ${this.state}`);
            }

            const result = await stateHandler.handleEvent(event);
            if (!result) {
                throw new Error(`State ${this.state} did not handle event ${type}`);
            }

            // Check if state handler requested a transition
            if (result.type && result.type !== type) {
                const targetState = this.getTargetState(result.type);
                await this.transition(targetState, result.context || context);
            }
        }
    },

    /**
     * Get target state from transition event
     */
    getTargetState(eventType) {
        switch (eventType) {
            case Events.START_EDITING:
                return States.EDITING;
            case Events.START_SEARCHING:
                return States.SEARCHING;
            case Events.START_IDLE:
            case Events.STOP_EDITING:  // Stop editing -> go to idle
            case Events.STOP_SEARCHING:  // Stop searching -> go to idle
                return States.IDLE;
            default:
                throw new Error(`Unknown transition event: ${eventType}`);
        }
    },

    /**
     * Execute a state transition
     */
    async transition(newState, context = null) {
        // NO MERCY - validate state
        if (!newState) {
            throw new Error('New state is required');
        }
        if (!Object.values(States).includes(newState)) {
            throw new Error(`Invalid state: ${newState}`);
        }

        // NO MERCY - validate context
        if (context && !(context instanceof StateContext)) {
            throw new Error('Invalid context: must be StateContext instance');
        }

        // Add activity monitor to context if needed
        if (context && newState === States.EDITING) {
            context.setActivityMonitor(this.activityMonitor);
        }

        // Get handlers
        const oldState = this.state;
        const exitHandler = StateTransitions.handlers[oldState];
        const enterHandler = StateTransitions.handlers[newState];

        // Execute transition
        console.log('[TRANSITION] State transition:', {
            from: oldState,
            to: newState,
            context: context || 'none'
        });

        if (exitHandler?.exit) {
            await exitHandler.exit(context);
        }

        this.state = newState;

        if (enterHandler?.enter) {
            await enterHandler.enter(context);
        }

        // Notify listeners
        this.notifyListeners(oldState, newState, context);
    },

    /**
     * Add a state change listener
     */
    addListener(callback) {
        this.listeners.push(callback);
    },

    /**
     * Notify listeners of state change
     */
    notifyListeners(oldState, newState, context) {
        this.listeners.forEach(listener => {
            try {
                listener(oldState, newState, context);
            } catch (error) {
                console.error('Listener error:', error);
            }
        });
    }
};