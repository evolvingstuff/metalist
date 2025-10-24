import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { ModeContextInstance as ModeContext } from './mode-manager/mode-context.js';
import { ErrorHandler } from './error-handler.js';

export const NotesAPI = {
                
    async _apiCall(url, options = {}) {
        try {
            // Add sync context to request body for non-GET requests
            let requestBody = options.body;
            if (options.method && options.method !== 'GET') {
                const syncContext = {
                    clientId: ModeContext.clientId,
                    lastUpdateUUID: ModeContext.lastUpdateUUID
                };
                
                if (requestBody) {
                    // Merge sync context with existing body
                    const existingBody = JSON.parse(requestBody);
                    requestBody = JSON.stringify({
                        ...existingBody,
                        ...syncContext
                    });
                } else {
                    // Just send sync context
                    requestBody = JSON.stringify(syncContext);
                }
            }
                                                
            console.log(' [API] Request:', {
                url: url,
                method: options.method || 'GET',
                body: requestBody ? JSON.parse(requestBody) : undefined,
                headers: options.headers
            });

            // Add auth token if it exists
            const authToken = localStorage.getItem('auth_token');
            console.log('[API] Auth token from localStorage:', authToken ? 'EXISTS' : 'NOT FOUND');
            
            const headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };
            
            if (authToken) {
                headers['Authorization'] = `Bearer ${authToken}`;
                console.log('[API] Added Authorization header');
            } else {
                console.log('[API] No auth token, no Authorization header added');
            }
            
            console.log('[API] Final headers:', headers);

            const response = await fetch(url, {
                ...options,
                body: requestBody,
                headers: headers
            });

            if (!response.ok) {
                // Use centralized error handling
                ErrorHandler.handleApiError(null, response);
                throw new Error(`API call failed: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();

            console.log(' [API] Response:', {
                url: url,
                status: response.status,
                data: data
            });
            
            // Extract and store update UUID if present
            if (data && data.updateUUID) {
                ModeContext.setLastUpdateUUID(data.updateUUID);
                console.log(' [API] Updated sync UUID:', data.updateUUID);
            }
                                                
            return data;
        } catch (error) {
            console.error(' [API] Error:', error);
            
            // Handle network errors (when fetch throws)
            if (!error.message.includes('API call failed:')) {
                // This is a network/connectivity error, not an HTTP error response
                ErrorHandler.handleApiError(error);
            }
            
            throw error;
        }
    },

    async createNote(firstVisibleNoteId = null, searchQuery = null) {
        const body = {};
        if (firstVisibleNoteId) {
            body.first_visible_note_id = firstVisibleNoteId;
        }
        if (searchQuery) {
            body.search_query = searchQuery;
        }
        
        return this._apiCall(CONFIG.API.NOTES.CREATE, {
            method: 'POST',
            body: Object.keys(body).length > 0 ? JSON.stringify(body) : undefined
        });
    },

    async createNoteDrop(parentId, siblingId, position) {
        return this._apiCall(CONFIG.API.NOTES.CREATE_DROP, {
            method: 'POST',
            body: JSON.stringify({
                new_parent_id: parentId,
                sibling_id: siblingId,
                position: position
            })
        });
    },

    async createSibling(noteId, searchQuery = null) {
        const body = {};
        if (searchQuery) {
            body.search_query = searchQuery;
        }
        
        return this._apiCall(CONFIG.API.NOTES.CREATE_SIBLING(noteId), { 
            method: 'POST',
            body: Object.keys(body).length > 0 ? JSON.stringify(body) : undefined
        });
    },

    async createChild(noteId) {
        return this._apiCall(CONFIG.API.NOTES.CREATE_CHILD(noteId), { 
            method: 'POST' 
        });
    },

    async updateNote(noteId, content) {
        return this._apiCall(CONFIG.API.NOTES.UPDATE(noteId), {
            method: 'PUT',
            body: JSON.stringify({ content })
        });
    },

    async saveNote(noteId, content) {
        return this._apiCall(CONFIG.API.NOTES.SAVE(noteId), {
            method: 'PUT',
            body: JSON.stringify({ content })
        }); 
    },

    async moveNote(noteId, siblingId, position, newParentId) {
        const body = {
            sibling_id: siblingId,
            position: position?.toUpperCase()
        };
                                
        if (newParentId !== undefined) {
            body.new_parent_id = newParentId;
        }

        return this._apiCall(CONFIG.API.NOTES.MOVE(noteId), {
            method: 'POST',
            body: JSON.stringify(body)
        });
    },

    async moveNoteRelative(noteId, direction) {
        console.log('Moving note:', { noteId, direction });
                                
        const noteElement = DOMUtils.getNoteById(noteId);
        console.log('Note element:', noteElement);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

        const siblingElement = direction === 'before' ? 
            noteElement.previousElementSibling : 
            noteElement.nextElementSibling;
        console.log('Sibling element:', siblingElement);
                                                
        if (!siblingElement) {
            console.log('No sibling found in direction:', direction);
            return;
        }

        const siblingId = DOMUtils.getNoteId(siblingElement);
        console.log('Found sibling:', { siblingId });

        const payload = { 
            position: direction.toUpperCase(),
            sibling_id: siblingId
        };
        console.log('Sending payload:', payload);

        return this._apiCall(CONFIG.API.NOTES.MOVE(noteId), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
    },

    async deleteNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.DELETE(noteId), { method: 'DELETE' });
    },

    async collapseNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.COLLAPSE(noteId), {
            method: 'POST'
        });
    },

    async expandNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.EXPAND(noteId), {
            method: 'POST'
        });
    },

    async undo() {
        return this._apiCall(`${CONFIG.API.NOTES.UNDO}?client_id=${encodeURIComponent(ModeContext.clientId)}`, { method: 'POST' });
    },

    async redo() {
        return this._apiCall(`${CONFIG.API.NOTES.REDO}?client_id=${encodeURIComponent(ModeContext.clientId)}`, { method: 'POST' });
    },

    getNoteElement(noteId) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return noteElement;
    },

    getNoteContentElement(noteId) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return noteElement.querySelector('.note-content');
    },

    async fetchView(noteId = null, searchQuery = null) {
        const payload = {
            clientId: ModeContext.clientId,
            editingNoteId: noteId || null,
            search: searchQuery || null,
            clientNoteUuidHashes: ModeContext.getNoteHashPayload(),
            clientSeenRootIds: ModeContext.getSeenRootIds()
        };

        const response = await this._apiCall(CONFIG.API.NOTES.VIEW, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        return response;
    },

    async moveNoteUp(noteId) {
        const noteElement = this.getNoteElement(noteId);
        const prevSibling = noteElement.previousElementSibling;
        if (!prevSibling || !prevSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;
                                
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(prevSibling),
            'BEFORE',
            noteElement.dataset.parentId || null
        );
    },

    async moveNoteDown(noteId) {
        const noteElement = this.getNoteElement(noteId);
        const nextSibling = noteElement.nextElementSibling;
        if (!nextSibling || !nextSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;
                                
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(nextSibling),
            'AFTER',
            noteElement.dataset.parentId || null
        );
    },

    async copyNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.COPY(noteId), {
            method: 'POST'
        });
    },

    async exportNoteAsHtml(noteId) {
        let url = CONFIG.API.NOTES.EXPORT_HTML(noteId);
        url += `?client_id=${encodeURIComponent(ModeContext.clientId)}`;
        
        return this._apiCall(url, {
            method: 'GET'
        });
    },

    async pasteNoteSibling(targetNoteId) {
        return this._apiCall(CONFIG.API.NOTES.PASTE_SIBLING(targetNoteId), {
            method: 'POST'
        });
    },

    async pasteNoteChild(targetNoteId) {
        return this._apiCall(CONFIG.API.NOTES.PASTE_CHILD(targetNoteId), {
            method: 'POST'
        });
    },

    async acquireLock(noteId) {
        return this._apiCall(CONFIG.API.NOTES.ACQUIRE_LOCK, {
            method: 'POST',
            body: JSON.stringify({ noteId })
        });
    },

    async releaseLock(noteId) {
        return this._apiCall(CONFIG.API.NOTES.RELEASE_LOCK, {
            method: 'POST', 
            body: JSON.stringify({ noteId })
        });
    }
};
