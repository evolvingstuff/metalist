/**
 * Application-wide configuration settings
 */
export const CONFIG = {
    // Timeouts
    INACTIVITY_TIMEOUT: 10000,  // Time before auto-save (ms)
    
    // API Endpoints
    API: {
        NOTES: {
            CREATE: '/api/notes/new',
            CREATE_DROP: '/api/notes/new-drop',
            CREATE_SIBLING: (noteId) => `/api/notes/new-sibling/${noteId}`,
            CREATE_CHILD: (noteId) => `/api/notes/new-child/${noteId}`,
            UPDATE: (noteId) => `/api/notes/${noteId}`,
            SAVE: (noteId) => `/api/notes/${noteId}/save`,
            MOVE: (noteId) => `/api/notes/${noteId}/move`,
            DELETE: (noteId) => `/api/notes/${noteId}`,
            UNDO: '/api/notes/undo',
            REDO: '/api/notes/redo',
            FRAGMENT: '/api/notes/fragment'
        }
    },
    
    // CSS Classes
    CLASSES: {
        NOTE: 'note',
        NOTE_CONTENT: 'note-content',
        EDITING: 'editing',
        DRAGGING: 'dragging',
        DRAG_OVER: 'drag-over',
        DRAG_BEFORE: 'drag-before',
        DRAG_AFTER: 'drag-after',
        DRAG_INSIDE: 'drag-inside',
        DRAG_TRASH: 'drag-trash'
    },
    
    // Feature flags
    FEATURES: {
        USE_STATE_MACHINE: true,      // Enable state machine
        USE_INACTIVITY_TIMEOUT: false // Enable inactivity timeout
    },
    
    // Debug flags
    DEBUG: {
        LOG_API_CALLS: true,
        LOG_STATE_CHANGES: true,
        LOG_STATE_MACHINE: true
    }
};