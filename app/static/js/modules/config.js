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
        SEARCH_RESULTS: 'search-results'
    },

    DEBUG: {
        LOG_API_CALLS: true,
        LOG_STATE_CHANGES: true
    },

    SELECT_ON_UNDO_OR_REDO: true
};