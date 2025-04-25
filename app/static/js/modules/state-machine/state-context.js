export class StateContext {
    constructor() {
                                
        this.type = null;            
        this.currentState = null;    
        this.targetState = null;     
        this.noteId = null;          
        this.targetNoteId = null;    
        this.cursorOffset = null;    
        this.coordinates = null;      
        this.activityMonitor = null; 
        this.lastSavedContent = null;
        this.key = null;             
        this.metaKey = false;        
        this.shiftKey = false;       
        this.query = null;           
        this.effects_exit = [];      
        this.effects_transition = []; 
        this.phase = null;           

        this.setType = this.setType.bind(this);
        this.setCurrentState = this.setCurrentState.bind(this);
        this.setTargetState = this.setTargetState.bind(this);
        this.setNoteId = this.setNoteId.bind(this);
        this.setTargetNoteId = this.setTargetNoteId.bind(this);
        this.setCursorOffset = this.setCursorOffset.bind(this);
        this.setCoordinates = this.setCoordinates.bind(this);
        this.setActivityMonitor = this.setActivityMonitor.bind(this);
        this.setLastSavedContent = this.setLastSavedContent.bind(this);
        this.setQuery = this.setQuery.bind(this);
        this.setKey = this.setKey.bind(this);
        this.setMetaKey = this.setMetaKey.bind(this);
        this.setShiftKey = this.setShiftKey.bind(this);
        this.addEffect = this.addEffect.bind(this);
        this.resetEffects = this.resetEffects.bind(this);
        this.resetType = this.resetType.bind(this);
        this.resetCurrentState = this.resetCurrentState.bind(this);
        this.resetTargetState = this.resetTargetState.bind(this);
        this.resetNoteId = this.resetNoteId.bind(this);
        this.resetTargetNoteId = this.resetTargetNoteId.bind(this);
        this.resetCursorOffset = this.resetCursorOffset.bind(this);
        this.resetCoordinates = this.resetCoordinates.bind(this);
        this.resetActivityMonitor = this.resetActivityMonitor.bind(this);
        this.resetLastSavedContent = this.resetLastSavedContent.bind(this);
        this.resetQuery = this.resetQuery.bind(this);
        this.resetKey = this.resetKey.bind(this);
        this.resetMetaKey = this.resetMetaKey.bind(this);
        this.resetShiftKey = this.resetShiftKey.bind(this);
        this.getPhase = this.getPhase.bind(this);
        this.setPhase = this.setPhase.bind(this);
        this.validatePhase = this.validatePhase.bind(this);
    }

    setType(type) {
        this.validatePhase(['event']);  
        if (!type) {
            throw new Error('Event type is required');
        }
        if (typeof type !== 'string') {
            throw new Error('Event type must be a string');
        }
        this.type = type;
        return this;
    }

    getType() {
        this.validatePhase(['event', 'effects']);  
        if (!this.type) {
            throw new Error('Event type not set');
        }
        return this.type;
    }

    resetType() {
        this.type = null;
        return this;
    }

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

    getCurrentState() {
        this.validatePhase(['event', 'exiting', 'effects', 'transition', 'render', 'entering']);  
        if (!this.currentState) {
            throw new Error('Current state not set');
        }
        return this.currentState;
    }

    resetCurrentState() {
        this.currentState = null;
        return this;
    }

    setTargetState(state) {
        this.validatePhase(['event', 'effects']);  
        if (!state) {
            throw new Error('Target state is required');
        }
        if (typeof state !== 'string') {
            throw new Error('Target state must be a string');
        }
        this.targetState = state;
        return this;
    }

    getTargetState() {
        this.validatePhase(['event', 'effects', 'transition', 'entering']);  
                                
        return this.targetState;
    }

    resetTargetState() {
        this.targetState = null;
        return this;
    }

    setNoteId(noteId) {
        this.validatePhase(['transition']);  
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        if (typeof noteId !== 'string') {
            throw new Error('Note ID must be a string');
        }
        this.noteId = noteId;
        return this;
    }

    getNoteId() {
        this.validatePhase(['event', 'exiting', 'effects', 'transition', 'render', 'entering']);  
        return this.noteId;
    }

    resetNoteId() {
        this.noteId = null;
        return this;
    }

    setTargetNoteId(targetNoteId) {
        this.validatePhase(['event', 'effects']);  
        if (!targetNoteId) {
            throw new Error('Target note ID is required');
        }
        if (typeof targetNoteId !== 'string') {
            throw new Error('Target note ID must be a string');
        }
        this.targetNoteId = targetNoteId;
        return this;
    }

    getTargetNoteId() {
        this.validatePhase(['event', 'effects', 'transition']);  
        return this.targetNoteId;
    }

    resetTargetNoteId() {
        this.targetNoteId = null;
        return this;
    }

    getCursorOffset() {
        if (this.cursorOffset === undefined || this.cursorOffset === null) {
            throw new Error('Cursor offset not set');
        }
        return this.cursorOffset;
    }

    setCursorOffset(offset) {
        if (typeof offset !== 'number' || offset < 0) {
            throw new Error(`Invalid cursor offset: ${offset}`);
        }
        this.cursorOffset = offset;
        return this;
    }

    resetCursorOffset() {
        this.cursorOffset = null;
        return this;
    }

    setCoordinates(coordinates) {
        this.validatePhase(['event']);  
        if (!coordinates || typeof coordinates !== 'object') {
            throw new Error('Coordinates must be an object');
        }
        if (typeof coordinates.x !== 'number' || typeof coordinates.y !== 'number') {
            throw new Error('Coordinates must have numeric x and y values');
        }
        this.coordinates = coordinates;
        return this;
    }

    getCoordinates() {
        return this.coordinates;
    }

    resetCoordinates() {
        this.coordinates = null;
        return this;
    }

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

    getActivityMonitor() {
        if (!this.activityMonitor) {
            throw new Error('Activity monitor not set');
        }
        return this.activityMonitor;
    }

    resetActivityMonitor() {
        this.activityMonitor = null;
        return this;
    }

    setLastSavedContent(content) {
        if (content === undefined || content === null) {
            throw new Error('Content is required');
        }
        this.lastSavedContent = content;
        return this;
    }

    getLastSavedContent() {
        this.validatePhase(['event', 'exiting', 'effects']);  
        if (this.lastSavedContent === null || this.lastSavedContent === undefined) {
            throw new Error('Last saved content not set');
        }
        return this.lastSavedContent;
    }

    resetLastSavedContent() {
        this.lastSavedContent = null;
        return this;
    }

    setQuery(query) {
        this.validatePhase(['event']);  
        if (typeof query !== 'string') {
            throw new Error('Query must be a string');
        }
        this.query = query;
        return this;
    }

    getQuery() {
        if (this.query === undefined || this.query === null) {
            throw new Error('Search query not set');
        }
        return this.query;
    }

    resetQuery() {
        this.query = null;
        return this;
    }

    setKey(key) {
        this.validatePhase(['event']);  
        if (!key) {
            throw new Error('Key is required');
        }
        if (typeof key !== 'string') {
            throw new Error('Key must be a string');
        }
        this.key = key;
        return this;
    }

    getKey() {
        if (!this.key) {
            throw new Error('Key not set');
        }
        return this.key;
    }

    resetKey() {
        this.key = null;
        return this;
    }

    setMetaKey(metaKey) {
        this.validatePhase(['event']);  
        this.metaKey = Boolean(metaKey);
        return this;
    }

    getMetaKey() {
        return !!this.metaKey;  
    }

    resetMetaKey() {
        this.metaKey = false;
        return this;
    }

    setShiftKey(shiftKey) {
        this.validatePhase(['event']);  
        this.shiftKey = Boolean(shiftKey);
        return this;
    }

    getShiftKey() {
        return !!this.shiftKey;  
    }

    resetShiftKey() {
        this.shiftKey = false;
        return this;
    }

    addEffect(effect) {
        if (!effect) {
            throw new Error('Effect is required');
        }
                                
        if (this.phase === 'exiting') {
            this.effects_exit.push(effect);
        } else {
            this.effects_transition.push(effect);
        }
        return this;
    }

    resetEffects() {
        this.effects_exit = [];
        this.effects_transition = [];
        return this;
    }

    getEffects() {
        this.validatePhase(['event', 'effects']);  
        return [...this.effects_exit, ...this.effects_transition];
    }

    getPhase() {
        return this.phase;
    }

    setPhase(phase) {
        const validPhases = ['event', 'exiting', 'effects', 'transition', 'render', 'entering'];
        if (!validPhases.includes(phase)) {
            throw new Error(`Invalid phase: ${phase}. Must be one of: ${validPhases.join(', ')}`);
        }
        console.log(`🔄 Phase: ${this.phase || 'null'} -> ${phase}`);
        this.phase = phase;
        return this;
    }

    validatePhase(allowedPhases) {
        if (!allowedPhases.includes(this.phase)) {
            throw new Error(`Invalid state access in phase ${this.phase}. Only allowed in: ${allowedPhases.join(', ')}`);
        }
    }

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

        return this;
    }

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
}