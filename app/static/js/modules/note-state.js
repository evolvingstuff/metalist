import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { NotesAPI } from './api-client.js';
import { NoteStateMachine } from './note-state-machine.js';

/**
 * Manages the state of notes and editing
 */
export const NoteState = {
    currentEditingNote: null,
    lastSavedContent: null,
    inactivityTimeout: null,
    isFinishingEdit: false,
    
    /**
     * Start editing a note
     */
    async startEditing(noteElement) {
        return CONFIG.FEATURES.USE_STATE_MACHINE ? 
            this.startEditingWithStateMachine(noteElement) :
            this.startEditingLegacy(noteElement);
    },

    /**
     * Legacy implementation of startEditing
     */
    async startEditingLegacy(noteElement) {
        const noteId = DOMUtils.getNoteId(noteElement);
        console.log('Starting editing note:', noteId);
        
        // Store current content for change detection
        this.lastSavedContent = DOMUtils.getNoteContentText(noteElement);
        this.currentEditingNote = noteElement;

        // Make note editable
        DOMUtils.setNoteEditable(noteElement, true);

        // Set up cursor position tracking
        const content = DOMUtils.getNoteContent(noteElement);
        content.addEventListener('mouseup', this.handleCursorChange);
        content.addEventListener('keyup', this.handleCursorChange);

        // Set up auto-save
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }
        this.setupInactivityTimeout();
    },

    /**
     * New state machine implementation of startEditing
     */
    async startEditingWithStateMachine(noteElement) {
        if (!NoteStateMachine.canTransitionTo('editing')) {
            console.warn('Cannot start editing in current state:', NoteStateMachine.getState());
            return;
        }

        await NoteStateMachine.transition('editing', async () => {
            // Store current content for change detection
            this.lastSavedContent = DOMUtils.getNoteContentText(noteElement);
            this.currentEditingNote = noteElement;

            // Make note editable
            DOMUtils.setNoteEditable(noteElement, true);

            // Set up cursor position tracking
            const content = DOMUtils.getNoteContent(noteElement);
            const boundHandler = this.handleCursorChange.bind(this);
            content.addEventListener('mouseup', boundHandler);
            content.addEventListener('keyup', boundHandler);

            // Set up auto-save
            if (this.inactivityTimeout) {
                clearTimeout(this.inactivityTimeout);
            }
            this.setupInactivityTimeout();
        }, {
            currentNote: noteElement,
            lastSavedContent: DOMUtils.getNoteContentText(noteElement)
        });
    },

    /**
     * Handle content changes during editing
     */
    handleContentChange() {
        if (!this.currentEditingNote) return;

        // Clear any existing timeout
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }

        // Set new timeout for auto-save
        this.inactivityTimeout = setTimeout(() => {
            this.saveCurrentNote();
        }, CONFIG.INACTIVITY_TIMEOUT);
    },

    /**
     * Save the current note if it has changes
     */
    async saveCurrentNote() {
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.saveCurrentNoteWithStateMachine() :
            this.saveCurrentNoteLegacy();
    },

    /**
     * Legacy implementation of saveCurrentNote
     */
    async saveCurrentNoteLegacy() {
        if (!this.currentEditingNote) {
            console.log('saveCurrentNote: no currentEditingNote');
            return;
        }

        const currentContent = DOMUtils.getNoteContentText(this.currentEditingNote);
        const cursorPosition = DOMUtils.getCursorPosition(this.currentEditingNote);
        
        if (cursorPosition) {
            localStorage.setItem('cursorPosition', JSON.stringify(cursorPosition));
        }
        
        if (currentContent !== this.lastSavedContent) {
            console.log('saveCurrentNote: content changed, about to call updateNote');
            const noteId = DOMUtils.getNoteId(this.currentEditingNote);
            try {
                await NotesAPI.updateNote(noteId, currentContent);
                console.log('saveCurrentNote: updateNote completed');
            } catch (e) {
                console.error('saveCurrentNote: updateNote failed:', e);
            }
            this.lastSavedContent = currentContent;
        } else {
            console.log('saveCurrentNote: content unchanged');
        }
    },

    /**
     * New state machine implementation of saveCurrentNote
     */
    async saveCurrentNoteWithStateMachine() {
        const state = NoteStateMachine.getState();
        if (state.state !== 'editing') {
            console.warn('Cannot save note in current state:', state);
            return;
        }

        const currentNote = this.currentEditingNote;
        const currentContent = DOMUtils.getNoteContentText(currentNote);
        
        if (currentContent !== this.lastSavedContent) {
            const noteId = DOMUtils.getNoteId(currentNote);
            try {
                await NotesAPI.updateNote(noteId, currentContent);
                this.lastSavedContent = currentContent;
            } catch (e) {
                console.error('Failed to save note:', e);
                throw e;
            }
        }
    },

    /**
     * Finish editing the current note
     */
    async finishEditing() {
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.finishEditingWithStateMachine() :
            this.finishEditingLegacy();
    },

    /**
     * Legacy implementation of finishEditing
     */
    async finishEditingLegacy() {
        if (this.isFinishingEdit || !this.currentEditingNote) return;
        
        this.isFinishingEdit = true;
        try {
            // Save any pending changes
            await this.saveCurrentNote();

            // Clean up
            DOMUtils.setNoteEditable(this.currentEditingNote, false);
            
            if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
                console.log('Finished editing note:', DOMUtils.getNoteId(this.currentEditingNote));
            }

            this.currentEditingNote = null;
            this.lastSavedContent = null;
            
            if (this.inactivityTimeout) {
                clearTimeout(this.inactivityTimeout);
                this.inactivityTimeout = null;
            }
        } finally {
            this.isFinishingEdit = false;
        }
    },

    /**
     * New state machine implementation of finishEditing
     */
    async finishEditingWithStateMachine() {
        if (!this.currentEditingNote) return;

        await NoteStateMachine.transition('finishing', async () => {
            // Save any pending changes
            await this.saveCurrentNote();

            // Clean up
            DOMUtils.setNoteEditable(this.currentEditingNote, false);
            
            if (CONFIG.DEBUG.LOG_STATE_CHANGES) {
                console.log('Finished editing note:', DOMUtils.getNoteId(this.currentEditingNote));
            }

            this.currentEditingNote = null;
            this.lastSavedContent = null;
            
            if (this.inactivityTimeout) {
                clearTimeout(this.inactivityTimeout);
                this.inactivityTimeout = null;
            }
        });

        await NoteStateMachine.transition('idle');
    },

    /**
     * Check if a specific note is being edited
     */
    isEditing(noteElement) {
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.isEditingWithStateMachine(noteElement) :
            this.isEditingLegacy(noteElement);
    },

    /**
     * Legacy implementation of isEditing
     */
    isEditingLegacy(noteElement) {
        return this.currentEditingNote === noteElement;
    },

    /**
     * New state machine implementation of isEditing
     */
    isEditingWithStateMachine(noteElement) {
        const state = NoteStateMachine.getState();
        return state.state === 'editing' && state.data.currentNote === noteElement;
    },

    /**
     * Get the currently editing note element
     */
    getCurrentEditingNote() {
        return this.currentEditingNote;
    },

    /**
     * Check if any note is currently being edited
     */
    isAnyNoteEditing() {
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.isAnyNoteEditingWithStateMachine() :
            this.isAnyNoteEditingLegacy();
    },

    /**
     * Legacy implementation of isAnyNoteEditing
     */
    isAnyNoteEditingLegacy() {
        return this.currentEditingNote !== null;
    },

    /**
     * New state machine implementation of isAnyNoteEditing
     */
    isAnyNoteEditingWithStateMachine() {
        const state = NoteStateMachine.getState();
        return state.state === 'editing';
    },

    /**
     * Force save all pending changes
     */
    async forceSaveAll() {
        await this.saveCurrentNote();
    },

    /**
     * Ensure any current edits are saved before performing an action
     */
    async ensureNotesSaved(action) {
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.ensureNotesSavedWithStateMachine(action) :
            this.ensureNotesSavedLegacy(action);
    },

    /**
     * Legacy implementation of ensureNotesSaved
     */
    async ensureNotesSavedLegacy(action) {
        console.log('ensureNotesSaved:', {
            isAnyEditing: this.isAnyNoteEditing(),
            currentEditingNote: this.currentEditingNote,
            lastSavedContent: this.lastSavedContent,
            currentContent: this.currentEditingNote ? DOMUtils.getNoteContentText(this.currentEditingNote) : null
        });
        
        if (this.isAnyNoteEditing()) {
            console.log('Saving current note before action');
            await this.saveCurrentNote();
            console.log('Note saved');
        }
        console.log('Executing action');
        const result = await action();
        console.log('Action completed');
        return result;
    },

    /**
     * New state machine implementation of ensureNotesSaved
     */
    async ensureNotesSavedWithStateMachine(action) {
        const state = NoteStateMachine.getState();
        console.log('ensureNotesSaved:', state);

        if (state.state === 'editing') {
            console.log('Saving current note before action');
            const currentContent = DOMUtils.getNoteContentText(this.currentEditingNote);
            if (currentContent !== this.lastSavedContent) {
                await this.saveCurrentNote();
            }
            console.log('Note saved');
        }
        
        console.log('Executing action');
        const result = await action();
        console.log('Action completed');
        return result;
    },

    /**
     * Set up inactivity timeout for auto-save
     */
    setupInactivityTimeout() {
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.setupInactivityTimeoutWithStateMachine() :
            this.setupInactivityTimeoutLegacy();
    },

    /**
     * Legacy implementation of setupInactivityTimeout
     */
    setupInactivityTimeoutLegacy() {
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }
        
        this.inactivityTimeout = setTimeout(
            () => this.saveCurrentNote(),
            CONFIG.INACTIVITY_TIMEOUT
        );
    },

    /**
     * New state machine implementation of setupInactivityTimeout
     */
    setupInactivityTimeoutWithStateMachine() {
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }
        
        this.inactivityTimeout = setTimeout(
            () => this.saveCurrentNote(),
            CONFIG.INACTIVITY_TIMEOUT
        );
    },

    /**
     * Handle cursor position changes
     */
    handleCursorChange: function() {
        // console.log('Cursor change handler called', {
        //     useStateMachine: CONFIG.FEATURES.USE_STATE_MACHINE,
        //     currentState: NoteStateMachine.getState()
        // });
        
        return CONFIG.FEATURES.USE_STATE_MACHINE ?
            this.handleCursorChangeWithStateMachine() :
            this.handleCursorChangeLegacy();
    },

    /**
     * Legacy implementation of handleCursorChange
     */
    handleCursorChangeLegacy: function() {
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }
        this.setupInactivityTimeout();
    },

    /**
     * New state machine implementation of handleCursorChange
     */
    handleCursorChangeWithStateMachine: function() {
        if (this.inactivityTimeout) {
            clearTimeout(this.inactivityTimeout);
        }
        this.setupInactivityTimeout();
    },

    /**
     * Handle transitions from EDITING state
     */
    async handleEditingTransition(toState) {
        // Save any pending changes
        if (this.currentEditingNote) {
            await this.saveCurrentNote();
            DOMUtils.setNoteEditable(this.currentEditingNote, false);
            
            // Clean up
            this.currentEditingNote = null;
            this.lastSavedContent = null;
            
            if (this.inactivityTimeout) {
                clearTimeout(this.inactivityTimeout);
                this.inactivityTimeout = null;
            }
        }

        // Now we can transition directly to the next state
        await NoteStateMachine.transition(toState);
    }
}; 