/**
 * State Context
 * 
 * Single source of truth for state machine context.
 * NO MERCY validation - all data must be perfect!
 */
export class StateContext {
    constructor() {
        // Initialize with null values
        this.noteId = null;          // ID of current note
        this.cursorOffset = null;    // Cursor offset from start of note
        this.coordinates = null;      // Click coordinates for cursor positioning
        this.activityMonitor = null; // Activity tracking
        this.lastSavedContent = null;// Content snapshot for change detection

        // Bind methods to instance
        this.setNoteId = this.setNoteId.bind(this);
        this.setCursorOffset = this.setCursorOffset.bind(this);
        this.setCoordinates = this.setCoordinates.bind(this);
        this.setActivityMonitor = this.setActivityMonitor.bind(this);
        this.setLastSavedContent = this.setLastSavedContent.bind(this);
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
     * Validate entire context
     */
    validate() {
        if (!this.noteId) {
            throw new Error('Context missing noteId');
        }
        if (this.cursorOffset === null) {
            throw new Error('Context missing cursorOffset');
        }
        // Coordinates optional - only needed for click positioning
        // Activity monitor optional - only needed for auto-save
        // Last saved content optional - only needed for change detection
        return this;
    }

    /**
     * Create context from raw event data
     */
    static fromRawEvent(noteId, cursorOffset, coordinates) {
        const context = new StateContext();

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

        return context;
    }
}