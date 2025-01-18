/**
 * State Machine Effects
 * 
 * Effects handle side effects during state transitions:
 * 
 * 1. Effect Pipeline:
 *    - Effects are queued in state context
 *    - Run in order during transitions
 *    - Complete before state changes
 * 
 * 2. Effect Types:
 *    - CreateNoteEffect: Creates new note and updates context
 *    - More effects can be added for other operations
 * 
 * 3. Effect Pattern:
 *    - Each effect extends base Effect class
 *    - Must implement execute() method
 *    - Should update context with results
 * 
 * Example:
 * ```
 * // 1. Queue effect
 * stateContext.queueEffect(new CreateNoteEffect());
 * 
 * // 2. Effect runs during transition
 * await effect.execute();
 * // - Creates note via API
 * // - Sets noteId in context
 * // - Sets initial content
 * // - Sets cursor position
 * ```
 */

import { NotesAPI } from '../api-client.js';
import { StateMachine } from './state-machine-controller.js';

/**
 * Base class for all effects
 */
export class Effect {
    async execute() {
        throw new Error('Effect must implement execute()');
    }
}

/**
 * Creates a new note
 */
export class CreateNoteEffect extends Effect {
    async execute() {
        console.log(' Creating new note');
        const data = await NotesAPI.createNote();
        console.log(' Note created:', data.id);
        StateMachine.currentStateContext
            .setNoteId(data.id)
            .setLastSavedContent('')
            .setCursorOffset(0);  // Start cursor at beginning of empty note
    }
}

/**
 * Creates a new child note under specified parent
 */
export class CreateChildEffect extends Effect {
    constructor(parentId) {
        super();
        if (!parentId) {
            throw new Error('Parent ID required');
        }
        this.parentId = parentId;
    }

    async execute() {
        console.log(' Creating child note under:', this.parentId);
        const data = await NotesAPI.createChild(this.parentId);
        if (!data?.id) {
            throw new Error('Invalid API response: missing note ID');
        }
        console.log(' Child note created:', data.id);
        
        StateMachine.currentStateContext
            .setTargetNoteId(data.id)
            .setLastSavedContent('')
            .setCursorOffset(0);  // Start cursor at beginning of empty note
    }
}

/**
 * Creates a new sibling note after the specified note
 */
export class CreateSiblingEffect extends Effect {
    constructor(siblingId) {
        super();
        if (!siblingId) {
            throw new Error('Sibling ID required');
        }
        this.siblingId = siblingId;
    }

    async execute() {
        console.log(' Creating sibling note after:', this.siblingId);
        const data = await NotesAPI.createSibling(this.siblingId);
        if (!data?.id) {
            throw new Error('Invalid API response: missing note ID');
        }
        console.log(' Sibling note created:', data.id);
        
        StateMachine.currentStateContext
            .setTargetNoteId(data.id)
            .setLastSavedContent('')
            .setCursorOffset(0);  // Start cursor at beginning of empty note
    }
}

/**
 * Updates a note's content
 */
export class UpdateNoteEffect extends Effect {
    constructor(noteId, content) {
        super();
        if (!noteId) {
            throw new Error('Note ID required');
        }
        if (typeof content !== 'string') {
            throw new Error('Content must be a string');
        }
        this.noteId = noteId;
        this.content = content;
    }

    async execute() {
        // Skip if content hasn't changed
        console.log('UpdateNoteEffect: Getting lastSavedContent');
        const lastSavedContent = StateMachine.currentStateContext.getLastSavedContent();
        console.log('UpdateNoteEffect: lastSavedContent =', lastSavedContent);
        if (this.content === lastSavedContent) {
            console.log(' Note unchanged, skipping update:', this.noteId);
            return;
        }

        console.log(' Updating note:', this.noteId);
        // Fire and forget - don't await
        NotesAPI.updateNote(this.noteId, this.content)
            .catch(err => console.error('Failed to update note:', err));
        console.log(' Note update triggered:', this.noteId);
        StateMachine.currentStateContext.setLastSavedContent(this.content);
    }
}

/**
 * Saves a note's content and waits for confirmation
 */
export class SaveNoteEffect extends Effect {
    constructor(noteId, content) {
        super();
        if (!noteId) {
            throw new Error('Note ID required');
        }
        if (typeof content !== 'string') {
            throw new Error('Content must be a string');
        }
        this.noteId = noteId;
        this.content = content;
    }

    async execute() {
        // Skip if content hasn't changed
        const lastSavedContent = StateMachine.currentStateContext.getLastSavedContent();
        console.log(' SaveNoteEffect comparison:', {
            noteId: this.noteId,
            contentLength: this.content.length,
            lastSavedLength: lastSavedContent.length,
            content: this.content.slice(0, 50) + '...',
            lastSaved: lastSavedContent.slice(0, 50) + '...',
            equal: this.content === lastSavedContent
        });

        if (this.content === lastSavedContent) {
            console.log(' Note unchanged, skipping save:', this.noteId);
            return;
        }

        console.log(' Saving note:', this.noteId);
        await NotesAPI.saveNote(this.noteId, this.content);
        console.log(' Note saved:', this.noteId);
        StateMachine.currentStateContext.setLastSavedContent(this.content);
    }
}

/**
 * Deletes a note and its children
 */
export class DeleteNoteEffect extends Effect {
    constructor(noteId) {
        super();
        if (!noteId) {
            throw new Error('Note ID required');
        }
        this.noteId = noteId;
    }

    async execute() {
        console.log(' Deleting note:', this.noteId);
        await NotesAPI.deleteNote(this.noteId);
        console.log(' Note deleted:', this.noteId);
        
        // Clear note ID if we just deleted the current note
        const currentNoteId = StateMachine.currentStateContext.getNoteId();
        if (currentNoteId === this.noteId) {
            StateMachine.currentStateContext
                .setNoteId(null)
                .setLastSavedContent('');
        }
    }
}