// Toggle the notes API base here to switch between v1 and v2
const API_BASE = '/api2'; // change to '/api' to switch back to v1
const API_NOTES_BASE = `${API_BASE}/notes`;
const API_AUTH_BASE = `${API_BASE}/auth`;
const API_FILES_BASE = `${API_BASE}/files`;
const RUNTIME_FLAGS = globalThis.__METALIST_RUNTIME__;
const STARTUP_ANIMATION_ENABLED = Boolean(
    RUNTIME_FLAGS &&
    typeof RUNTIME_FLAGS === 'object' &&
    RUNTIME_FLAGS.startupAnimationEnabled === true,
);

export const CONFIG = {
    API: {
        NOTES: {
            CREATE: `${API_NOTES_BASE}/new`,
            CREATE_SIBLING: (noteId) => `${API_NOTES_BASE}/new-sibling/${noteId}`,
            CREATE_CHILD: (noteId) => `${API_NOTES_BASE}/new-child/${noteId}`,
            UPDATE: (noteId) => `${API_NOTES_BASE}/${noteId}`,
            SAVE: (noteId) => `${API_NOTES_BASE}/${noteId}/save`,
            TOGGLE_TODO: (noteId) => `${API_NOTES_BASE}/${noteId}/toggle-todo`,
            RUN_SHELL: (noteId) => `${API_NOTES_BASE}/${noteId}/run-shell`,
            RUN_SHELL_STATUS: (noteId, runId) => `${API_NOTES_BASE}/${noteId}/run-shell/${runId}`,
            RUN_SHELL_INPUT: (noteId, runId) => `${API_NOTES_BASE}/${noteId}/run-shell/${runId}/input`,
            JOIN_NEXT: (noteId) => `${API_NOTES_BASE}/${noteId}/join-next`,
            REFERENCE_MODE: (noteId) => `${API_NOTES_BASE}/${noteId}/reference-mode`,
            MOVE: (noteId) => `${API_NOTES_BASE}/${noteId}/move`,
            MOVE_TO_TOP: (noteId) => `${API_NOTES_BASE}/${noteId}/move-to-top`,
            PRIORITIZE: `${API_NOTES_BASE}/prioritize`,
            INDENT: (noteId) => `${API_NOTES_BASE}/${noteId}/indent`,
            OUTDENT: (noteId) => `${API_NOTES_BASE}/${noteId}/outdent`,
            COLLAPSE: (noteId) => `${API_NOTES_BASE}/${noteId}/collapse`,
            EXPAND: (noteId) => `${API_NOTES_BASE}/${noteId}/expand`,
            SET_COLLAPSED_BULK: `${API_NOTES_BASE}/set-collapsed-bulk`,
            SET_COLLAPSED_IN_CONTEXT: `${API_NOTES_BASE}/set-collapsed-in-context`,
            DELETE: (noteId) => `${API_NOTES_BASE}/${noteId}`,
            COPY: (noteId) => `${API_NOTES_BASE}/${noteId}/copy`,
            EXPORT_HTML: `${API_NOTES_BASE}/export-html`,
            PASTE_SIBLING: (targetNoteId) => `${API_NOTES_BASE}/paste-sibling/${targetNoteId}`,
            PASTE_CHILD: (targetNoteId) => `${API_NOTES_BASE}/paste-child/${targetNoteId}`,
            UNDO: `${API_NOTES_BASE}/undo`,
            REDO: `${API_NOTES_BASE}/redo`,
            EDIT_MODE: `${API_NOTES_BASE}/edit-mode`,
            VIEW: `${API_NOTES_BASE}/view`,
            TAB_STATE: `${API_NOTES_BASE}/tab-state`,
            TAB_STATE_NEW_TAB: `${API_NOTES_BASE}/tab-state/new-tab`,
            TAB_STATE_DELETE_TAB: `${API_NOTES_BASE}/tab-state/delete-tab`,
            TAB_STATE_SORT_MODE: `${API_NOTES_BASE}/tab-state/sort-mode`,
            SEARCH_INTERACTIONS: `${API_NOTES_BASE}/search-interactions`,
            SEARCH_SUGGESTIONS: `${API_NOTES_BASE}/search-suggestions`,
            PRIORITIZE_TAG_SUGGESTIONS: `${API_NOTES_BASE}/prioritize-tag-suggestions`,
            TAG_SUGGESTIONS: `${API_NOTES_BASE}/tag-suggestions`,
            BACKLINKS: (noteId) => `${API_NOTES_BASE}/${noteId}/backlinks`,
        },
        AUTH: {
            STATUS: `${API_AUTH_BASE}/status`,
            LOGIN: `${API_AUTH_BASE}/login`,
            LOGOUT: `${API_AUTH_BASE}/logout`,
            SESSION: `${API_AUTH_BASE}/session`,
            SESSIONS: `${API_AUTH_BASE}/sessions`,
            HYDRATE: `${API_AUTH_BASE}/hydrate`,
            HYDRATION_STATUS: `${API_AUTH_BASE}/hydration-status`,
            BACKUP: {
                CREATE: `${API_AUTH_BASE}/backup/create`,
                LIST: `${API_AUTH_BASE}/backup/list`,
                DELETE_OLDEST: `${API_AUTH_BASE}/backup/delete-oldest`,
                RESTORE: `${API_AUTH_BASE}/backup/restore`,
            },
            NAMESPACES: {
                LIST: `${API_AUTH_BASE}/namespaces`,
                OPEN: `${API_AUTH_BASE}/namespaces/open`,
                DELETE_CURRENT: `${API_AUTH_BASE}/namespaces/delete-current`,
                DELETE_JOB_STATUS: (jobId) => `${API_AUTH_BASE}/namespaces/delete-jobs/${jobId}`,
            },
            SETTINGS: {
                PASSWORD: {
                    CREATE: `${API_AUTH_BASE}/settings/password/create`,
                    CHANGE: `${API_AUTH_BASE}/settings/password/change`,
                    REMOVE: `${API_AUTH_BASE}/settings/password/remove`
                }
            }
        },
        BACKUP: {
            SETTINGS: `${API_BASE}/backup/settings`,
            RUN: `${API_BASE}/backup/run`,
            LIST: `${API_BASE}/backup/list`,
            RESTORE: `${API_BASE}/backup/restore`,
            GOOGLE_DRIVE: {
                CONNECT_START: `${API_BASE}/backup/google-drive/connect/start`,
                CONNECT_STATUS: (requestId) => `${API_BASE}/backup/google-drive/connect/status?request_id=${encodeURIComponent(requestId)}`,
                VALIDATE: `${API_BASE}/backup/google-drive/validate`,
                DISCONNECT: `${API_BASE}/backup/google-drive/disconnect`,
            },
        },
        MEMORY: {
            BASE: `${API_BASE}/memory`
        },
        FILES: {
            UPLOAD: `${API_FILES_BASE}/upload`,
            DOWNLOAD: (fileId) => `${API_FILES_BASE}/${fileId}/download`,
            TRIM_UNUSED: `${API_FILES_BASE}/trim-unused`,
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

    PASTE: {
        MAX_DATA_IMAGE_BYTES: 10_485_760,
        EMBED_TARGET_IMAGE_BYTES: 350_000,
        EMBED_MAX_DIMENSION_PX: 1_600,
        MAX_CLIPBOARD_IMAGE_BYTES: 31_457_280,
    },

    TABS: {
        MAX_TABS: 1000,
        CREATE_AND_SWITCH: true,
    },

    REFERENCE_NAVIGATION: {
        CLOSE_REF_TAB_ON_BACK: true,
    },

    BACKUP: {
        RETENTION_PROMPT_THRESHOLD: 25,
        RETENTION_SUGGESTED_KEEP_COUNT: 3,
    },

    STARTUP: {
        ENABLE_LOGIN_INTRO: STARTUP_ANIMATION_ENABLED,
    },
};
