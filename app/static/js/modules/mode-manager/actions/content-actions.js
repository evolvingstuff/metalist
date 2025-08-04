import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';
import { CommentUtils } from '../../comment-utils.js';

export async function actionSaveNote(noteId) {
    Logger.logAction('saveNote', { noteId });

    if (!noteId) {
        throw new Error('Cannot save note: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Cannot save note ${noteId} - not the current note being edited (${ModeContext.currentNoteId})`);
    }

    const noteElement = DOMUtils.getNoteById(noteId);
    const noteContentElement = DOMUtils.getNoteContent(noteElement);
    const contentHTML = CommentUtils.getCleanContent(noteContentElement);

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

export async function actionSaveNoteOnIdle(noteId) {
    Logger.logAction('saveNoteOnIdle', { 
        noteId,
        idle: !ModeContext.isActive
    });

    if (!noteId) {
        throw new Error('Cannot save note on idle: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Cannot save note ${noteId} on idle - not the current note being edited (${ModeContext.currentNoteId})`);
    }

    if (!ModeContext.isDirty) {
        Logger.logDebug('Note not dirty, skipping idle save', { 
            noteId,
            isActive: ModeContext.isActive
        }, Logger.LogCategory.DEBUG);
        return Promise.resolve(); 
    }

    const noteElement = DOMUtils.getNoteById(noteId);
    const noteContentElement = DOMUtils.getNoteContent(noteElement);
    const contentHTML = CommentUtils.getCleanContent(noteContentElement);
    
    Logger.logDebug('Auto-saving note during idle period', {
        noteId,
        contentLength: contentHTML.length
    }, Logger.LogCategory.STATE);

    ModeContext.setLoading(true);
    const response = await NotesAPI.saveNote(noteId, contentHTML);
    ModeContext.setLoading(false);

    ModeContext.setLastSavedContent(contentHTML);
    ModeContext.setDirty(false);

    Logger.logDebug('Idle save completed successfully', {
        noteId,
        response: response ? 'success' : 'error'
    }, Logger.LogCategory.STATE);
    return response;

}