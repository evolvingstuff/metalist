import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { NoteStateMachine } from './note-state-machine.js';

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
                    await NoteStateMachine.handleFragmentLoad(data);  // Pass API response data
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
        
        if (newParentId !== undefined) {
            body.new_parent_id = newParentId;
        }

        // Check if note is being edited BEFORE the move
        const noteElement = document.querySelector(`[data-id="${noteId}"]`);
        const wasEditing = noteElement?.classList.contains(CONFIG.CLASSES.EDITING);
        
        const response = await this._apiCall(CONFIG.API.NOTES.MOVE(noteId), {
            method: 'POST',
            body: JSON.stringify(body)
        });
        
        // Only store note ID if it was being edited
        if (wasEditing) {
            localStorage.setItem('newNoteId', noteId);
            // Also store a flag to indicate this was a move operation
            localStorage.setItem('wasMovedWhileEditing', 'true');
        }
        
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
    },

    async moveNoteUp(noteId) {
        const noteElement = document.querySelector(`[data-id="${noteId}"]`);
        const prevSibling = noteElement.previousElementSibling;
        if (!prevSibling || !prevSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;

        // Store cursor position before move
        const cursorPosition = DOMUtils.getCursorPosition(noteElement);
        
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(prevSibling),
            'BEFORE',
            noteElement.dataset.parentId || null
        );

        // Store cursor position to restore after move
        if (cursorPosition) {
            localStorage.setItem('cursorPosition', JSON.stringify(cursorPosition));
        }
    },

    async moveNoteDown(noteId) {
        const noteElement = document.querySelector(`[data-id="${noteId}"]`);
        const nextSibling = noteElement.nextElementSibling;
        if (!nextSibling || !nextSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;

        // Store cursor position before move
        const cursorPosition = DOMUtils.getCursorPosition(noteElement);
        
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(nextSibling),
            'AFTER',
            noteElement.dataset.parentId || null
        );

        // Store cursor position to restore after move
        if (cursorPosition) {
            localStorage.setItem('cursorPosition', JSON.stringify(cursorPosition));
        }
    }
};