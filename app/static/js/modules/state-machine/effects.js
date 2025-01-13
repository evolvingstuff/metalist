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
        const response = await NotesAPI.createNote();
        console.log(' Note created:', response.id);
        StateMachine.currentStateContext
            .setNoteId(response.id)
            .setLastSavedContent('')
            .setCursorOffset(0);  // Start cursor at beginning of empty note
    }
}