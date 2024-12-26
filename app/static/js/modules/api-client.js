import { CONFIG } from './config.js';

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
            console.log('API Request:', {
                url: url,
                method: options.method || 'GET',
                body: options.body ? JSON.parse(options.body) : undefined,
                headers: options.headers
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
            console.log('API Response:', {
                url: url,
                status: response.status,
                data: data
            });

            if (reloadOnSuccess) {
                window.location.reload();
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
        const response = await this._apiCall(CONFIG.API.NOTES.CREATE, { method: 'POST' });
        localStorage.setItem('newNoteId', response.id);
        localStorage.setItem('cursorPosition', 'end');  // Default to end for new notes
        return response;
    },

    /**
     * Create a new note via drag and drop
     */
    async createNoteDrop(parentId, siblingId, position) {
        const response = await this._apiCall(CONFIG.API.NOTES.CREATE_DROP, {
            method: 'POST',
            body: JSON.stringify({
                new_parent_id: parentId,
                sibling_id: siblingId,
                position: position
            })
        });
        localStorage.setItem('newNoteId', response.id);
        localStorage.setItem('cursorPosition', 'end');
        return response;
    },

    /**
     * Create a sibling note
     */
    async createSibling(noteId) {
        const response = await this._apiCall(CONFIG.API.NOTES.CREATE_SIBLING(noteId), { method: 'POST' });
        localStorage.setItem('newNoteId', response.id);
        localStorage.setItem('cursorPosition', 'end');
        return response;
    },

    /**
     * Create a child note
     */
    async createChild(noteId) {
        const response = await this._apiCall(CONFIG.API.NOTES.CREATE_CHILD(noteId), { method: 'POST' });
        localStorage.setItem('newNoteId', response.id);
        localStorage.setItem('cursorPosition', 'end');
        return response;
    },

    /**
     * Update a note's content
     */
    async updateNote(noteId, content) {
        return this._apiCall(CONFIG.API.NOTES.UPDATE(noteId), {
            method: 'PUT',
            body: JSON.stringify({ content })
        }, false); // Don't reload on content updates
    },

    /**
     * Move a note
     */
    async moveNote(noteId, siblingId, position, newParentId) {
        const body = {
            sibling_id: siblingId,
            position: position?.toUpperCase()
        };
        
        // Only include new_parent_id if it was actually passed
        if (newParentId !== undefined) {
            body.new_parent_id = newParentId;
        }

        console.log('Move note params:', {
            noteId,
            siblingId,
            position,
            newParentId,
            body
        });

        const response = await this._apiCall(CONFIG.API.NOTES.MOVE(noteId), {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        // Store note ID and preserve existing cursor position
        localStorage.setItem('newNoteId', noteId);
        return response;
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
    }
}; 