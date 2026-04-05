import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';
import { getTagBarValue, setTagBarValue } from '../services/tag-bar-service.js';
import { persistExpandedEditSessionIfNeeded } from '../services/edit-session-collapse-service.js';

function getNoteElementIfPresent(noteId) {
    if (!noteId) {
        throw new Error('noteId is required');
    }
    return document.querySelector(`[data-note-id="${noteId}"]`);
}

export async function actionSaveNote(noteId) {
    Logger.logAction('saveNote', { noteId });

    if (!noteId) {
        throw new Error('Cannot save note: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Cannot save note ${noteId} - not the current note being edited (${ModeContext.currentNoteId})`);
    }

    await persistExpandedEditSessionIfNeeded(noteId);

    const noteElement = getNoteElementIfPresent(noteId);
    if (noteElement === null) {
        Logger.logDebug('Skipping save for missing note element', { noteId });
        return Promise.resolve();
    }
    const contentHTML = DOMUtils.getNoteContentHTML(noteElement);
    const tags = getTagBarValue(noteElement);
    const previousTags = typeof noteElement.dataset.noteTags === 'string' ? noteElement.dataset.noteTags : '';
    const tagsChanged = tags !== previousTags;

    if (!ModeContext.isDirty && !tagsChanged) {
        Logger.logDebug('Note not dirty, skipping save', { 
            noteId,
            contentLength: contentHTML.length,
            tagsChanged,
        }, Logger.LogCategory.DEBUG);
        return Promise.resolve(); 
    }

    const response = await NotesAPI.saveNote(noteId, contentHTML, tags);

    if (ModeContext.isDirty) {
        ModeContext.setLastSavedContent(contentHTML);
        ModeContext.setDirty(false);
    }
    if (tagsChanged) {
        setTagBarValue(noteElement, tags);
    }

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

    await persistExpandedEditSessionIfNeeded(noteId);

    if (!ModeContext.isDirty) {
        Logger.logDebug('Note not dirty, skipping idle save', { 
            noteId,
            isActive: ModeContext.isActive
        }, Logger.LogCategory.DEBUG);
        return Promise.resolve(); 
    }

    const noteElement = getNoteElementIfPresent(noteId);
    if (noteElement === null) {
        Logger.logDebug('Skipping idle save for missing note element', { noteId });
        return Promise.resolve();
    }
    const contentHTML = DOMUtils.getNoteContentHTML(noteElement);
    const tags = getTagBarValue(noteElement);
    
    Logger.logDebug('Auto-saving note during idle period', {
        noteId,
        contentLength: contentHTML.length,
        tagsLength: tags.length,
    }, Logger.LogCategory.STATE);

    const response = await NotesAPI.saveNote(noteId, contentHTML, tags);

    ModeContext.setLastSavedContent(contentHTML);
    ModeContext.setDirty(false);
    setTagBarValue(noteElement, tags);

    Logger.logDebug('Idle save completed successfully', {
        noteId,
        response: response ? 'success' : 'error'
    }, Logger.LogCategory.STATE);
    return response;

}
