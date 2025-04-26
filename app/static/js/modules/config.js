export const CONFIG = {
                
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
            PASTE_SIBLING: (sourceNoteId, targetNoteId) => `/api/notes/${sourceNoteId}/paste-sibling/${targetNoteId}`,
            PASTE_CHILD: (sourceNoteId, targetNoteId) => `/api/notes/${sourceNoteId}/paste-child/${targetNoteId}`,
            UNDO: '/api/notes/undo',
            REDO: '/api/notes/redo',
            FRAGMENT: '/api/notes/fragment'
        }
    },

    CLASSES: {
        NOTE: 'note',
        NOTE_CONTENT: 'note-content',
        EDITING: 'editing',
        SEARCH_INPUT: 'search-input',
        SEARCH_RESULTS: 'search-results',
        LOADING: 'loading'
    },

    DEBUG: {
        LOG_API_CALLS: true,
        LOG_STATE_CHANGES: true
    },
    
    LOADING: {
        // Artificial delay in milliseconds to simulate slow network (0 to disable)
        ARTIFICIAL_DELAY: 0,
        
        // Time in milliseconds before showing the loading cursor
        SPINNER_DELAY: 500,
        
        // Whether to block user actions while loading
        BLOCK_ACTIONS: true
    }
};