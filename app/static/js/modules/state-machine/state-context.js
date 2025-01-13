/**
 * State Context
 * 
 * Single source of truth for state machine context.
 * NO MERCY validation - all data must be perfect!
 */
export class StateContext {
    constructor() {
        // Initialize with null values
        this.type = null;            // Event type
        this.currentState = null;    // Current state machine state
        this.targetState = null;     // Target state for transitions
        this.noteId = null;          // ID of current note
        this.cursorOffset = null;    // Cursor offset from start of note
        this.coordinates = null;      // Click coordinates for cursor positioning
        this.activityMonitor = null; // Activity tracking
        this.lastSavedContent = null;// Content snapshot for change detection
        this.key = null;             // Key pressed (for keyboard events)
        this.metaKey = false;        // Meta key pressed
        this.shiftKey = false;       // Shift key pressed
        this.query = null;           // Search query

        // Bind methods to instance
        this.setType = this.setType.bind(this);
        this.setCurrentState = this.setCurrentState.bind(this);
        this.setTargetState = this.setTargetState.bind(this);
        this.setNoteId = this.setNoteId.bind(this);
        this.setCursorOffset = this.setCursorOffset.bind(this);
        this.setCoordinates = this.setCoordinates.bind(this);
        this.setActivityMonitor = this.setActivityMonitor.bind(this);
        this.setLastSavedContent = this.setLastSavedContent.bind(this);
        this.setQuery = this.setQuery.bind(this);
        this.setKey = this.setKey.bind(this);
        this.setMetaKey = this.setMetaKey.bind(this);
        this.setShiftKey = this.setShiftKey.bind(this);
        this.resetType = this.resetType.bind(this);
        this.resetCurrentState = this.resetCurrentState.bind(this);
        this.resetTargetState = this.resetTargetState.bind(this);
        this.resetNoteId = this.resetNoteId.bind(this);
        this.resetCursorOffset = this.resetCursorOffset.bind(this);
        this.resetCoordinates = this.resetCoordinates.bind(this);
        this.resetActivityMonitor = this.resetActivityMonitor.bind(this);
        this.resetLastSavedContent = this.resetLastSavedContent.bind(this);
        this.resetQuery = this.resetQuery.bind(this);
        this.resetKey = this.resetKey.bind(this);
        this.resetMetaKey = this.resetMetaKey.bind(this);
        this.resetShiftKey = this.resetShiftKey.bind(this);
    }

    /**
     * Set event type with validation
     */
    setType(type) {
        if (!type) {
            throw new Error('Event type is required');
        }
        if (typeof type !== 'string') {
            throw new Error('Event type must be a string');
        }
        this.type = type;
        return this;
    }

    /**
     * Get event type
     * @throws {Error} If type is not set
     */
    getType() {
        if (!this.type) {
            throw new Error('Event type not set');
        }
        return this.type;
    }

    /**
     * Reset event type
     */
    resetType() {
        this.type = null;
        return this;
    }

    /**
     * Set current state with validation
     */
    setCurrentState(state) {
        if (!state) {
            throw new Error('Current state is required');
        }
        if (typeof state !== 'string') {
            throw new Error('Current state must be a string');
        }
        this.currentState = state;
        return this;
    }

    /**
     * Get current state
     * @throws {Error} If currentState is not set
     */
    getCurrentState() {
        if (!this.currentState) {
            throw new Error('Current state not set');
        }
        return this.currentState;
    }

    /**
     * Reset current state
     */
    resetCurrentState() {
        this.currentState = null;
        return this;
    }

    /**
     * Set target state with validation
     */
    setTargetState(state) {
        if (!state) {
            throw new Error('Target state is required');
        }
        if (typeof state !== 'string') {
            throw new Error('Target state must be a string');
        }
        this.targetState = state;
        return this;
    }

    /**
     * Get target state
     * @throws {Error} If targetState is not set
     */
    getTargetState() {
        // target state CAN be null; indicates no transition
        return this.targetState;
    }

    /**
     * Reset target state
     */
    resetTargetState() {
        this.targetState = null;
        return this;
    }

    /**
     * Set note ID with validation
     */
    setNoteId(noteId) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        if (typeof noteId !== 'string') {
            throw new Error('Note ID must be a string');
        }
        this.noteId = noteId;
        return this;
    }

    /**
     * Get note ID
     * @throws {Error} If noteId is not set
     */
    getNoteId() {
        if (!this.noteId) {
            throw new Error('Note ID not set');
        }
        return this.noteId;
    }

    /**
     * Reset note ID
     */
    resetNoteId() {
        this.noteId = null;
        return this;
    }

    /**
     * Get cursor offset
     * @returns {number|null} Cursor offset from start of note
     * @throws {Error} If cursorOffset is not set
     */
    getCursorOffset() {
        if (this.cursorOffset === undefined || this.cursorOffset === null) {
            throw new Error('Cursor offset not set');
        }
        return this.cursorOffset;
    }

    /**
     * Set cursor offset with validation
     */
    setCursorOffset(offset) {
        if (typeof offset !== 'number' || offset < 0) {
            throw new Error(`Invalid cursor offset: ${offset}`);
        }
        this.cursorOffset = offset;
        return this;
    }

    /**
     * Reset cursor offset
     */
    resetCursorOffset() {
        this.cursorOffset = null;
        return this;
    }

    /**
     * Set click coordinates with validation
     */
    setCoordinates(coordinates) {
        if (!coordinates) {
            throw new Error('Coordinates are required');
        }
        if (typeof coordinates.x !== 'number' || typeof coordinates.y !== 'number') {
            throw new Error('Invalid coordinates');
        }
        this.coordinates = coordinates;
        return this;
    }

    /**
     * Get coordinates
     * @throws {Error} If coordinates is not set
     */
    getCoordinates() {
        if (!this.coordinates) {
            throw new Error('Coordinates not set');
        }
        return this.coordinates;
    }

    /**
     * Reset coordinates
     */
    resetCoordinates() {
        this.coordinates = null;
        return this;
    }

    /**
     * Set activity monitor with validation
     */
    setActivityMonitor(monitor) {
        if (!monitor) {
            throw new Error('Activity monitor is required');
        }
        if (typeof monitor.startMonitoring !== 'function') {
            throw new Error('Invalid activity monitor: missing startMonitoring');
        }
        if (typeof monitor.stopMonitoring !== 'function') {
            throw new Error('Invalid activity monitor: missing stopMonitoring');
        }
        this.activityMonitor = monitor;
        return this;
    }

    /**
     * Get activity monitor
     * @throws {Error} If activityMonitor is not set
     */
    getActivityMonitor() {
        if (!this.activityMonitor) {
            throw new Error('Activity monitor not set');
        }
        return this.activityMonitor;
    }

    /**
     * Reset activity monitor
     */
    resetActivityMonitor() {
        this.activityMonitor = null;
        return this;
    }

    /**
     * Set last saved content with validation
     */
    setLastSavedContent(content) {
        if (content === undefined || content === null) {
            throw new Error('Content is required');
        }
        this.lastSavedContent = content;
        return this;
    }

    /**
     * Get last saved content
     * @throws {Error} If lastSavedContent is not set
     */
    getLastSavedContent() {
        if (!this.lastSavedContent) {
            throw new Error('Last saved content not set');
        }
        return this.lastSavedContent;
    }

    /**
     * Reset last saved content
     */
    resetLastSavedContent() {
        this.lastSavedContent = null;
        return this;
    }

    /**
     * Set search query with validation
     */
    setQuery(query) {
        if (query !== null && typeof query !== 'string') {
            throw new Error('Search query must be a string or null');
        }
        this.query = query;
        return this;
    }

    /**
     * Get search query
     * @throws {Error} If query is not set
     */
    getQuery() {
        if (this.query === undefined || this.query === null) {
            throw new Error('Search query not set');
        }
        return this.query;
    }

    /**
     * Reset search query
     */
    resetQuery() {
        this.query = null;
        return this;
    }

    /**
     * Set keyboard key with validation
     */
    setKey(key) {
        if (!key) {
            throw new Error('Key is required');
        }
        if (typeof key !== 'string') {
            throw new Error('Key must be a string');
        }
        this.key = key;
        return this;
    }

    /**
     * Get key
     * @throws {Error} If key is not set
     */
    getKey() {
        if (!this.key) {
            throw new Error('Key not set');
        }
        return this.key;
    }

    /**
     * Reset key
     */
    resetKey() {
        this.key = null;
        return this;
    }

    /**
     * Set meta key state
     */
    setMetaKey(metaKey) {
        this.metaKey = Boolean(metaKey);
        return this;
    }

    /**
     * Get meta key state
     */
    getMetaKey() {
        return !!this.metaKey;  // Convert to boolean
    }

    /**
     * Reset meta key state
     */
    resetMetaKey() {
        this.metaKey = false;
        return this;
    }

    /**
     * Set shift key state
     */
    setShiftKey(shiftKey) {
        this.shiftKey = Boolean(shiftKey);
        return this;
    }

    /**
     * Get shift key state
     */
    getShiftKey() {
        return !!this.shiftKey;  // Convert to boolean
    }

    /**
     * Reset shift key state
     */
    resetShiftKey() {
        this.shiftKey = false;
        return this;
    }

    /**
     * Validate entire context
     */
    validate() {
        if (!this.type) {
            throw new Error('Event type not set');
        }
        if (!this.currentState) {
            throw new Error('Current state not set');
        }
        if (!this.noteId) {
            throw new Error('Note ID not set');
        }
        // Coordinates optional - only needed for click positioning
        // Activity monitor optional - only needed for auto-save
        // Last saved content optional - only needed for change detection
        return this;
    }

    /**
     * Create context from raw event data
     */
    static fromRawEvent(type, noteId, cursorOffset, coordinates) {
        const context = new StateContext();

        if (!type) {
            throw new Error('Raw event missing type');
        }
        context.setType(type);

        if (!noteId) {
            throw new Error('Raw event missing noteId');
        }
        context.setNoteId(noteId);

        if (cursorOffset !== undefined) {
            context.setCursorOffset(cursorOffset);
        }

        if (coordinates) {
            context.setCoordinates(coordinates);
        }

        return context;
    }

    /**
     * Create context from state data
     */
    static fromStateData(data) {
        const context = new StateContext();

        if (!data) {
            throw new Error('Missing state data');
        }

        if (data.type) {
            context.setType(data.type);
        }

        if (data.currentState) {
            context.setCurrentState(data.currentState);
        }

        if (data.targetState) {
            context.setTargetState(data.targetState);
        }

        if (data.noteId) {
            context.setNoteId(data.noteId);
        }

        if (data.cursorOffset !== undefined) {
            context.setCursorOffset(data.cursorOffset);
        }

        if (data.coordinates) {
            context.setCoordinates(data.coordinates);
        }

        if (data.activityMonitor) {
            context.setActivityMonitor(data.activityMonitor);
        }

        if (data.lastSavedContent) {
            context.setLastSavedContent(data.lastSavedContent);
        }

        if (data.query) {
            context.setQuery(data.query);
        }

        if (data.key) {
            context.setKey(data.key);
        }

        if (data.metaKey !== undefined) {
            context.setMetaKey(data.metaKey);
        }

        if (data.shiftKey !== undefined) {
            context.setShiftKey(data.shiftKey);
        }

        return context;
    }
}