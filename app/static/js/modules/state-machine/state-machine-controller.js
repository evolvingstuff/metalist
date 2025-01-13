import { RawEvents } from './raw-events.js';
import { EventMapper } from './event-mapper.js';
import { StateTransitions } from './transition-coordinator.js';
import { NotesAPI } from '../api-client.js';
import { ActivityMonitor } from './activity-monitor.js';
import { StateContext } from './state-context.js';
import { DOMUtils } from '../dom-utils.js';
import { CONFIG } from '../config.js';

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

// Valid state machine events
export const Events = {
    KEY_DOWN: 'KEY_DOWN',
    NOTE_CONTENT_CLICKED: 'NOTE_CONTENT_CLICKED',
    NOTE_CONTENT_CHANGED: 'NOTE_CONTENT_CHANGED',
    CLICKED_OUTSIDE_NOTE: 'CLICKED_OUTSIDE_NOTE',
    SEARCH_FOCUSED: 'SEARCH_FOCUSED',
    FRAGMENT_LOADED: 'FRAGMENT_LOADED',
    NO_OP: 'NO_OP'
};

export const StateMachine = {
    // Current state and context
    state: States.IDLE,
    currentStateContext: null,
    listeners: [],

    // Activity monitoring
    startActivityMonitor() {
        if (CONFIG.FEATURES.USE_INACTIVITY_TIMEOUT) {
            const activityMonitor = new ActivityMonitor(this);
            this.currentStateContext.setActivityMonitor(activityMonitor);
            activityMonitor.startMonitoring();
        }
    },

    stopActivityMonitor() {
        if (CONFIG.FEATURES.USE_INACTIVITY_TIMEOUT) {
            const monitor = this.currentStateContext.getActivityMonitor();
            if (monitor) {
                monitor.stopMonitoring();
                this.currentStateContext.resetActivityMonitor();
            }
        }
    },

    init() {
        this.state = States.IDLE;
        this.currentStateContext = new StateContext();
        this.listeners = [];
        return this;
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

        // Clear event-specific state
        this.currentStateContext
            .resetKey()
            .resetMetaKey()
            .resetShiftKey()
            .resetTargetState()
            .resetCoordinates()
            .resetType();

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

        // Handle raw event
        handler();

        // Map and handle the event
        this.handleMappedEvent();
    },

    async handleMappedEvent() {
        // NO MERCY validation
        if (!this.currentStateContext || typeof this.currentStateContext !== 'object') {
            throw new Error('Invalid state context: not an object');
        }
        if (!(this.currentStateContext instanceof StateContext)) {
            throw new Error('Invalid state context: must be StateContext instance');
        }
        if (!this.state || typeof this.state !== 'string') {
            throw new Error('Invalid state machine state');
        }
        if (!Object.values(States).includes(this.state)) {
            throw new Error(`Invalid current state: ${this.state}`);
        }

        // Map the event using current state
        const eventType = this.currentStateContext.getType();
        if (!eventType) {
            throw new Error('Event type not set');
        }
        if (typeof eventType !== 'string') {
            throw new Error('Event type must be a string');
        }
        if (!this.isValidEvent(eventType)) {
            throw new Error(`Invalid event type: ${eventType}`);
        }

        // Let current state handle event
        const stateHandler = StateTransitions.handlers[this.state];
        if (!stateHandler) {
            throw new Error(`No handler for state: ${this.state}`);
        }
        if (typeof stateHandler.handleEvent !== 'function') {
            throw new Error(`Invalid handler for state: ${this.state}`);
        }

        // Handle event in current state
        await stateHandler.handleEvent();

        // Check if we need to transition
        const targetState = this.currentStateContext.getTargetState();
        if (targetState) {
            if (!Object.values(States).includes(targetState)) {
                throw new Error(`Invalid target state: ${targetState}`);
            }

            console.log('🔄 Transitioning due to event:', {
                from: this.state,
                to: targetState,
                event: eventType,
                noteId: this.currentStateContext.getNoteId()
            });

            await this.transition();
        } else {
            console.log('🎯 Handled by current state:', {
                state: this.state,
                event: eventType
            });
        }
    },

    async transition() {
        const targetState = this.currentStateContext.getTargetState();
        if (!targetState) {
            throw new Error('Target state not set');
        }

        // Get handlers for current and target states
        const exitHandler = StateTransitions.handlers[this.state];
        const enterHandler = StateTransitions.handlers[targetState];

        console.log('🔄 State transition:', {
            from: this.state,
            to: targetState,
            context: this.currentStateContext
        });

        // Run exit handler for current state
        if (exitHandler?.exit) {
            await exitHandler.exit();
        }

        // Update state
        this.state = targetState;

        // Run enter handler for new state
        if (enterHandler?.enter) {
            await enterHandler.enter();
        }

        // Reset target state
        this.currentStateContext.resetTargetState();

        // Notify listeners
        this.notifyListeners();
    },

    resetOnNewEvent() {
        // Clear event-specific state
        this.currentStateContext
            .resetKey()
            .resetMetaKey()
            .resetShiftKey()
            .resetTargetState()
            .resetCoordinates()
            .resetType();
    },

    addListener(callback) {
        this.listeners.push(callback);
    },

    notifyListeners() {
        this.listeners.forEach(callback => callback());
    }
};