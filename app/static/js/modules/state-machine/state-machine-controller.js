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
export const StateMachine = {
    state: 'idle',
    data: {},
    listeners: [],
    activityMonitor: null,

    /**
     * Initialize the state machine
     */
    init() {
        this.state = 'idle';
        this.data = {};
        this.activityMonitor = new ActivityMonitor(this);
    },

    /**
     * Handle a raw DOM event
     */
    async handleRawEvent(eventName, domEvent) {
        if (this.state === 'editing') {
            this.activityMonitor.handleActivity();
        }

        // Convert DOM event to low-level event
        const rawEvent = RawEvents[`handle${eventName}`]?.(domEvent);
        if (!rawEvent) return;

        console.log('🔰 Raw Event:', { eventName, rawEvent });

        // Map to state machine event
        const mappedEvent = EventMapper.mapEvent(rawEvent, this.state, this.data);
        if (!mappedEvent) return;

        console.log('📍 Mapped Event:', { 
            from: rawEvent.type,
            to: mappedEvent.type,
            state: this.state,
            data: mappedEvent.data 
        });

        // Execute the event
        await this.handleMappedEvent(mappedEvent);
    },

    /**
     * Handle a mapped state machine event
     */
    async handleMappedEvent(event) {
        const { type, data } = event;
        
        console.log('🎯 State Machine Event:', {
            type,
            currentState: this.state,
            data
        });

        // Let current state handle event first
        const stateHandler = StateTransitions.handlers[this.state];
        if (!stateHandler?.handleEvent) {
            throw new Error(`No handler for state: ${this.state}`);
        }

        const result = await stateHandler.handleEvent(event, this.data);
        if (!result) {
            return;
        }

        // If state handler returns a transition request, execute it
        if (result.type?.startsWith('START_')) {
            const newState = result.type.slice(6).toLowerCase();
            await this.transition(newState, result.data);
            return;
        }

        // Otherwise just update state data
        this.data = { ...this.data, ...result };
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
     * Get new state based on event type
     */
    getNewState(eventType) {
        const stateMap = {
            'CREATE_TOP_NOTE': 'editing',
            'START_EDITING': 'editing',
            'STOP_EDITING': 'idle',
            'SWITCH_NOTE': 'editing',
            'SEARCH_FOCUSED': 'searching',
            'STOP_SEARCH': 'idle',
            'UPDATE_SEARCH' : null,  // null means stay in current state
            'CREATE_NOTE': 'editing',
            'ENTER_PRESSED': 'editing',
            'COMMAND_ENTER_PRESSED': 'editing',
            'INACTIVITY_TIMEOUT': null  // Stay in current state, let handler deal with it
        };

        return stateMap[eventType] ?? null;
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