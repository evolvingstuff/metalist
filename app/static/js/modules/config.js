// Toggle the notes API base here to switch between v1 and v2
const API_BASE = '/api2'; // change to '/api' to switch back to v1
const API_NOTES_BASE = `${API_BASE}/notes`;
const API_AUTH_BASE = `${API_BASE}/auth`;

export const CONFIG = {
    API: {
        NOTES: {
            CREATE: `${API_NOTES_BASE}/new`,
            CREATE_SIBLING: (noteId) => `${API_NOTES_BASE}/new-sibling/${noteId}`,
            CREATE_CHILD: (noteId) => `${API_NOTES_BASE}/new-child/${noteId}`,
            UPDATE: (noteId) => `${API_NOTES_BASE}/${noteId}`,
            SAVE: (noteId) => `${API_NOTES_BASE}/${noteId}/save`,
            MOVE: (noteId) => `${API_NOTES_BASE}/${noteId}/move`,
            COLLAPSE: (noteId) => `${API_NOTES_BASE}/${noteId}/collapse`,
            EXPAND: (noteId) => `${API_NOTES_BASE}/${noteId}/expand`,
            SET_COLLAPSED_BULK: `${API_NOTES_BASE}/set-collapsed-bulk`,
            SET_COLLAPSED_IN_CONTEXT: `${API_NOTES_BASE}/set-collapsed-in-context`,
            DELETE: (noteId) => `${API_NOTES_BASE}/${noteId}`,
            COPY: (noteId) => `${API_NOTES_BASE}/${noteId}/copy`,
            EXPORT_HTML: (noteId) => `${API_NOTES_BASE}/${noteId}/export-html`,
            PASTE_SIBLING: (targetNoteId) => `${API_NOTES_BASE}/paste-sibling/${targetNoteId}`,
            PASTE_CHILD: (targetNoteId) => `${API_NOTES_BASE}/paste-child/${targetNoteId}`,
            UNDO: `${API_NOTES_BASE}/undo`,
            REDO: `${API_NOTES_BASE}/redo`,
            EDIT_MODE: `${API_NOTES_BASE}/edit-mode`,
            VIEW: `${API_NOTES_BASE}/view`,
            TAB_STATE: `${API_NOTES_BASE}/tab-state`,
            TAB_STATE_NEW_TAB: `${API_NOTES_BASE}/tab-state/new-tab`,
            TAB_STATE_DELETE_TAB: `${API_NOTES_BASE}/tab-state/delete-tab`,
            SEARCH_SUGGESTIONS: `${API_NOTES_BASE}/search-suggestions`,
        },
        AUTH: {
            STATUS: `${API_AUTH_BASE}/status`,
            LOGIN: `${API_AUTH_BASE}/login`,
            LOGOUT: `${API_AUTH_BASE}/logout`,
            SESSION: `${API_AUTH_BASE}/session`,
            SESSIONS: `${API_AUTH_BASE}/sessions`,
            SETTINGS: {
                PASSWORD: {
                    CREATE: `${API_AUTH_BASE}/settings/password/create`,
                    CHANGE: `${API_AUTH_BASE}/settings/password/change`,
                    REMOVE: `${API_AUTH_BASE}/settings/password/remove`
                }
            }
        },
        MEMORY: {
            BASE: `${API_BASE}/memory`
        }
    },

    CLASSES: {
        NOTE: 'note',
        NOTE_CONTENT: 'note-content',
        EDITING: 'editing',
        CARET_HIDDEN: 'caret-hidden',
        SEARCH_INPUT: 'search-input',
        SEARCH_RESULTS: 'search-results',
        LOADING: 'loading'
    },

    SYNC: {
        POLL_INTERVAL_MS: 5_000,
    },

    DEBUG: {
        LOG_API_CALLS: true,
        LOG_STATE_CHANGES: true
    },
    
    LOADING: {
        
        ARTIFICIAL_DELAY: 0,

        SPINNER_DELAY: 500,

        BLOCK_ACTIONS: true
    },
    
    SEARCH: {
        DEBOUNCE_MS: 300  // Delay before executing search after typing stops
    },
    
    TRANSITIONS: {
        ENABLE_INITIAL_FADE: true,  // Enable fade effect on initial page load only
        FADE_DURATION_MS: 150       // Duration of fade effect in milliseconds
    },
    
    EDITOR: {
        DEFAULT_CURSOR_POSITION: 'END'    // Where to place cursor when entering edit mode ('START' or 'END')
    },

    TABS: {
        MAX_TABS: 10,
        CREATE_AND_SWITCH: true,
    },
};
