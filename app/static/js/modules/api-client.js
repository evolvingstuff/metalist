import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { StateMachine } from './state-machine/state-machine-controller.js';

/**
 * Handles all API communication
 */
export const NotesAPI = {
    /**
     * Generic API call handler with error management
     */
    async _apiCall(url, options = {}, reloadOnSuccess = true) {
        try {
            // Detailed request logging
            console.log(' [API] Request:', {
                url: url,
                method: options.method || 'GET',
                body: options.body ? JSON.parse(options.body) : undefined,
                headers: options.headers,
                reloadOnSuccess
            });

            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            if (!response.ok) {
                throw new Error(`API call failed: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();
            
            // Log the response
            console.log(' [API] Response:', {
                url: url,
                status: response.status,
                data: data,
                reloadOnSuccess
            });

            if (reloadOnSuccess) {
                console.log(' [API] Fetching fragment');
                // Instead of window.location.reload(), fetch the fragment
                if (CONFIG.DEBUG.LOG_API_CALLS) {
                    console.log('API Request:', {
                        url: '/api/notes/fragment',
                        method: 'GET'
                    });
                }

                const fragmentResponse = await fetch('/api/notes/fragment');
                const fragmentData = await fragmentResponse.json();
                
                if (CONFIG.DEBUG.LOG_API_CALLS) {
                    console.log('API Response:', {
                        url: '/api/notes/fragment',
                        status: fragmentResponse.status,
                        data: fragmentData
                    });
                }

                // Update the notes container with new HTML
                const notesContainer = document.getElementById('notes-container');
                if (notesContainer && fragmentData.data.html) {
                    notesContainer.innerHTML = fragmentData.data.html;
                    await StateMachine.handleMappedEvent({
                        type: 'FRAGMENT_LOADED',
                        data: { apiResponse: data }
                    });
                }
            }
            
            return data;
        } catch (error) {
            console.error('API Error:', error);
            alert(`Operation failed: ${error.message}`);
            throw error;
        }
    },

    /**
     * Create a new note
     */
    async createNote() {
        return this._apiCall(CONFIG.API.NOTES.CREATE, {
            method: 'POST'
        });
    },

    /**
     * Create a new note via drag and drop
     */
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

    /**
     * Create a sibling note
     */
    async createSibling(noteId) {
        return this._apiCall(CONFIG.API.NOTES.CREATE_SIBLING(noteId), { 
            method: 'POST' 
        });
    },

    /**
     * Create a child note
     */
    async createChild(noteId) {
        return this._apiCall(CONFIG.API.NOTES.CREATE_CHILD(noteId), { 
            method: 'POST' 
        });
    },

    /**
     * Update a note's content (fire and forget)
     */
    async updateNote(noteId, content) {
        return this._apiCall(CONFIG.API.NOTES.UPDATE(noteId), {
            method: 'PUT',
            body: JSON.stringify({ content })
        }, false); // Don't reload on content updates
    },

    /**
     * Save a note's content and wait for confirmation
     */
    async saveNote(noteId, content) {
        return this._apiCall(CONFIG.API.NOTES.SAVE(noteId), {
            method: 'PUT',
            body: JSON.stringify({ content })
        }); // Wait for save confirmation
    },

    /**
     * Move a note
     */
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

    /**
     * Delete a note
     */
    async deleteNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.DELETE(noteId), { method: 'DELETE' });
    },

    /**
     * Undo last action
     */
    async undo() {
        return this._apiCall(CONFIG.API.NOTES.UNDO, { method: 'POST' });
    },

    /**
     * Redo last undone action
     */
    async redo() {
        return this._apiCall(CONFIG.API.NOTES.REDO, { method: 'POST' });
    },

    async moveNoteUp(noteId) {
        const noteElement = document.querySelector(`[data-id="${noteId}"]`);
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
        const noteElement = document.querySelector(`[data-id="${noteId}"]`);
        const nextSibling = noteElement.nextElementSibling;
        if (!nextSibling || !nextSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;
        
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(nextSibling),
            'AFTER',
            noteElement.dataset.parentId || null
        );
    }
};