import { RawEvents } from './raw-events.js';
import { EventMapper } from './event-mapper.js';
import { StateTransitions } from './transition-coordinator.js';
import { NotesAPI } from '../api-client.js';

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

    /**
     * Initialize the state machine
     */
    init() {
        this.state = 'idle';
        this.data = {};
    },

    /**
     * Handle a raw DOM event
     */
    async handleRawEvent(eventName, domEvent) {
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

        if (type === 'CREATE_TOP_NOTE') {
            console.log('📝 Creating new note...');
            const result = await NotesAPI.createNote();
            if (!result) {
                console.warn('❌ Failed to create note');
                return;
            }

            console.log('✅ Note created:', result);
            const newNote = document.querySelector(`[data-id="${result.id}"]`);
            if (newNote) {
                await this.transition('editing', {
                    nextNote: newNote,
                    cursorPosition: 'end'
                });
            }
            return;
        }

        try {
            // Determine new state based on event type
            const newState = this.getNewState(type);
            if (!newState || newState === this.state) {
                // Just update data if no state change
                this.data = { ...this.data, ...data };
                return;
            }

            // Execute state transition
            await this.transition(newState, data);
        } catch (error) {
            console.error('Event handling failed:', error);
        }
    },

    /**
     * Execute a state transition
     */
    async transition(newState, data = {}) {
        const oldState = this.state;
        
        console.log('🔄 State Transition:', {
            from: oldState,
            to: newState,
            data
        });

        try {
            // Execute transition and get new state data
            const newData = await StateTransitions.execute(oldState, newState, {
                ...this.data,
                ...data
            });

            // Update state
            this.state = newState;
            this.data = { ...this.data, ...newData };

            console.log('✨ New State:', {
                state: this.state,
                data: this.data
            });

            // Notify listeners
            this.notifyListeners(oldState, newState);

            return true;
        } catch (error) {
            console.error('❌ Transition failed:', error);
            return false;
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
            'START_SEARCH': 'searching',
            'STOP_SEARCH': 'idle',
            UPDATE_SEARCH: null  // null means stay in current state
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
                console.error('Listener error:', error);
            }
        });
    }
}; 