import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { DOMUtils } from '../../dom-utils.js';
import { actionSaveNote } from './content-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';
import { NotesAPI } from '../../api-client.js';

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

    // Try to acquire lock before entering edit mode
    try {
        await NotesAPI.acquireLock(noteId);
        Logger.logDebug('Acquired lock for note', { noteId });
    } catch (error) {
        Logger.logError('Failed to acquire lock', error);
        // Check if it's a connection issue or an actual lock conflict
        if (!ModeContext.isConnected) {
            // Don't show alert - connection error banner is already visible
            Logger.logDebug('Cannot acquire lock - server unavailable');
        } else if (error.message && error.message.includes('409')) {
            // Actual lock conflict
            alert('This note is being edited by another device');
        } else {
            // Some other error
            alert('Failed to acquire lock. Please try again.');
        }
        ModeContext.setCurrentNoteId(null);
        return;
    }

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

    // Release the lock when exiting edit mode
    if (noteId) {
        try {
            await NotesAPI.releaseLock(noteId);
            Logger.logDebug('Released lock for note', { noteId });
        } catch (error) {
            Logger.logError('Failed to release lock', error);
        }
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

    // Release lock on current note if switching
    if (currentNoteId) {
        try {
            await NotesAPI.releaseLock(currentNoteId);
            Logger.logDebug('Released lock when switching notes', { fromNote: currentNoteId });
        } catch (error) {
            Logger.logError('Failed to release lock when switching', error);
        }
    }

    // Try to acquire lock on new note
    try {
        await NotesAPI.acquireLock(newNoteId);
        Logger.logDebug('Acquired lock for new note', { noteId: newNoteId });
    } catch (error) {
        Logger.logError('Failed to acquire lock for new note', error);
        // Check if it's a connection issue or an actual lock conflict
        if (!ModeContext.isConnected) {
            // Don't show alert - connection error banner is already visible
            Logger.logDebug('Cannot acquire lock - server unavailable');
        } else if (error.message && error.message.includes('409')) {
            // Actual lock conflict
            alert('This note is being edited by another device');
        } else {
            // Some other error
            alert('Failed to acquire lock. Please try again.');
        }
        return;
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