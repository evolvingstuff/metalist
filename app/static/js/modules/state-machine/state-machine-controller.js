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

export const States = {
    IDLE: 'idle',
    EDITING: 'editing',
    SEARCHING: 'searching'
};

export const StateMachine = {
                
    handlers: {
        idle: idleTransitions,
        editing: editingTransitions,
        searching: searchingTransitions
    },

    validTransitions: {
        idle: ['editing', 'searching'],
        editing: ['idle', 'editing', 'searching'],
        searching: ['idle', 'editing']
    },

    state: 'idle',
    currentStateContext: null,
    listeners: [],

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

    handleRawEvent(eventName, domEvent) {
                                
        if (!eventName) {
            throw new Error('Event name is required');
        }
        if (!domEvent) {
            throw new Error('DOM event is required');
        }

        this.currentStateContext.setPhase('event');

        this.currentStateContext
            .resetKey()
            .resetMetaKey()
            .resetShiftKey()
            .resetTargetState()
            .resetCoordinates()
            .resetType();

        const handlerMap = {
            'Click': () => RawEvents.handleClick(domEvent),
            'KeyDown': () => RawEvents.handleKeyDown(domEvent),
            'DragStart': () => RawEvents.handleDragStart(domEvent),
            'Input': () => RawEvents.handleInput(domEvent),
            'SearchInput': () => RawEvents.handleSearchInput(domEvent),
            'SearchBlur': () => RawEvents.handleSearchBlur(domEvent),
            'SearchFocus': () => RawEvents.handleSearchClick(domEvent),
            'ClickOutsideNote': () => RawEvents.handleClickOutsideNote(domEvent),
            'FragmentLoaded': () => RawEvents.handleFragmentLoaded(domEvent),
            'AddButtonClick': () => RawEvents.handleAddNoteClick(domEvent)
        };

        const handler = handlerMap[eventName];
        if (!handler) {
            throw new Error(`No handler for event: ${eventName}`);
        }

        handler();

        this.handleMappedEvent();
    },

    async handleMappedEvent() {
                                
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

        const eventType = this.currentStateContext.getType();
        if (!eventType) {
            throw new Error('Event type not set');
        }
        if (typeof eventType !== 'string') {
            throw new Error('Event type must be a string');
        }

        const stateHandler = this.handlers[this.state];
        if (!stateHandler) {
            throw new Error(`No handler for state: ${this.state}`);
        }
        if (typeof stateHandler.handleEvent !== 'function') {
            throw new Error(`Invalid handler for state: ${this.state}`);
        }

        await stateHandler.handleEvent();

        const targetState = this.currentStateContext.getTargetState();
        if (targetState) {
            console.log('🔄 Transitioning:', {
                from: this.state,
                to: targetState,
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

        const exitHandler = this.handlers[this.state];
        const enterHandler = this.handlers[targetState];

        console.log('🔄 State transition:', {
            from: this.state,
            to: targetState,
            context: this.currentStateContext
        });

        if (exitHandler?.exit) {
            this.currentStateContext.setPhase('exiting');
            await exitHandler.exit();
        }

        this.currentStateContext.setPhase('effects');
        const effects = this.currentStateContext.getEffects();
        console.log('🔄 Running effects:', effects.map(e => e.constructor.name));
        for (const effect of effects) {
            await effect.execute();
        }
        this.currentStateContext.resetEffects();

        const targetNoteId = this.currentStateContext.getTargetNoteId();

        this.currentStateContext.setPhase('transition');

        this.currentStateContext.resetNoteId();  
        this.currentStateContext.resetTargetNoteId();
        if (targetNoteId) {  
            this.currentStateContext.setNoteId(targetNoteId);
        }

        console.log('🔄 Updating fragment (state-machine-controller)');
        const html = await NotesAPI.getFragment(this.currentStateContext.getNoteId());
        if (!html) {
            throw new Error('Invalid fragment: missing HTML');
        }

        const notesContainer = document.getElementById('notes-container');
        if (!notesContainer) {
            throw new Error('Notes container not found');
        }
        if (typeof html !== 'string') {
            throw new Error('Invalid fragment HTML type');
        }

        notesContainer.innerHTML = html;
        console.log('✅ Fragment updated (state-machine-controller)');

        this.state = targetState;

        if (enterHandler?.enter) {
            this.currentStateContext.setPhase('entering');
            await enterHandler.enter();
        }

        this.currentStateContext.setPhase('event');

        this.currentStateContext.resetTargetState();

        this.notifyListeners();
    },

    resetOnNewEvent() {
                                
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