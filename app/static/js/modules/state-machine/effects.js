import { NotesAPI } from '../api-client.js';
import { StateMachine } from './state-machine-controller.js';

export class Effect {
    async execute() {
        throw new Error('Effect must implement execute()');
    }
}

export class CreateNoteEffect extends Effect {
    async execute() {
        console.log(' Creating new note');
        const data = await NotesAPI.createNote();
        console.log(' Note created:', data.id);
        StateMachine.currentStateContext
            .setTargetNoteId(data.id)
            .setLastSavedContent('')
            .setCursorOffset(0);  
    }
}

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
            .setCursorOffset(0);  
    }
}

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
            .setCursorOffset(0);  
    }
}

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
                                
        console.log('UpdateNoteEffect: Getting lastSavedContent');
        const lastSavedContent = StateMachine.currentStateContext.getLastSavedContent();
        console.log('UpdateNoteEffect: lastSavedContent =', lastSavedContent);
        if (this.content === lastSavedContent) {
            console.log(' Note unchanged, skipping update:', this.noteId);
            return;
        }

        console.log(' Updating note:', this.noteId);
                                
        NotesAPI.updateNote(this.noteId, this.content)
            .catch(err => console.error('Failed to update note:', err));
        console.log(' Note update triggered:', this.noteId);
        StateMachine.currentStateContext.setLastSavedContent(this.content);
    }
}

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
    }
}

export class MoveNoteEffect extends Effect {
    constructor(noteId, direction) {
        super();
        if (!noteId) {
            throw new Error('Note ID required');
        }
        if (direction !== 'before' && direction !== 'after') {
            throw new Error('Direction must be "before" or "after"');
        }
        this.noteId = noteId;
        this.direction = direction;
    }

    async execute() {
        await NotesAPI.moveNoteRelative(this.noteId, this.direction);
    }
}