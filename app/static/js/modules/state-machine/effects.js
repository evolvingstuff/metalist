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