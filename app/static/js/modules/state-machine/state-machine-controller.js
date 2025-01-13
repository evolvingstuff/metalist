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
 * 1. Raw event handling (DOM events → StateContext)
 * 2. Event mapping (StateContext → state machine events)
 * 3. State transitions (state changes with enter/exit hooks)
 * 
 * Flow:
 * DOM Event → StateContext → Mapped Event → State Transition → New State
 * 
 * Each stage:
 * 1. Raw Events:
 *    - Takes DOM event
 *    - Returns StateContext with event type and data
 * 
 * 2. Event Mapper:
 *    - Takes StateContext and current state
 *    - Returns state machine event with same or modified StateContext
 * 
 * 3. State Machine:
 *    - Takes state machine event
 *    - Handles state transitions using StateContext
 * 
 * @example
 * // Initialize
 * StateMachine.init();
 * 
 * // Handle DOM event
 * StateMachine.handleRawEvent('Click', domEvent);
 * 
 * // Direct state machine event
 * StateMachine.handleMappedEvent({
 *   type: 'START_EDITING',
 *   context: new StateContext()
 *     .setNoteId('note-1')
 *     .setContent('Note content')
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

    init() {
        this.state = States.IDLE;
        this.activityMonitor = new ActivityMonitor(this);  // Pass controller reference
        this.listeners = [];
    },

    isValidEvent(eventType) {
        return Object.values(Events).includes(eventType);
    },

    handleRawEvent(eventName, domEvent) {
        // NO MERCY - event validation
        if (!eventName) {
            throw new Error('Event name is required');
        }
        if (!domEvent) {
            throw new Error('DOM event is required');
        }

        // Map event names to handlers
        const handlerMap = {
            'Click': () => RawEvents.handleClick(domEvent),
            'KeyDown': () => RawEvents.handleKeyDown(domEvent),
            'DragStart': () => RawEvents.handleDragStart(domEvent),
            'Input': () => RawEvents.handleInput(domEvent),
            'SearchInput': () => RawEvents.handleSearchInput(domEvent),
            'SearchBlur': () => RawEvents.handleSearchBlur(domEvent),
            'SearchFocus': () => RawEvents.handleSearchClick(domEvent),
            'ClickOutsideNote': () => RawEvents.handleClickOutsideNote(domEvent),
            'FragmentLoaded': () => RawEvents.handleFragmentLoaded(domEvent)
        };

        const handler = handlerMap[eventName];
        if (!handler) {
            throw new Error(`No handler for event: ${eventName}`);
        }

        // Get raw event (StateContext)
        const stateContext = handler();

        // NO MERCY validation
        if (!stateContext) {
            throw new Error('Raw event handler returned null');
        }
        if (!(stateContext instanceof StateContext)) {
            throw new Error('Raw event must return StateContext');
        }

        // Map raw event to state machine event
        const mappedEvent = EventMapper.mapEvent(stateContext, this.state);
        if (!mappedEvent) {
            throw new Error('Event mapper returned null');
        }

        // Skip NO_OP events
        if (mappedEvent.getType() === Events.NO_OP) {
            console.log('Skipping NO_OP event');
            return;
        }

        // Handle mapped event
        return this.handleMappedEvent(mappedEvent);
    },

    async handleMappedEvent(stateContext) {
        // Validate state context
        if (!stateContext || typeof stateContext !== 'object') {
            throw new Error('Invalid state context: not an object');
        }
        if (!(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context: must be StateContext instance');
        }

        // Set current state
        stateContext.setCurrentState(this.state);

        const eventType = stateContext.getType();
        if (!eventType || typeof eventType !== 'string') {
            throw new Error('Invalid state context: missing or invalid type');
        }
        if (!this.isValidEvent(eventType)) {
            throw new Error(`Invalid event type: ${eventType}`);
        }

        console.log(' State Machine Event:', {
            type: eventType,
            currentState: stateContext.getCurrentState(),
            context: stateContext
        });

        // Set target state based on event type
        try {
            const targetState = this.getTargetState(eventType);
            stateContext.setTargetState(targetState);
            await this.transition(stateContext);
            return;
        } catch (error) {
            // Not a transition event, let current state handle it
            const stateHandler = StateTransitions.handlers[stateContext.getCurrentState()];
            if (!stateHandler) {
                throw new Error(`No handler for state: ${stateContext.getCurrentState()}`);
            }

            const result = await stateHandler.handleEvent(stateContext);
            if (!result) {
                throw new Error(`State ${stateContext.getCurrentState()} did not handle event ${eventType}`);
            }

            // Check if state handler requested a transition
            const newTargetState = result.getTargetState();
            if (newTargetState && newTargetState !== stateContext.getCurrentState()) {
                await this.transition(result);
            }
        }
    },

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

    async transition(stateContext) {
        // NO MERCY - validate context
        if (!stateContext || typeof stateContext !== 'object') {
            throw new Error('Invalid state context: not an object');
        }
        if (!(stateContext instanceof StateContext)) {
            throw new Error('Invalid state context: must be StateContext instance');
        }

        const targetState = stateContext.getTargetState();
        if (!targetState) {
            throw new Error('Target state is required');
        }
        if (!Object.values(States).includes(targetState)) {
            throw new Error(`Invalid target state: ${targetState}`);
        }

        // Add activity monitor to context if needed
        if (targetState === States.EDITING) {
            // Validate required fields for editing
            if (!stateContext.getNoteId()) {
                throw new Error('Cannot transition to editing without note ID');
            }
            if (stateContext.getLastSavedContent() === null) {
                throw new Error('Cannot transition to editing without last saved content');
            }
            stateContext.setActivityMonitor(this.activityMonitor);
        }

        // Get handlers
        const exitHandler = StateTransitions.handlers[stateContext.getCurrentState()];
        const enterHandler = StateTransitions.handlers[targetState];

        // Execute transition
        console.log('[TRANSITION] State transition:', {
            from: stateContext.getCurrentState(),
            to: targetState,
            context: stateContext
        });

        if (exitHandler?.exit) {
            await exitHandler.exit(stateContext);
        }

        // Update current state
        this.state = targetState;
        stateContext.setCurrentState(targetState);

        if (enterHandler?.enter) {
            await enterHandler.enter(stateContext);
        }

        // Notify listeners
        this.notifyListeners(stateContext);
    },

    addListener(callback) {
        this.listeners.push(callback);
    },

    notifyListeners(stateContext) {
        this.listeners.forEach(listener => {
            listener(stateContext);
        });
    }
};