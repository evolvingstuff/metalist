/**
 * State Machine Controller
 * 
 * Manages application state transitions and side effects in a predictable way:
 * 
 * 1. Events flow through:
 *    raw event -> mapped event -> state handler -> (optional) transition
 * 
 * 2. State transitions:
 *    - Run exit handler for old state
 *    - Execute queued effects
 *    - Update fragment
 *    - Change state
 *    - Run enter handler for new state
 * 
 * 3. State Context:
 *    - Holds all state data (noteId, content, cursor position, etc.)
 *    - Validates data access
 *    - Queues effects for next transition
 * 
 * Example flow:
 * ```
 * // 1. Initialize
 * StateMachine.init();
 * 
 * // 2. Handle raw event
 * StateMachine.handleRawEvent({
 *   type: 'keydown',
 *   key: 'Enter'
 * });
 * 
 * // 3. State handler queues effects and sets target state
 * stateContext
 *   .queueEffect(new CreateNoteEffect())
 *   .setTargetState('editing');
 * 
 * // 4. Transition runs effects and handlers
 * await StateMachine.transition();
 * ```
 */

import { RawEvents } from './raw-events.js';
import { EventMapper } from './event-mapper.js';
import { NotesAPI } from '../api-client.js';
import { ActivityMonitor } from './activity-monitor.js';
import { editingTransitions } from './states/editing.js';
import { searchingTransitions } from './states/searching.js';
import { idleTransitions } from './states/idle.js';
import { StateContext } from './state-context.js';
import { DOMUtils } from '../dom-utils.js';
import { CONFIG } from '../config.js';

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
    // State handlers
    handlers: {
        idle: idleTransitions,
        editing: editingTransitions,
        searching: searchingTransitions
    },

    // Valid state transitions
    validTransitions: {
        idle: ['editing', 'searching'],
        editing: ['idle', 'editing', 'searching'],
        searching: ['idle', 'editing']
    },

    // State variables
    state: 'idle',
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
        const stateHandler = this.handlers[this.state];
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
        const exitHandler = this.handlers[this.state];
        const enterHandler = this.handlers[targetState];

        console.log('🔄 State transition:', {
            from: this.state,
            to: targetState,
            context: this.currentStateContext
        });

        // Run exit handler for current state - needs current noteId
        if (exitHandler?.exit) {
            await exitHandler.exit();
        }

        // Run all queued effects - needs current noteId
        const effects = this.currentStateContext.getEffects();
        console.log('🔄 Running effects:', effects.map(e => e.constructor.name));
        for (const effect of effects) {
            await effect.execute();
        }
        this.currentStateContext.resetEffects();

        // Cache the target note ID before any resets
        const targetNoteId = this.currentStateContext.getTargetNoteId();
        
        // NOW safe to reset and update IDs since exit and effects are done
        this.currentStateContext.resetNoteId();  // Always start fresh
        this.currentStateContext.resetTargetNoteId();
        if (targetNoteId) {  // Only set if we have a target
            this.currentStateContext.setNoteId(targetNoteId);
        }

        // Trigger fragment render with the new noteId
        console.log('🔄 Updating fragment (state-machine-controller)');
        const html = await NotesAPI.getFragment(this.currentStateContext.getNoteId());
        if (!html) {
            throw new Error('Invalid fragment: missing HTML');
        }

        // Update the notes container with new HTML
        const notesContainer = document.getElementById('notes-container');
        if (!notesContainer) {
            throw new Error('Notes container not found');
        }
        if (typeof html !== 'string') {
            throw new Error('Invalid fragment HTML type');
        }

        notesContainer.innerHTML = html;
        console.log('✅ Fragment updated (state-machine-controller)');

        // Update state
        this.state = targetState;

        // Run enter handler for new state
        if (enterHandler?.enter) {
            console.log('🔄 Running enter handler for:', targetState);
            await enterHandler.enter();
            console.log('✅ Enter handler complete');
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