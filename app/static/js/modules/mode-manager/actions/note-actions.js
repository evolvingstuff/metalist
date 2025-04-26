import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { actionSaveNote } from './content-actions.js';
import { actionSwitchNotes, actionSelectNote } from './selection-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';

export async function deleteNote(noteId) {
    Logger.logAction('deleteNote', { 
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    });

    if (!noteId) {
        throw new Error('Cannot delete note: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Programming error: Deleting note ${noteId}, but currentNoteId is ${ModeContext.currentNoteId}`);
    }

    if (!ModeContext.isEditing) {
        throw new Error(`Programming error: Deleting current note ${noteId}, but isEditing is false`);
    }

    ModeContext.setEditing(false);
    ModeContext.setCurrentNoteId(null);

    if (ModeContext.currentContent !== null) {
        ModeContext.setCurrentContent(null);
    }
        
    if (ModeContext.isDirty) {
        ModeContext.setDirty(false);
    }

    ModeContext.setLoading(true);

    await NotesAPI.deleteNote(noteId);

    ModeContext.setLoading(false);

    await actionRefreshAndMaybeSelect();

    return;
}

export async function createNote() {
    Logger.logAction('createNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const currentNoteId = ModeContext.currentNoteId;

    if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    if (!(ModeContext.isEditing && ModeContext.isDirty && currentNoteId)) {
        ModeContext.setLoading(true);
    }

    let data;
    if (currentNoteId) {
                
        Logger.logDebug('Creating new sibling note after note', { 
            currentNoteId 
        }, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createSibling(currentNoteId);
    } else {
                
        Logger.logDebug('Creating new note at top of list', {}, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createNote();
    }

    const newNoteId = data.id;

    ModeContext.setLoading(false);

    if (ModeContext.isEditing) {
        return await actionSwitchNotes(newNoteId);
    } else {
        return await actionSelectNote(newNoteId);
    }
}

export async function createChildNote() {
    Logger.logAction('createChildNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const currentNoteId = ModeContext.currentNoteId;

    if (!currentNoteId) {
        Logger.logDebug('Cannot create child note: no parent note selected', {}, Logger.LogCategory.DEBUG);
        return await createNote();
    }

    if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    if (!(ModeContext.isEditing && ModeContext.isDirty && currentNoteId)) {
        ModeContext.setLoading(true);
    }

    Logger.logDebug('Creating new child note under parent', { 
        parentNoteId: currentNoteId 
    }, Logger.LogCategory.DEBUG);
    
    const data = await NotesAPI.createChild(currentNoteId);
    const newNoteId = data.id;

    ModeContext.setLoading(false);

    if (ModeContext.isEditing) {
        return await actionSwitchNotes(newNoteId);
    } else {
        return await actionSelectNote(newNoteId);
    }
}

export async function moveNoteUp(noteId) {
    Logger.logAction('moveNoteUp', { 
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot move note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

    if (ModeContext.isEditing && noteId === ModeContext.currentNoteId) {
        ModeContext.setSavedCursorOffset(noteId, window.getSelection().focusOffset);
    }

    ModeContext.setLoading(true);
    
    try {
        await NotesAPI.moveNoteUp(noteId);
    } finally {
        ModeContext.setLoading(false);
    }

    const newContent = await actionRefreshAndMaybeSelect();

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

export async function moveNoteDown(noteId) {
    Logger.logAction('moveNoteDown', { 
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot move note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

    if (ModeContext.isEditing && noteId === ModeContext.currentNoteId) {
        ModeContext.setSavedCursorOffset(noteId, window.getSelection().focusOffset);
    }

    ModeContext.setLoading(true);
    
    try {
        await NotesAPI.moveNoteDown(noteId);
    } finally {
        ModeContext.setLoading(false);
    }

    const newContent = await actionRefreshAndMaybeSelect();

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

/**
 * Copies a note to the internal clipboard.
 * This does not call any API endpoint, it just stores the note ID for later paste operations.
 * 
 * Note: Event handler should validate context before calling this action.
 * This function assumes:
 * - We are in editing mode
 * - A valid note ID is available
 * - No text is selected (just cursor)
 */
export function actionCopyNote() {
    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionCopyNote', { 
        currentNoteId: currentNoteId,
        isEditing: ModeContext.isEditing
    });

    // Save the note ID to clipboard
    ModeContext.setClipboardNoteId(currentNoteId);
}