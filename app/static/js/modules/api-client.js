import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { StateMachine } from './state-machine/state-machine-controller.js';

export const NotesAPI = {
                
    async _apiCall(url, options = {}) {
        try {
                                                
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

    async createNote() {
        return this._apiCall(CONFIG.API.NOTES.CREATE, {
            method: 'POST'
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

    async createSibling(noteId) {
        return this._apiCall(CONFIG.API.NOTES.CREATE_SIBLING(noteId), { 
            method: 'POST' 
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

    async undo() {
        return this._apiCall(CONFIG.API.NOTES.UNDO, { method: 'POST' });
    },

    async redo() {
        return this._apiCall(CONFIG.API.NOTES.REDO, { method: 'POST' });
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