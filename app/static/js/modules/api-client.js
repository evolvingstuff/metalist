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
    async _apiCall(url, options = {}) {
        try {
            // Detailed request logging
            console.log(' [API] Request:', {
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
            console.log(' [API] Response:', {
                url: url,
                status: response.status,
                data: data
            });
            
            return data;
        } catch (error) {
            console.error(' [API] Error:', error);
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
        });
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
     * Move note before/after sibling
     * @param {string} noteId - ID of note to move
     * @param {string} direction - 'before' or 'after'
     */
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

    /**
     * Get a note element by ID
     */
    getNoteElement(noteId) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return noteElement;
    },

    /**
     * Get a note's content element by ID
     */
    getNoteContentElement(noteId) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return noteElement.querySelector('.note-content');
    },

    /**
     * Get updated fragment
     * @param {string|null} noteId - ID of note being edited, if any
     */
    async getFragment(noteId = null) {
        const url = `${CONFIG.API.NOTES.FRAGMENT}${noteId ? `?editing_note_id=${noteId}` : ''}`;
        return this._apiCall(url, {
            method: 'GET',
            headers: {
                'Accept': 'text/html'
            }
        });
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
    }
};