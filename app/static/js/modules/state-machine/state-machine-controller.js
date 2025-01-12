import { RawEvents } from './raw-events.js';
import { EventMapper } from './event-mapper.js';
import { StateTransitions } from './transition-coordinator.js';
import { NotesAPI } from '../api-client.js';
import { ActivityMonitor } from './activity-monitor.js';

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
 *   data: { nextNote: noteElement }
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
    KEY_DOWN: 'KEY_DOWN',
    SWITCH_NOTE: 'SWITCH_NOTE',
    SEARCH_FOCUSED: 'SEARCH_FOCUSED',
    SEARCH_QUERY_CHANGED: 'SEARCH_QUERY_CHANGED',
    FRAGMENT_LOADED: 'FRAGMENT_LOADED',
    INACTIVITY_TIMEOUT: 'INACTIVITY_TIMEOUT',
    NO_OP: 'NO_OP'
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
    data: {},
    listeners: [],
    activityMonitor: null,

    /**
     * Initialize the state machine
     */
    init() {
        this.state = States.IDLE;
        this.data = {};
        this.activityMonitor = new ActivityMonitor(this);
    },

    /**
     * Check if an event type is valid
     */
    isValidEvent(eventType) {
        return Object.values(Events).includes(eventType);
    },

    /**
     * Handle a raw DOM event
     */
    async handleRawEvent(eventName, domEvent) {
        if (this.state === States.EDITING) {
            this.activityMonitor.handleActivity();
        }

        // Convert DOM event to low-level event
        const rawEvent = RawEvents.handleEvent(eventName, domEvent);
        console.log('🎯 Raw Event:', { eventName, rawEvent });

        // Map to state machine event
        const mappedEvent = EventMapper.mapEvent(rawEvent, this.state, this.data);
            
        if (!mappedEvent) {
            throw new Error(`No mapped event for raw event: ${rawEvent.type}`);
        }

        // Skip NO_OP events
        if (mappedEvent.type === 'NO_OP') {
            console.log('⏭️ Skipping NO_OP event');
            return;
        }

        // Handle mapped event
        await this.handleMappedEvent(mappedEvent);
    },

    /**
     * Handle a mapped state machine event
     */
    async handleMappedEvent(event) {
        const { type, data } = event;
        
        // Every event must be explicitly defined
        if (!this.isValidEvent(type)) {
            throw new Error(`Invalid event type: ${type}`);
        }

        console.log('🎯 State Machine Event:', {
            type,
            currentState: this.state,
            data
        });

        // Special case: NO_OP events are explicitly ignored
        if (type === Events.NO_OP) {
            console.log('🔕 Ignoring NO_OP event');
            return;
        }

        // Handle state transitions
        const targetState = StateTransitionMap[type];
        if (targetState) {
            await this.transition(targetState, data);
            return;
        }

        // Let current state handle non-transition events
        const stateHandler = StateTransitions.handlers[this.state];
        if (!stateHandler?.handleEvent) {
            throw new Error(`No handler for state: ${this.state}`);
        }

        const result = await stateHandler.handleEvent(event, this.data);
        
        // State MUST handle the event by either:
        // 1. Returning a transition event
        // 2. Returning new state data
        if (typeof result !== 'object') {
            throw new Error(`Invalid handler result for event ${type}: ${result}`);
        }

        // Handle transition requests from state handlers
        const handlerTargetState = StateTransitionMap[result.type];
        if (handlerTargetState) {
            await this.transition(handlerTargetState, result.data);
            return;
        }

        // If not a transition, must be new state data
        this.data = { ...this.data, ...result };
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
                return States.IDLE;
            default:
                throw new Error(`Unknown transition event: ${eventType}`);
        }
    },

    /**
     * Execute a state transition with an optional command
     */
    async transition(newState, data = {}, command = null) {
        const oldState = this.state;
        
        data.activityMonitor = this.activityMonitor;
        
        console.log('🔄 [TRANSITION] Start:', {
            from: oldState,
            to: newState,
            data
        });

        try {
            // Execute transition and get new state data
            console.log('🔄 [TRANSITION] Executing state transition');
            const newData = await StateTransitions.execute(oldState, newState, {
                ...this.data,
                ...data
            }, command);
            console.log('🔄 [TRANSITION] State transition executed');

            // Update state
            this.state = newState;
            this.data = { ...this.data, ...newData };

            console.log('✨ [TRANSITION] New State:', {
                state: this.state,
                data: this.data
            });

            // Notify listeners
            this.notifyListeners(oldState, newState);

            return true;
        } catch (error) {
            throw new Error('Transition failed:', error);
        }
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
    notifyListeners(oldState, newState) {
        this.listeners.forEach(listener => {
            try {
                listener(oldState, newState, this.data);
            } catch (error) {
                throw new Error('Listener error:', error);
            }
        });
    }
};