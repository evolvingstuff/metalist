import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { DOMUtils } from '../../dom-utils.js';
import { actionSaveNote } from './content-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';

export async function actionSelectNote(noteId) {
    Logger.logAction('selectNote', { 
        noteId, 
        currentNoteId: ModeContext.currentNoteId 
    });

    if (!noteId) {
        throw new Error('Cannot select note: noteId is required');
    }

    if (ModeContext.isEditing) {
        if (ModeContext.currentNoteId === noteId) {
            Logger.logDebug('Note already selected, skipping', { noteId });
            return; 
        }

        await actionDeselectNote();
    }

    ModeContext.setCurrentNoteId(noteId);

    ModeContext.setEditing(true);

    const newContent = await actionRefreshAndMaybeSelect();

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }

    ModeContext.validate();
}

export async function actionDeselectNote() {
    Logger.logAction('deselectNote', { 
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const noteId = ModeContext.currentNoteId;
    const isDirty = ModeContext.isDirty;

    if (!ModeContext.isEditing) {
        throw new Error('Cannot deselect note: not currently editing');
    }

    if (isDirty) {
        await actionSaveNote(noteId);
    }

    ModeContext.setEditing(false);

    ModeContext.setCurrentNoteId(null);

    ModeContext.setCurrentContent(null);

    await actionRefreshAndMaybeSelect();

    ModeContext.validate();
}

export async function actionSwitchNotes(newNoteId) {
    Logger.logAction('switchNotes', { 
        currentNoteId: ModeContext.currentNoteId,
        newNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    if (!newNoteId) {
        throw new Error('Cannot switch notes: newNoteId is required');
    }
        
    const currentNoteId = ModeContext.currentNoteId;

    if (currentNoteId === newNoteId) {
        Logger.logDebug('Already on this note, not switching', { noteId: newNoteId });
        return;
    }

    if (ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    const currentNoteElement = currentNoteId ? DOMUtils.getNoteById(currentNoteId) : null;

    if (currentNoteElement) {
        DOMUtils.setNoteEditable(currentNoteElement, false);
    }

    if (ModeContext.currentContent === null) {
        throw new Error(`Programming error: Switching from note ${currentNoteId} but currentContent is null`);
    }

    ModeContext.setCurrentContent(null);

    ModeContext.setCurrentNoteId(newNoteId);

    const newContent = await actionRefreshAndMaybeSelect();
    
    ModeContext.setCurrentContent(newContent);
  
    ModeContext.validate();
}