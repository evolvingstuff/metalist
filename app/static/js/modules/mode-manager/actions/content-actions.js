import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';

export async function actionSaveNote(noteId) {
    Logger.logAction('saveNote', { noteId });

    if (!noteId) {
        throw new Error('Cannot save note: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Cannot save note ${noteId} - not the current note being edited (${ModeContext.currentNoteId})`);
    }

    const noteElement = DOMUtils.getNoteById(noteId);
    const contentHTML = DOMUtils.getNoteContentHTML(noteElement);

    if (!ModeContext.isDirty) {
        Logger.logDebug('Note not dirty, skipping save', { 
            noteId,
            contentLength: contentHTML.length
        }, Logger.LogCategory.DEBUG);
        return Promise.resolve(); 
    }

    ModeContext.setLoading(true);

    const response = await NotesAPI.saveNote(noteId, contentHTML);

    ModeContext.setLastSavedContent(contentHTML);
    ModeContext.setDirty(false);

    ModeContext.setLoading(false);

    return response;
}